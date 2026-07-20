#!/usr/bin/env python3
"""
Police 24/7 motion bridge — physical duck/cover for PCSX2.

What it does
------------
Watches you through a fixed webcam (Insta360 Link 2C), finds the top of your
silhouette (your head — the same thing the game's own Capture Eye code
tracked), and while your head drops below a calibrated duck line it HOLDS a
keyboard key (default: K) using low-level Windows SendInput with scancodes.
In PCSX2, pad Square (the game's cover/duck button when no camera is present)
is bound to that key — so physically ducking takes cover in-game, standing
back up pops you out of cover.

It can also take head data over UDP instead of the webcam (iPhone ARKit
fallback): send JSON datagrams to port 47911 (see --source udp below).

Detection method
----------------
MOG2 background subtraction on a downscaled grayscale frame. On startup (and
whenever you press B) it learns the empty scene for ~2 seconds — STAY OUT OF
FRAME during that window. After that, the highest image row containing enough
foreground pixels is taken as head height. No ML models, no GPU — reliable at
living-room range under constant lighting, ~1-2 ms per frame.

Hotkeys (preview window focused)
--------------------------------
  B  re-learn background (step out of frame first!)
  S  capture standing head level (stand upright at your play spot)
  D  set the duck line at your CURRENT head height (crouch to where you
     want "ducked" to begin, then press D)
  [ / ]  nudge duck line up / down
  P  toggle the preview overlay drawing (saves a little CPU)
  Q  quit
Calibration is saved to bridge_config.json next to this script.

Usage
-----
  python police247_bridge.py                    # webcam, preview on
  python police247_bridge.py --no-preview       # after calibrating once
  python police247_bridge.py --source udp       # iPhone ARKit mode
  python police247_bridge.py --dry-run          # log key events, don't inject
  python police247_bridge.py --selftest         # synthetic-frame self test
  python police247_bridge.py --list-cameras     # enumerate capture devices

UDP protocol (--source udp, port 47911)
---------------------------------------
One JSON object per datagram. Either of:
  {"duck": true}            explicit state (you decide on the phone)
  {"head_y": 0.42}          normalized head height, 0.0 = top of frame,
                            1.0 = floor; same calibration/hotkeys apply
Datagrams older than 0.5 s with no successor release the key (failsafe).
"""

import argparse
import ctypes
import json
import os
import socket
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "bridge_config.json")

DEFAULT_CONFIG = {
    "camera_index": 0,
    "capture_width": 640,
    "capture_height": 360,
    "capture_fps": 30,
    "proc_width": 320,          # analysis resolution (downscaled)
    "duck_key": "k",            # bound to pad Square in PCSX2
    "standing_head_y": 0.25,    # normalized; overwritten by S hotkey
    "duck_line_y": 0.50,        # head below this = ducked (D hotkey)
    "hysteresis": 0.05,         # rise this far above the line to stand
    "min_row_pixels": 10,       # fg pixels a row needs to count (at proc res)
    "min_fg_area": 600,         # ignore frames with less total fg than this
    "debounce_frames": 2,       # consecutive frames to confirm a transition
    "udp_port": 47911,
    "udp_timeout": 0.5,
}

# ---------------------------------------------------------------------------
# Windows key injection (SendInput with scancodes so games/emulators see it)
# ---------------------------------------------------------------------------

SCANCODES = {
    "a": 0x1E, "b": 0x30, "c": 0x2E, "d": 0x20, "e": 0x12, "f": 0x21,
    "g": 0x22, "h": 0x23, "i": 0x17, "j": 0x24, "k": 0x25, "l": 0x26,
    "m": 0x32, "n": 0x31, "o": 0x18, "p": 0x19, "q": 0x10, "r": 0x13,
    "s": 0x1F, "t": 0x14, "u": 0x16, "v": 0x2F, "w": 0x11, "x": 0x2D,
    "y": 0x15, "z": 0x2C,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "space": 0x39, "enter": 0x1C, "shift": 0x2A, "ctrl": 0x1D,
}

