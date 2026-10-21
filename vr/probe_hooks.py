"""Log every mouse button / key event Windows receives for N seconds (no moves).

    py probe_hooks.py [seconds]

Shows what the SteamVR desktop view sends to the PC for each controller button.
"""
import ctypes, ctypes.wintypes as W, sys, time
from voice_ptt import _exe

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120
u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, W.WPARAM, W.LPARAM)
u32.CallNextHookEx.argtypes = [W.HHOOK, ctypes.c_int, W.WPARAM, W.LPARAM]
u32.CallNextHookEx.restype = LRESULT
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, W.HINSTANCE, W.DWORD]
u32.SetWindowsHookExW.restype = W.HHOOK


class MSLL(ctypes.Structure):
    _fields_ = [('pt', W.POINT), ('mouseData', W.DWORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', ctypes.c_size_t)]


class KBLL(ctypes.Structure):
    _fields_ = [('vk', W.DWORD), ('scan', W.DWORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', ctypes.c_size_t)]


MOUSE = {0x201: 'LDOWN', 0x202: 'LUP', 0x204: 'RDOWN', 0x205: 'RUP', 0x207: 'MDOWN',
         0x208: 'MUP', 0x20A: 'WHEEL', 0x20B: 'XDOWN', 0x20C: 'XUP', 0x20E: 'HWHEEL'}
KEY = {0x100: 'KEYDOWN', 0x101: 'KEYUP', 0x104: 'SYSKEYDOWN', 0x105: 'SYSKEYUP'}
t0 = time.time()


def stamp():
    return f'{time.time() - t0:6.2f} fg={_exe(u32.GetForegroundWindow()) or "?":20}'


@HOOKPROC
def mouse(n, wp, lp):
    if n == 0 and wp in MOUSE:
        m = ctypes.cast(lp, ctypes.POINTER(MSLL)).contents
        extra = (m.mouseData >> 16) & 0xFFFF
        if wp in (0x20A, 0x20E):
            extra = ctypes.c_short(extra).value
        print(f'{stamp()} mouse {MOUSE[wp]:6} data={extra} injected={m.flags & 1} '
              f'extra=0x{m.extra:x}', flush=True)
    return u32.CallNextHookEx(None, n, wp, lp)


@HOOKPROC
def kbd(n, wp, lp):
    if n == 0 and wp in KEY:
        k = ctypes.cast(lp, ctypes.POINTER(KBLL)).contents
        print(f'{stamp()} key   {KEY[wp]:10} vk=0x{k.vk:02x} injected={(k.flags >> 4) & 1} '
              f'extra=0x{k.extra:x}', flush=True)
    return u32.CallNextHookEx(None, n, wp, lp)


hm = u32.SetWindowsHookExW(14, mouse, None, 0)
hk = u32.SetWindowsHookExW(13, kbd, None, 0)
print(f'hooks {bool(hm)} {bool(hk)} -- logging {secs:.0f}s', flush=True)
msg = W.MSG()
end = time.time() + secs
while time.time() < end:
    while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        u32.TranslateMessage(ctypes.byref(msg))
        u32.DispatchMessageW(ctypes.byref(msg))
    u32.MsgWaitForMultipleObjects(0, None, False, 50, 0x04FF)
u32.UnhookWindowsHookEx(hm)
u32.UnhookWindowsHookEx(hk)
print('done', flush=True)
