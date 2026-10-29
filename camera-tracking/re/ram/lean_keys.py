"""Keyboard lean/duck through the head hook -- a stand-in for the headset.

    hold J  lean left        hold L  lean right        hold M  duck
    release -> ease back to neutral cover.   Ctrl+C to quit (head returns to neutral).

Keys are read globally with GetAsyncKeyState, so they work while PCSX2 has
focus. J/L/M are not bound in PCSX2.ini. head_x is mirrored on screen, so
leaning LEFT is a LARGER head_x.

    py lean_keys.py

Importable: KeyLean(p, lock).step() advances one tick, for scripts that already
hold the PINE connection (PINE does not like several busy clients at once).
"""
import ctypes, sys, threading, time, os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pine as P
import hook as H

VK_J, VK_L, VK_M = 0x4A, 0x4C, 0x4D
RATE = 6.0        # fraction of the way to the target per second (exp. smoothing)


def down(vk):
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


class KeyLean:
    def __init__(self, p, lock=None):
        self.p, self.lock = p, lock or threading.Lock()
        self.dx = self.dy = 0.0
        self.t = time.time()
        self.last = None

    def target(self):
        tx = (-1.0 if down(VK_J) else 0.0) + (1.0 if down(VK_L) else 0.0)
        ty = 1.0 if down(VK_M) else 0.0
        return tx, ty

    def step(self):
        now = time.time()
        a = min(1.0, (now - self.t) * RATE)
        self.t = now
        tx, ty = self.target()
        self.dx += (tx - self.dx) * a
        self.dy += (ty - self.dy) * a
        hx, hy = H.from_normalised(self.dx, self.dy)
        if (hx, hy) != self.last:
            with self.lock:
                H.set_head(self.p, hx, hy)
            self.last = (hx, hy)
        return hx, hy


def main():
    with P.Pine() as p:
        H.enable(p)
        k = KeyLean(p)
        print('lean_keys: hold J = left, L = right, M = duck.  Ctrl+C to stop.', flush=True)
        try:
            while True:
                k.step()
                time.sleep(1 / 120)
        except KeyboardInterrupt:
            pass
        finally:
            H.set_head(p, *H.NEUTRAL)
            print('lean_keys: stopped, head neutral')


if __name__ == '__main__':
    main()
