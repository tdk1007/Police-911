"""Hands-free Claude Code from inside VR, without ever touching window focus.

    link = ClaudeVoice()
    link.update(held)     # call every frame with the push-to-talk state (same API as PushToTalk)

Hold to talk: the mic is recorded right here (sounddevice), so PCSX2 keeps focus.
Release: faster-whisper transcribes locally and the text goes to a headless Opus
Claude Code session (`claude -p` over stream-json, cwd = this repo; the session id
is kept in claude_voice.session so context survives restarts). When Opus finishes,
Haiku rewrites its answer as a short spoken reply and Kokoro reads it out. During
long turns Haiku gives a one-line progress update every PROGRESS_S.

Talking while it speaks cuts the speech off. Spoken commands (the whole utterance):
"stop" / "cancel" interrupts Opus, "quiet" / "shut up" just stops the speech,
"repeat" says the last reply again, "which conversation" says which session it is
talking to, "new conversation" starts a fresh Opus session.

Standalone, for testing without the headset:
    py claude_voice.py --say "hello"        # TTS only
    py claude_voice.py --typed              # type prompts, hear replies
    py claude_voice.py --fresh ...          # start a new Opus session

Everything said both ways is appended to claude_voice.log.
"""
import argparse, json, os, queue, re, subprocess, sys, threading, time, uuid

import numpy as np
import sounddevice as sd

os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MODELS = os.path.join(HERE, 'models')
SESSION_FILE = os.path.join(HERE, 'claude_voice.session')
LOG = os.path.join(HERE, 'claude_voice.log')

MIC_SR = 16000
MIN_SPEECH_S = 0.3
PROGRESS_S = 60           # spoken progress update this often during a long Opus turn
WHISPER_MODEL = 'small.en'
TTS_VOICE = 'af_heart'
TTS_SPEED = 1.1
# vocabulary hint so whisper spells project words right
WHISPER_PROMPT = ('Claude, Opus, Haiku, PCSX2, Police 24/7, OpenVR, SteamVR, frame bridge, '
                  'savestate, recenter, head tracker, stereo, FOV, culling, PINE, Ghidra.')

OPUS_CONTEXT = """\
The user is wearing a VR headset and playing Police 24/7 (PCSX2 VR mod in this repo) \
while talking to you. Their messages come from speech-to-text, so expect misheard \
words and fill in the obvious meaning. They cannot read the screen: your final message \
is summarized aloud by another model, so end every turn with a plain-language final \
message that leads with the outcome (what changed, what you found, whether they need to \
restart or retest something, any question for them). Keep game interruptions in mind: \
never focus, move or close the PCSX2 window and never send keystrokes to it unless asked. \
If an action needs their approval or something is risky, stop and ask in the final message."""

HAIKU_SYSTEM = """\
You voice a coding agent for someone who is busy playing a VR game and can only listen. \
Each message is independent (ignore earlier ones) and starts with REPORT: or ACTIVITY:.

REPORT: the agent's final report. Say what a teammate would say out loud. Speak as the \
agent, in first person ("I fixed...", "I didn't change anything"); "you" is the player. \
Lead with the outcome. 1-3 short sentences unless the report asks the player a question or \
needs them to do something, then say that clearly.

ACTIVITY: the agent's recent work log, mid-task. Say in ONE short sentence (under 15 \
words) what it is doing right now.

Always output only the words to speak: no markdown, lists, code, file paths, line \
numbers, hashes or URLs (say "the frame bridge" not "vr/frame_bridge.py"). Casual, \
natural tone."""
HAIKU_RECYCLE = 8         # restart the Haiku process after this many calls (bounds its context)
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
PREFIX = re.compile(r'^\s*(REPORT|ACTIVITY)\s*:\s*', re.I)   # Haiku sometimes echoes the tag
SPEAKABLE_MAX = 240       # an Opus reply this short with no markup is spoken as-is (skips Haiku)


def log(who, text):
    line = f'{time.strftime("%H:%M:%S")} {who}: {text}'
    print(line, flush=True)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


