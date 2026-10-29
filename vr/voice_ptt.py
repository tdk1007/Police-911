"""Controller push-to-talk for Claude Code /voice while PCSX2 keeps focus.

    ptt = PushToTalk()
    ptt.update(held)      # call every frame with the button state

On press: remember the foreground window (PCSX2), focus the Claude Code
terminal, and hold Space. /voice hold mode detects a held key by its
auto-repeat, and injected keys never auto-repeat, so a repeat KEYDOWN is sent
every REPEAT_S. On release: KEYUP (voice autoSubmit then sends the prompt) and
focus goes back to the window that had it.

The terminal is the first Windows Terminal (or console) window whose title
contains `title` (case-insensitive; '' = any).
"""
import ctypes, ctypes.wintypes as W, threading, time

_u32 = ctypes.windll.user32
_k32 = ctypes.windll.kernel32
VK_SPACE, VK_MENU = 0x20, 0x12
KEYUP = 0x0002
REPEAT_S = 0.033          # ~30 Hz, like a real keyboard's typematic rate
TERMINALS = ('windowsterminal.exe', 'conhost.exe', 'openconsole.exe')


class _KI(ctypes.Structure):
    _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD),
                ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _MI(ctypes.Structure):        # only here so the union has the right size
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('mouseData', W.DWORD),
                ('dwFlags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [('ki', _KI), ('mi', _MI)]


class _IN(ctypes.Structure):
    _fields_ = [('type', W.DWORD), ('u', _U)]


def key(vk, up=False):
    i = _IN(1, _U(ki=_KI(vk, _u32.MapVirtualKeyW(vk, 0), KEYUP if up else 0, 0, 0)))
    _u32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_IN))


def _exe(hwnd):
    pid = W.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    hp = _k32.OpenProcess(0x1000, False, pid.value)      # QUERY_LIMITED_INFORMATION
    if not hp:
        return ''
    n, b = W.DWORD(512), ctypes.create_unicode_buffer(512)
    ok = _k32.QueryFullProcessImageNameW(hp, 0, b, ctypes.byref(n))
    _k32.CloseHandle(hp)
    return b.value.rsplit('\\', 1)[-1].lower() if ok else ''


def find_terminal(title=''):
    found = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        if _u32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(512)
            _u32.GetWindowTextW(h, buf, 512)
            t = buf.value.lower()
            # with no title given, skip plain consoles ("...\py.exe", "cmd.exe") --
            # the bridge and the game launcher run in those
            if (_exe(h) in TERMINALS and title.lower() in t
                    and (title or not t.endswith('.exe'))):
                found.append(h)
        return True
    _u32.EnumWindows(cb, 0)
    return found[0] if found else None


def find_exe_window(prefix):
    """The largest visible top-level window of a process whose exe starts with prefix."""
    best, area = None, 0

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        nonlocal best, area
        if _u32.IsWindowVisible(h) and _exe(h).startswith(prefix):
            r = W.RECT()
            _u32.GetWindowRect(h, ctypes.byref(r))
            a = (r.right - r.left) * (r.bottom - r.top)
            if a > area:
                best, area = h, a
        return True
    _u32.EnumWindows(cb, 0)
    return best


def focus(hwnd):
    """SetForegroundWindow from a background process: attach to the current
    foreground thread's input first; fall back to the Alt-tap trick."""
    if not hwnd or _u32.GetForegroundWindow() == hwnd:
        return bool(hwnd)
    fg = _u32.GetForegroundWindow()
    me = _k32.GetCurrentThreadId()
    other = _u32.GetWindowThreadProcessId(fg, None)
    _u32.AttachThreadInput(me, other, True)
    try:
        _u32.BringWindowToTop(hwnd)
        _u32.SetForegroundWindow(hwnd)
    finally:
        _u32.AttachThreadInput(me, other, False)
    if _u32.GetForegroundWindow() != hwnd:
        key(VK_MENU); key(VK_MENU, up=True)
        _u32.SetForegroundWindow(hwnd)
    return _u32.GetForegroundWindow() == hwnd


class PushToTalk:
    def __init__(self, title=''):
        self.title = title
        self.held = False
        self._back = None
        self._stop = threading.Event()
        self._t = None

    def _repeat(self):
        while not self._stop.wait(REPEAT_S):
            key(VK_SPACE)

    def update(self, held):
        if held and not self.held:
            self.held = True
            self._back = _u32.GetForegroundWindow()
            term = find_terminal(self.title)
            if self._back == term:
                self._back = None         # already in the terminal: nothing to return to
            if not focus(term):
                print('voice: could not focus the Claude Code terminal', flush=True)
                self.held = False
                return
            key(VK_SPACE)
            self._stop.clear()
            self._t = threading.Thread(target=self._repeat, daemon=True)
            self._t.start()
        elif not held and self.held:
            self.release()

    def release(self):
        if not self.held:
            return
        self.held = False
        self._stop.set()
        if self._t:
            self._t.join()
        key(VK_SPACE, up=True)
        time.sleep(0.15)                  # let the terminal see the key-up first
        if self._back:
            ok = focus(self._back)
            print(f'voice: focus back to {_exe(self._back) or "?"}: '
                  f'{"ok" if ok else "FAILED"}', flush=True)
