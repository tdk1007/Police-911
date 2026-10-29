"""Normalised screen point + trigger -> the game's crosshair and a real click.

    a = AimWriter(pine)
    a.set(u, v, trigger)      # u, v in 0..1 across the GAME PICTURE (not the monitor)

Aim is written straight into EE RAM (found and write-verified 2026-10-12):
    AIM_X 0x002C240C  int32, pixels from frame centre on the 640x480 frame
    AIM_Y 0x002C2410  int32, screen_y = 240 + 0.9375 * AIM_Y

Fire cannot be written: 0x002C4740 mirrors the trigger but the game ignores
writes to it. A SendInput left click with PCSX2 focused does fire, so the
trigger becomes a real mouse button. Clicks are only sent while PCSX2 is the
foreground window, so a stray trigger never clicks into another program.
"""
import ctypes

AIM_X, AIM_Y = 0x002C240C, 0x002C2410
W, H = 640, 480
Y_SCALE = 0.9375
X_LIM, Y_LIM = 320, 256

_u32 = ctypes.windll.user32
LEFTDOWN, LEFTUP = 0x0002, 0x0004


class _MI(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', ctypes.c_ulong),
                ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class _IN(ctypes.Structure):
    _fields_ = [('type', ctypes.c_ulong), ('mi', _MI)]


def click(flag):
    i = _IN(0, _MI(0, 0, 0, flag, 0, None))
    return _u32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_IN))


def pcsx2_focused():
    h = _u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetWindowTextW(h, buf, 256)
    pid = ctypes.c_ulong()
    _u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    k = ctypes.windll.kernel32
    hp = k.OpenProcess(0x1000, False, pid.value)       # PROCESS_QUERY_LIMITED_INFORMATION
    name = ''
    if hp:
        n = ctypes.c_ulong(512)
        b = ctypes.create_unicode_buffer(512)
        if k.QueryFullProcessImageNameW(hp, 0, b, ctypes.byref(n)):
            name = b.value.lower()
        k.CloseHandle(hp)
    return 'pcsx2' in name.rsplit('\\', 1)[-1]


def uv_to_aim(u, v):
    x = int(round(u * W - W / 2))
    y = int(round((v * H - H / 2) / Y_SCALE))
    return max(-X_LIM, min(X_LIM, x)), max(-Y_LIM, min(Y_LIM, y))


class AimWriter:
    def __init__(self, pine, focus=None):
        self.p = pine
        self.focus = focus        # optional: called to bring PCSX2 forward on a trigger pull
        self.last = None
        self.down = False
        self.blocked = 0          # trigger pulls ignored because PCSX2 wasn't focused

    def set(self, u, v, trigger=None):
        if u is not None and v is not None:
            xy = uv_to_aim(u, v)
            if xy != self.last:
                self.p.write32(AIM_X, xy[0] & 0xFFFFFFFF)
                self.p.write32(AIM_Y, xy[1] & 0xFFFFFFFF)
                self.last = xy
        if trigger is not None and trigger != self.down:
            if trigger and not pcsx2_focused() and self.focus:
                self.focus()
            if trigger and not pcsx2_focused():
                self.blocked += 1
                return self.last
            click(LEFTDOWN if trigger else LEFTUP)
            self.down = trigger
        return self.last

    def release(self):
        if self.down:
            click(LEFTUP)
            self.down = False