class Haiku:
    """A Haiku process kept warm between calls (a fresh `claude -p` costs ~3 s of
    startup) that streams its answer, so the first sentence can be spoken while the
    rest is still being written."""

    def __init__(self):
        self.lock = threading.Lock()
        self.p, self.calls = None, 0

    def _start(self):
        if self.p:
            self.p.kill()
        self.p = subprocess.Popen(
            ['claude', '-p', '--input-format', 'stream-json', '--output-format', 'stream-json',
             '--verbose', '--include-partial-messages', '--model', 'haiku', '--tools', '',
             '--no-session-persistence', '--setting-sources', '', '--strict-mcp-config',
             '--system-prompt', HAIKU_SYSTEM],
            cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', bufsize=1)
        self.calls = 0

    def warm(self):
        with self.lock:
            if not self.p:
                self._start()

    def ask(self, kind, text, on_sentence=None):
        """kind is 'REPORT' or 'ACTIVITY'. on_sentence(s) gets each sentence as it
        completes. Returns the whole answer, or None if Haiku failed."""
        with self.lock:
            try:
                if not self.p or self.p.poll() is not None or self.calls >= HAIKU_RECYCLE:
                    self._start()
                self.calls += 1
                self.p.stdin.write(json.dumps({
                    'type': 'user', 'parent_tool_use_id': None,
                    'message': {'role': 'user', 'content': f'{kind}:\n{text}'}}) + '\n')
                self.p.stdin.flush()
                buf, out = '', []
                for line in self.p.stdout:
                    m = json.loads(line)
                    if m.get('type') == 'stream_event':
                        d = m['event'].get('delta', {})
                        if d.get('type') == 'text_delta':
                            buf += d['text']
                            if not out:
                                buf = PREFIX.sub('', buf)
                            *done, buf = SENTENCE_END.split(buf)
                            for s in done:
                                out.append(s)
                                on_sentence and on_sentence(s)
                    elif m.get('type') == 'result':
                        buf = PREFIX.sub('', buf) if not out else buf
                        if buf.strip():
                            out.append(buf.strip())
                            on_sentence and on_sentence(buf.strip())
                        return ' '.join(out) or None
                raise OSError('haiku process exited')
            except (OSError, ValueError) as e:
                log('haiku', f'failed: {e}')
                self.p = None
                return None


class Speaker:
    """Kokoro TTS on its own thread; say() queues, stop() cuts off what's playing."""

    def __init__(self, voice=TTS_VOICE, speed=TTS_SPEED, device=None):
        from kokoro_onnx import Kokoro
        self.tts = Kokoro(os.path.join(MODELS, 'kokoro-v1.0.onnx'),
                          os.path.join(MODELS, 'voices-v1.0.bin'))
        self.voice, self.speed, self.device = voice, speed, device
        self.q = queue.Queue()
        self.gen = 0                      # bumped by stop(); stale queue items are dropped
        self.last = ''
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text, gen=None, remember=True):
        """gen: the generation this belongs to (from self.gen when a streamed reply
        began) -- dropped if stop() happened since. remember: keep it for "repeat"."""
        gen = self.gen if gen is None else gen
        if text and gen == self.gen:
            if remember:
                self.last = text
            self.q.put((gen, text))

    def stop(self):
        self.gen += 1
        sd.stop()

    def _run(self):
        while True:
            gen, text = self.q.get()
            # sentence at a time so the first words play while the rest synthesize
            for s in SENTENCE_END.split(text.strip()):
                if gen != self.gen:
                    break
                if not s:
                    continue
                try:
                    audio, sr = self.tts.create(s, voice=self.voice, speed=self.speed, lang='en-us')
                except Exception as e:
                    log('tts', f'failed: {e}')
                    continue
                if gen != self.gen:
                    break
                sd.play(audio, sr, device=self.device)
                sd.wait()
            self.q.task_done()