if sys.platform == "win32":
    ULONG_PTR = ctypes.wintypes.WPARAM if hasattr(ctypes, "wintypes") else ctypes.c_size_t
    import ctypes.wintypes as wt

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD),
                    ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 40)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]

    INPUT_KEYBOARD = 1
    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002

    def _send_scancode(scan, down):
        flags = KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP)
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(0, scan, flags, 0, 0)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
else:  # non-Windows: dry-run only (development convenience)
    def _send_scancode(scan, down):
        pass


class KeyOutput:
    """Holds/releases one key, with dry-run logging and crash-safe release."""

    def __init__(self, key_name, dry_run=False):
        if key_name not in SCANCODES:
            raise ValueError(f"unsupported key {key_name!r}; use a-z, 0-9, space, enter")
        self.key = key_name
        self.scan = SCANCODES[key_name]
        self.dry_run = dry_run
        self.held = False
        self.events = []  # (timestamp, "down"/"up") — used by selftest

    def set(self, down):
        if down == self.held:
            return
        self.held = down
        self.events.append((time.monotonic(), "down" if down else "up"))
        if self.dry_run:
            print(f"[key] {'DOWN' if down else 'UP  '} '{self.key}'")
        else:
            _send_scancode(self.scan, down)

    def release(self):
        self.set(False)


# ---------------------------------------------------------------------------
# Duck state machine (shared by webcam and UDP sources)
# ---------------------------------------------------------------------------

