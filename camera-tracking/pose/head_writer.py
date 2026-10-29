"""Normalised body pose -> the game's head tracker, over PINE.

    w = HeadWriter(pine)      # NOPs the tracker guards (re/ram/hook.py)
    w.set(dx, dy)             # dx -1 lean left .. +1 lean right, dy 0 standing .. +1 ducked

Smoothing lives here so every pose source (headset, webcam, keyboard) gets the
same feel. Writes only when the integer value changes: with the guards NOPed the
game never stores HEAD_X/Y itself, so a written value sticks until we change it.
"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 're', 'ram'))
import hook as H


class HeadWriter:
    def __init__(self, pine, smooth_hz=12.0, deadzone=0.04):
        self.p = pine
        self.smooth_hz = smooth_hz      # exp. smoothing rate; 0 = raw
        self.deadzone = deadzone        # ignore tiny sway around neutral
        self.dx = self.dy = 0.0
        self.t = None
        self.last = None
        H.enable(pine)

    def set(self, dx, dy):
        dx = max(-1.0, min(1.0, dx))
        dy = max(0.0, min(1.0, dy))
        # soft deadzone: subtract it rather than snap, so leaving it is not a jump
        dz = self.deadzone
        dx = 0.0 if abs(dx) < dz else (dx - dz if dx > 0 else dx + dz) / (1.0 - dz)
        now = time.time()
        if self.t is None or not self.smooth_hz:
            self.dx, self.dy = dx, dy
        else:
            a = min(1.0, (now - self.t) * self.smooth_hz)
            self.dx += (dx - self.dx) * a
            self.dy += (dy - self.dy) * a
        self.t = now
        hx, hy = H.from_normalised(self.dx, self.dy)
        if (hx, hy) != self.last:
            H.set_head(self.p, hx, hy)
            self.last = (hx, hy)
        return hx, hy

    def neutral(self):
        self.dx = self.dy = 0.0
        H.set_head(self.p, *H.NEUTRAL)
        self.last = H.NEUTRAL