class Opus:
    """A persistent headless Claude Code session. send() queues a user message;
    on_result(text) / on_activity(text) are called from the reader thread."""

    NAME = 'Claude Voice'     # display name in /resume and the desktop session list

    def __init__(self, on_result, on_activity, model='opus', fresh=False, effort=None):
        self.on_result, self.on_activity = on_result, on_activity
        self.busy = False
        self.turn_start = 0.0
        cmd = ['claude', '-p', '--input-format', 'stream-json', '--output-format', 'stream-json',
               '--verbose', '--model', model, '--permission-mode', 'auto', '--name', self.NAME,
               '--append-system-prompt', OPUS_CONTEXT]
        if effort:
            cmd += ['--effort', effort]
        self.sid = None if fresh else saved_session()
        self.resumed = bool(self.sid)
        if self.sid:
            cmd += ['--resume', self.sid]
        self.p = subprocess.Popen(cmd, cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._errors, daemon=True).start()
        log('opus', f'session {"resumed " + self.sid if self.sid else "started"}')

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            self.p.kill()

    def _write(self, obj):
        self.p.stdin.write(json.dumps(obj) + '\n')
        self.p.stdin.flush()

    def send(self, text):
        if not self.busy:
            self.busy, self.turn_start = True, time.time()
        self._write({'type': 'user', 'message': {'role': 'user', 'content': text},
                     'parent_tool_use_id': None})

    def interrupt(self):
        self._write({'type': 'control_request', 'request_id': uuid.uuid4().hex,
                     'request': {'subtype': 'interrupt'}})

    def _errors(self):
        for line in self.p.stderr:
            if line.strip():
                log('opus stderr', line.rstrip())

    def _read(self):
        for line in self.p.stdout:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            t = m.get('type')
            if t == 'system' and m.get('subtype') == 'init':
                if m['session_id'] != self.sid:
                    self.sid = m['session_id']
                    log('opus', f'session id {self.sid}')
                    set_title(self.sid)
                with open(SESSION_FILE, 'w') as f:
                    f.write(self.sid)
            elif t == 'assistant':
                for b in m.get('message', {}).get('content', []):
                    if b.get('type') == 'text' and b['text'].strip():
                        self.on_activity(b['text'].strip())
                    elif b.get('type') == 'tool_use':
                        inp = b.get('input', {})
                        what = inp.get('description') or inp.get('file_path') or inp.get('pattern') or ''
                        self.on_activity(f'[{b["name"]}] {what}'[:200])
            elif t == 'result':
                self.busy = False
                self.on_result(m.get('result') or m.get('subtype', ''), m.get('is_error', False))
        log('opus', f'process exited ({self.p.wait()})')