class DuckLogic:
    """head_y (0=top .. 1=bottom) -> debounced duck/stand with hysteresis."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.ducked = False
        self._pending = None
        self._pending_count = 0

    def update(self, head_y):
        cfg = self.cfg
        if head_y is None:  # nobody visible: fail safe to standing
            want = False
        elif self.ducked:
            want = bool(head_y > (cfg["duck_line_y"] - cfg["hysteresis"]))
        else:
            want = bool(head_y > cfg["duck_line_y"])
        if want != self.ducked:
            if self._pending == want:
                self._pending_count += 1
            else:
                self._pending, self._pending_count = want, 1
            if self._pending_count >= cfg["debounce_frames"]:
                self.ducked = want
                self._pending = None
        else:
            self._pending = None
        return self.ducked


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------

class HeadTracker:
    """Background-subtraction head-height tracker."""

    def __init__(self, cfg, cv2):
        self.cfg = cfg
        self.cv2 = cv2
        self.subtractor = None
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.learning = 0  # frames of background learning remaining

    def start_learning(self, frames=60):
        cv2 = self.cv2
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=24, detectShadows=True)
        self.learning = frames

    def process(self, gray):
        """gray: downscaled grayscale frame. Returns (head_y or None, mask)."""
        cv2 = self.cv2
        if self.subtractor is None:
            self.start_learning()
        # Learn fast during calibration, then FREEZE the model (lr=0).
        # A frozen background can never absorb a player holding a long duck;
        # re-learn manually (B key) if the room/lighting changes.
        lr = 0.5 if self.learning > 0 else 0.0
        mask = self.subtractor.apply(gray, learningRate=lr)
        if self.learning > 0:
            self.learning -= 1
            return None, mask
        # kill shadows (127) and noise
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        fg = cv2.countNonZero(mask)
        if fg > 0.6 * mask.size:
            # whole-scene change (lights toggled, TV flash washing the room):
            # unreliable frame — report nobody rather than a bogus head
            return None, mask
        if fg < self.cfg["min_fg_area"]:
            return None, mask
        row_counts = (mask > 0).sum(axis=1)
        rows = (row_counts >= self.cfg["min_row_pixels"]).nonzero()[0]
        if len(rows) == 0:
            return None, mask
        return float(rows[0]) / mask.shape[0], mask


# ---------------------------------------------------------------------------
# UDP source (iPhone ARKit fallback)
# ---------------------------------------------------------------------------

class UdpSource:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.last_time = 0.0
        self.head_y = None
        self.duck_override = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", cfg["udp_port"]))
        self.sock.settimeout(0.25)
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print(f"[udp] listening on 0.0.0.0:{cfg['udp_port']}")

    def _loop(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            with self.lock:
                self.last_time = time.monotonic()
                if "duck" in msg:
                    self.duck_override = bool(msg["duck"])
                    self.head_y = None
                elif "head_y" in msg:
                    try:
                        self.head_y = max(0.0, min(1.0, float(msg["head_y"])))
                    except (TypeError, ValueError):
                        continue
                    self.duck_override = None

    def read(self):
        """Returns (head_y, duck_override); both None if stale."""
        with self.lock:
            if time.monotonic() - self.last_time > self.cfg["udp_timeout"]:
                return None, None
            return self.head_y, self.duck_override

    def stop(self):
        self.running = False
        self.sock.close()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (ValueError, OSError) as e:
            print(f"[cfg] could not read {CONFIG_PATH}: {e}; using defaults")
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print(f"[cfg] saved {CONFIG_PATH}")


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------

def open_capture(cv2, index):
    """OpenCV 5 dropped DirectShow-by-index on Windows; prefer Media
    Foundation, fall back to whatever backend OpenCV picks."""
    for backend in (cv2.CAP_MSMF, cv2.CAP_ANY):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            return cap
        cap.release()
    return cv2.VideoCapture(index)


def run_webcam(cfg, key, preview=True):
    import cv2
    cap = open_capture(cv2, cfg["camera_index"])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["capture_width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["capture_height"])
    cap.set(cv2.CAP_PROP_FPS, cfg["capture_fps"])
    if not cap.isOpened():
        print(f"[cam] FAILED to open camera index {cfg['camera_index']}."
              " Run with --list-cameras and set --camera-index.")
        return 1
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[cam] opened index {cfg['camera_index']} at {w}x{h}")
    print("[cal] STEP OUT OF FRAME — learning background for ~2s...")

    tracker = HeadTracker(cfg, cv2)
    tracker.start_learning()
    logic = DuckLogic(cfg)
    proc_w = cfg["proc_width"]
    fps_t, fps_n, fps = time.monotonic(), 0, 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[cam] frame grab failed; retrying...")
                time.sleep(0.1)
                continue
            scale = proc_w / frame.shape[1]
            proc_h = int(frame.shape[0] * scale)
            small = cv2.resize(frame, (proc_w, proc_h))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            head_y, mask = tracker.process(gray)
            ducked = logic.update(head_y)
            key.set(ducked)

            fps_n += 1
            now = time.monotonic()
            if now - fps_t >= 1.0:
                fps, fps_n, fps_t = fps_n / (now - fps_t), 0, now

            if preview:
                disp = small.copy()
                dl = int(cfg["duck_line_y"] * proc_h)
                st = int(cfg["standing_head_y"] * proc_h)
                cv2.line(disp, (0, dl), (proc_w, dl), (0, 0, 255), 2)
                cv2.line(disp, (0, st), (proc_w, st), (0, 255, 0), 1)
                if head_y is not None:
                    hy = int(head_y * proc_h)
                    cv2.circle(disp, (proc_w // 2, hy), 6, (0, 255, 255), -1)
                state = "LEARNING BG" if tracker.learning > 0 else (
                    "DUCKED" if ducked else "standing")
                cv2.putText(disp, f"{state}  {fps:.0f}fps", (6, 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                            (0, 0, 255) if ducked else (0, 255, 0), 2)
                cv2.putText(disp, "B=bg S=stand D=duckline [ ]=nudge Q=quit",
                            (6, proc_h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                            (255, 255, 255), 1)
                cv2.imshow("Police 24/7 bridge", disp)
                cv2.imshow("mask", mask)
                k = cv2.waitKey(1) & 0xFF
            else:
                k = 255
                time.sleep(0.001)

            if k in (ord("q"), 27):
                break
            elif k == ord("b"):
                print("[cal] STEP OUT OF FRAME — re-learning background...")
                tracker.start_learning()
            elif k == ord("s") and head_y is not None:
                cfg["standing_head_y"] = round(head_y, 3)
                # default duck line: 60% of the way from head to mid-thigh
                cfg["duck_line_y"] = round(head_y + 0.22, 3)
                save_config(cfg)
                print(f"[cal] standing head = {cfg['standing_head_y']}, "
                      f"duck line auto-set to {cfg['duck_line_y']}")
            elif k == ord("d") and head_y is not None:
                cfg["duck_line_y"] = round(head_y - 0.02, 3)
                save_config(cfg)
                print(f"[cal] duck line = {cfg['duck_line_y']}")
            elif k == ord("["):
                cfg["duck_line_y"] = round(cfg["duck_line_y"] - 0.02, 3)
                save_config(cfg)
            elif k == ord("]"):
                cfg["duck_line_y"] = round(cfg["duck_line_y"] + 0.02, 3)
                save_config(cfg)
            elif k == ord("p"):
                preview = not preview
                cv2.destroyAllWindows()
    finally:
        key.release()
        cap.release()
        cv2.destroyAllWindows()
    return 0


def run_udp(cfg, key):
    src = UdpSource(cfg)
    logic = DuckLogic(cfg)
    print("[udp] running; Ctrl+C to quit. Send {\"duck\": true/false} or"
          " {\"head_y\": 0..1} datagrams.")
    try:
        while True:
            head_y, override = src.read()
            if override is not None:
                key.set(override)
            else:
                key.set(logic.update(head_y))
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        key.release()
        src.stop()
    return 0


# ---------------------------------------------------------------------------
# Self test — synthetic frames, no camera, no key injection
# ---------------------------------------------------------------------------

def selftest():
    import numpy as np
    import cv2

    cfg = dict(DEFAULT_CONFIG)
    cfg["debounce_frames"] = 2
    cfg["standing_head_y"] = 0.20
    cfg["duck_line_y"] = 0.45
    key = KeyOutput(cfg["duck_key"], dry_run=True)
    tracker = HeadTracker(cfg, cv2)
    tracker.start_learning(frames=40)
    logic = DuckLogic(cfg)

    H, W = 240, 320
    rng = np.random.default_rng(7)

    def scene(head_frac=None):
        img = np.full((H, W), 110, np.uint8)
        img += rng.integers(0, 6, (H, W), dtype=np.uint8)  # sensor noise
        if head_frac is not None:
            top = int(head_frac * H)
            cv2.rectangle(img, (130, top), (190, H), 30, -1)  # "person"
            # people are textured and never pixel-static
            img[top:, 130:190] += rng.integers(0, 12, (H - top, 60), dtype=np.uint8)
        return img

    phases = [("empty", None, 50), ("standing", 0.20, 30),
              ("ducked", 0.55, 30), ("standing2", 0.20, 30),
              ("gone", None, 20)]
    results = {}
    for name, head, n in phases:
        for _ in range(n):
            hy, _ = tracker.process(scene(head))
            logic.update(hy)
            key.set(logic.ducked)
        results[name] = (logic.ducked, hy)
        print(f"[selftest] after {name:10s}: ducked={logic.ducked} head_y={hy}")

    ok = (results["standing"][0] is False
          and results["ducked"][0] is True
          and results["standing2"][0] is False
          and results["gone"][0] is False)
    downs = [e for e in key.events if e[1] == "down"]
    ups = [e for e in key.events if e[1] == "up"]
    print(f"[selftest] key events: {len(downs)} down, {len(ups)} up")
    ok = ok and len(downs) == 1 and len(ups) == 1
    # head height accuracy while standing must be within 4% of truth
    if results["standing"][1] is None or abs(results["standing"][1] - 0.20) > 0.04:
        ok = False
    print(f"[selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def list_cameras():
    import cv2
    print("Probing camera indices 0-9 (Media Foundation) ...")
    found = []
    for i in range(10):
        cap = open_capture(cv2, i)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"  index {i}: {w}x{h}")
            found.append(i)
        cap.release()
    if not found:
        print("  none found")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["webcam", "udp"], default="webcam")
    ap.add_argument("--camera-index", type=int, default=None)
    ap.add_argument("--duck-key", default=None, help="key to hold while ducked")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="log key events instead of injecting them")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--list-cameras", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())
    if args.list_cameras:
        sys.exit(list_cameras())

    cfg = load_config()
    if args.camera_index is not None:
        cfg["camera_index"] = args.camera_index
        save_config(cfg)
    if args.duck_key:
        cfg["duck_key"] = args.duck_key.lower()
        save_config(cfg)

    key = KeyOutput(cfg["duck_key"], dry_run=args.dry_run)
    if args.source == "udp":
        sys.exit(run_udp(cfg, key))
    sys.exit(run_webcam(cfg, key, preview=not args.no_preview))


if __name__ == "__main__":
    main()