def saved_session():
    try:
        with open(SESSION_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def set_title(sid):
    """Console title shows which session the headset is talking to."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(
            f'Claude Voice - session {sid[:8] if sid else "(new)"}')
    except (AttributeError, OSError):
        pass


def session_age(sid):
    """'started tonight at 12:39 AM' style description of a saved session, for speech."""
    path = os.path.join(os.path.expanduser('~'), '.claude', 'projects',
                        re.sub(r'[^A-Za-z0-9]', '-', REPO), f'{sid}.jsonl')
    try:
        t = os.path.getctime(path)
    except OSError:
        return ''
    day = lambda s: time.strftime('%Y%m%d', time.localtime(s))
    when = time.strftime('%I:%M %p', time.localtime(t)).lstrip('0')
    if day(t) == day(time.time()):
        return f'from today at {when}'
    if day(t) == day(time.time() - 86400):
        return f'from yesterday at {when}'
    days = int((time.time() - t) / 86400)
    return f'from {time.strftime("%A", time.localtime(t))}' if days < 7 else f'from {days} days ago'


class AlreadyRunning(RuntimeError):
    pass


class ClaudeVoice:
    """Push-to-talk front end: record -> whisper -> Opus -> Haiku -> Kokoro.

    Only one runs at a time (a bound localhost port is the lock), so the
    standalone "Claude Voice" app and the game bridge never both answer."""

    LOCK_PORT = 47247

    def __init__(self, model='opus', fresh=False, voice=TTS_VOICE, tts_device=None,
                 mic_device=None, effort=None):
        import socket
        self._lock = socket.socket()
        try:
            self._lock.bind(('127.0.0.1', self.LOCK_PORT))
        except OSError:
            self._lock.close()
            raise AlreadyRunning('Claude voice is already running in another window')
        self.held = False
        self.mic_device = mic_device
        self._chunks, self._stream = [], None
        self._activity, self._last_said = [], time.time()
        self._jobs = queue.Queue()
        log('voice', 'loading speech models...')
        from faster_whisper import WhisperModel
        self.stt = WhisperModel(WHISPER_MODEL, device='cpu', compute_type='int8')
        self.speaker = Speaker(voice=voice, device=tts_device)
        self.haiku = Haiku()
        self.model, self.effort = model, effort
        self.opus = self._open(fresh)
        threading.Thread(target=self._work, daemon=True).start()
        threading.Thread(target=self._progress, daemon=True).start()
        threading.Thread(target=self.haiku.warm, daemon=True).start()
        log('voice', 'ready')
        self.speaker.say(f"Claude's listening. {self._which()}")

    def _open(self, fresh):
        o = Opus(self._on_result, self._on_activity, model=self.model, fresh=fresh,
                 effort=self.effort)
        set_title(o.sid)
        return o

    def _which(self):
        if not self.opus.resumed:
            return 'This is a new conversation.'
        age = session_age(self.opus.sid)
        return f'Continuing the conversation {age}.' if age else 'Continuing the last conversation.'

    # --- push-to-talk (called from the bridge loop) ---
    def update(self, held):
        if held and not self.held:
            self.held = True
            self.speaker.stop()                     # barge-in
            self._chunks = []
            self._stream = sd.InputStream(samplerate=MIC_SR, channels=1, dtype='float32',
                                          device=self.mic_device,
                                          callback=lambda d, *_: self._chunks.append(d.copy()))
            self._stream.start()
        elif not held and self.held:
            self.release()

    def release(self):
        if not self.held:
            return
        self.held = False
        self._stream.stop(); self._stream.close()
        audio = np.concatenate(self._chunks)[:, 0] if self._chunks else np.zeros(0, np.float32)
        if len(audio) >= MIN_SPEECH_S * MIC_SR:
            self._jobs.put(('audio', audio))

    def ask(self, text):
        self._jobs.put(('text', text))

    # --- worker: transcription and dispatch off the bridge's frame loop ---
    def _work(self):
        while True:
            kind, data = self._jobs.get()
            text = data if kind == 'text' else self._transcribe(data)
            if not text:
                self.speaker.say("Sorry, didn't catch that.")
                continue
            log('you', text)
            cmd = re.sub(r'[^a-z ]', '', text.lower()).strip()
            if cmd in ('stop', 'cancel', 'stop stop', 'cancel that', 'abort'):
                self.opus.interrupt()
                self.speaker.say('Stopping.')
            elif cmd in ('quiet', 'shut up', 'be quiet', 'shush', 'never mind', 'nevermind'):
                self.speaker.stop()
            elif cmd in ('repeat', 'say again', 'say that again', 'repeat that',
                         'repeat that again', 'repeat again', 'say it again', 'what did you say'):
                self.speaker.say(self.speaker.last)
            elif cmd in ('new conversation', 'start a new conversation', 'new session',
                         'start over', 'fresh start', 'start a new session'):
                self.opus.close()
                self.opus = self._open(fresh=True)
                self.speaker.say('Okay, new conversation.')
            elif cmd in ('which conversation', 'which session', 'what conversation is this',
                         'what session is this', 'which conversation is this',
                         'which session is this', 'where am i'):
                self.speaker.say(self._which())
            else:
                self.speaker.say('Still working, queued that.' if self.opus.busy else 'On it.')
                self._activity, self._last_said = [], time.time()
                self.opus.send(text)

    def _transcribe(self, audio):
        segs, _ = self.stt.transcribe(audio, language='en', beam_size=1, vad_filter=True,
                                      initial_prompt=WHISPER_PROMPT)
        return ' '.join(s.text.strip() for s in segs).strip()

    # --- Opus callbacks ---
    def _on_activity(self, text):
        self._activity = (self._activity + [text])[-12:]

    def _on_result(self, text, is_error):
        log('opus', text)
        self._last_said = time.time()
        gen = self.speaker.gen
        if text and len(text) <= SPEAKABLE_MAX and not re.search(r'[*`#/\\\n]|https?:', text):
            spoken = text                       # already plain speech: skip Haiku's few seconds
            self.speaker.say(spoken, gen=gen)
        else:
            spoken = self.haiku.ask('REPORT', text, lambda s: self.speaker.say(
                s, gen=gen, remember=False)) if text else None
        if not spoken:
            spoken = ('That run hit an error. The details are in the voice log.' if is_error
                      else text[:400])
            self.speaker.say(spoken, gen=gen)
        self.speaker.last = spoken
        log('said', spoken)
        self._last_said = time.time()

    def _progress(self):
        while True:
            time.sleep(5)
            if (self.opus.busy and self._activity and not self.held
                    and time.time() - self._last_said > PROGRESS_S):
                self._last_said = time.time()
                line = self.haiku.ask('ACTIVITY', '\n'.join(self._activity))
                if line and self.opus.busy:
                    log('said', line)
                    self.speaker.say(line, remember=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--say', help='just speak this text and exit')
    ap.add_argument('--typed', action='store_true', help='type prompts instead of talking')
    ap.add_argument('--fresh', action='store_true', help='start a new Opus session')
    ap.add_argument('--effort', choices=('low', 'medium', 'high', 'xhigh', 'max'),
                    help='Opus effort (lower = faster replies)')
    ap.add_argument('--model', default='opus')
    ap.add_argument('--voice', default=TTS_VOICE, help='Kokoro voice, e.g. af_heart, am_michael, bf_emma')
    args = ap.parse_args()
    if args.say:
        sp = Speaker(voice=args.voice)
        sp.say(args.say)
        sp.q.join()
        return
    link = ClaudeVoice(model=args.model, fresh=args.fresh, voice=args.voice, effort=args.effort)
    if args.typed:
        print('type a prompt and press Enter; Ctrl+C to quit', flush=True)
        try:
            for line in sys.stdin:
                if line.strip():
                    link.ask(line.strip())
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
