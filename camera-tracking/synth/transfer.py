"""Real body movement -> the head position we command the game to see.

This is the layer that decides what the rig FEELS like, and it is deliberately
separate from both ends: it does not care whether the pose came from mediapipe
or an iPhone, nor whether the output drives a rendered frame or a PINE write.

The chain, in order:

    raw pose  -> normalise   using the player's own measured envelope
              -> deadzone    so standing still is actually still
              -> curve       so small leans are gentle and big leans commit
              -> gain+clamp  so a real 60 cm lean reaches a full in-game dodge
              -> quantise    optional: snap to arcade-style zones
              -> slew        so nothing teleports

Two feels, one switch. The PS2 port's tracking is reportedly graduated -- you can
peek partway around cover -- so CONTINUOUS is the default. The arcade cabinet read
body position off overhead sensors and behaved like discrete zones, so
`zone_snap` quantises to left / centre / right (and a separate duck channel) with
hysteresis and a minimum dwell time.

Hysteresis is not a nicety. Without it, a player standing right on a zone
boundary makes the cop flicker between two poses many times a second, which
looks broken and plays worse than no zones at all.
"""
import json
import os

DEFAULTS = {
    # normalisation: what the player's own extremes map to. Filled in from
    # capture_pose.json; these fallbacks assume a roughly symmetric player.
    "lean_neutral": 0.0,
    "lean_max": 0.55,          # raw units (nose offset in shoulder widths)
    "crouch_neutral": 0.0,
    "crouch_max": 0.45,

    "deadzone": 0.08,          # fraction of range treated as "not moving"
    "curve": 1.35,             # >1 = gentle near centre, decisive near the edge
    "gain": 1.0,               # after normalisation; >1 reaches full dodge sooner
    "limit": 1.0,              # hard clamp on the command

    "slew": 6.0,               # max command units per second (0 = unlimited)

    "zone_snap": False,
    "zone_edges": [-0.45, -0.15, 0.15, 0.45],
    "zone_hysteresis": 0.07,   # extra travel needed to LEAVE a zone
    "zone_dwell": 0.12,        # seconds a zone must be held before changing

    "duck_snap": True,         # duck is binary on the cabinet, and reads better
    "duck_on": 0.55,           # crouch fraction that engages the duck
    "duck_off": 0.40,          # and the lower level that releases it
    "duck_dwell": 0.10,

    "invert_lean": False,
    "invert_crouch": False,
}


def _sign(v):
    return -1.0 if v < 0 else 1.0


def apply_deadzone(v, dz):
    """Zero inside the deadzone, and rescale outside it so there is no step.

    Naive deadzones subtract without rescaling, which makes the command jump
    from 0 to `dz` the instant the player crosses out of it.
    """
    if dz <= 0:
        return v
    a = abs(v)
    if a <= dz:
        return 0.0
    return _sign(v) * (a - dz) / (1.0 - dz)


def apply_curve(v, gamma):
    """Shape the response while preserving sign, 0 and +/-1."""
    if gamma == 1.0:
        return v
    return _sign(v) * (abs(v) ** gamma)


class Hysteretic:
    """A quantiser that refuses to flap.

    Holds a zone until the input travels past the boundary by `hysteresis` AND
    the current zone has been held for `dwell` seconds. Both conditions matter:
    hysteresis handles a player leaning on a boundary, dwell handles a player
    swinging through one.
    """

    def __init__(self, edges, hysteresis=0.07, dwell=0.12):
        self.edges = list(edges)
        self.hysteresis = float(hysteresis)
        self.dwell = float(dwell)
        self.zone = self._raw_zone(0.0)
        self.held = 1e9          # start ready to move

    def _raw_zone(self, v):
        z = 0
        for e in self.edges:
            if v >= e:
                z += 1
        return z

    def centres(self):
        """Representative output value for each zone."""
        pts = [-1.0] + list(self.edges) + [1.0]
        return [(pts[i] + pts[i + 1]) / 2.0 for i in range(len(pts) - 1)]

    def update(self, v, dt):
        self.held += max(0.0, dt)
        want = self._raw_zone(v)
        if want != self.zone and self.held >= self.dwell:
            # require the input to be past the crossed boundary by the margin
            if want > self.zone:
                edge = self.edges[self.zone]          # boundary being crossed upward
                if v >= edge + self.hysteresis:
                    self.zone, self.held = self.zone + 1, 0.0
            else:
                edge = self.edges[self.zone - 1]
                if v <= edge - self.hysteresis:
                    self.zone, self.held = self.zone - 1, 0.0
        return self.zone


class Schmitt:
    """Two-threshold on/off with a dwell time. For the duck channel."""

    def __init__(self, on, off, dwell=0.1):
        self.on, self.off, self.dwell = float(on), float(off), float(dwell)
        self.state = False
        self.held = 1e9

    def update(self, v, dt):
        self.held += max(0.0, dt)
        if self.held >= self.dwell:
            if not self.state and v >= self.on:
                self.state, self.held = True, 0.0
            elif self.state and v <= self.off:
                self.state, self.held = False, 0.0
        return self.state


class Transfer:
    """Turn a pose reading into a commanded (dx, dy).

    `lean` and `crouch` are raw values in whatever units the pose source
    produces -- `capture_pose.py` expresses them in shoulder widths, which is
    what makes them comparable between players and between distances.
    """

    def __init__(self, config=None):
        self.cfg = dict(DEFAULTS)
        if config:
            self.cfg.update(config)
        c = self.cfg
        self.zones = Hysteretic(c["zone_edges"], c["zone_hysteresis"], c["zone_dwell"])
        self.duck = Schmitt(c["duck_on"], c["duck_off"], c["duck_dwell"])
        self.dx = 0.0
        self.dy = 0.0

    # ------------------------------------------------------------- calibration
    @classmethod
    def from_capture(cls, path, overrides=None):
        """Build from capture_pose.json -- the player's measured envelope.

        Expects the four held poses capture_pose.py records. Falls back to the
        defaults for anything missing rather than refusing to run, so a partial
        capture still gives something playable.
        """
        cfg = {}
        try:
            with open(path, encoding='utf-8-sig') as f:
                cap = json.load(f)
        except Exception:
            cap = {}
        poses = cap.get('poses', cap)

        def get(name, key):
            p = poses.get(name)
            return None if not isinstance(p, dict) else p.get(key)

        neutral = get('neutral', 'nose_dx_shoulders')
        left = get('lean_left', 'nose_dx_shoulders')
        right = get('lean_right', 'nose_dx_shoulders')
        if neutral is not None:
            cfg['lean_neutral'] = float(neutral)
        if left is not None and right is not None and neutral is not None:
            # half the total travel, so a symmetric lean reaches +/-1 either way
            cfg['lean_max'] = max(1e-3, (abs(left - neutral) + abs(right - neutral)) / 2.0)

        n_y = get('neutral', 'nose_dy_shoulders')
        sq_y = get('squat', 'nose_dy_shoulders')
        if n_y is not None:
            cfg['crouch_neutral'] = float(n_y)
        if n_y is not None and sq_y is not None:
            cfg['crouch_max'] = max(1e-3, abs(sq_y - n_y))

        if overrides:
            cfg.update(overrides)
        return cls(cfg)

    # ------------------------------------------------------------------ update
    def _shape(self, raw, neutral, span, invert):
        v = (raw - neutral) / span if span else 0.0
        if invert:
            v = -v
        v = apply_deadzone(max(-2.0, min(2.0, v)), self.cfg["deadzone"])
        v = apply_curve(v, self.cfg["curve"]) * self.cfg["gain"]
        lim = self.cfg["limit"]
        return max(-lim, min(lim, v))

    def _slew(self, cur, target, dt):
        rate = self.cfg["slew"]
        if rate <= 0 or dt <= 0:
            return target
        step = rate * dt
        if target > cur + step:
            return cur + step
        if target < cur - step:
            return cur - step
        return target

    def update(self, lean, crouch, dt):
        """One frame. Returns (dx, dy) in the -1..+1 the renderer and PINE want."""
        c = self.cfg
        x = self._shape(lean, c["lean_neutral"], c["lean_max"], c["invert_lean"])
        y = self._shape(crouch, c["crouch_neutral"], c["crouch_max"], c["invert_crouch"])

        if c["zone_snap"]:
            z = self.zones.update(x, dt)
            x = self.zones.centres()[z]

        if c["duck_snap"]:
            y = 1.0 if self.duck.update(abs(y), dt) else 0.0

        self.dx = self._slew(self.dx, x, dt)
        self.dy = self._slew(self.dy, y, dt)
        return self.dx, self.dy


def load_config(path):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return {}


if __name__ == '__main__':
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    cap = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'capture_pose.json')
    t = Transfer.from_capture(cap)
    print(f"capture: {cap} ({'found' if os.path.exists(cap) else 'MISSING -- using defaults'})")
    for k in ('lean_neutral', 'lean_max', 'crouch_neutral', 'crouch_max'):
        print(f"  {k:>16}: {t.cfg[k]}")
    print("\n  raw lean -> dx (continuous, steady state)")
    for raw in (-0.6, -0.4, -0.2, -0.05, 0.0, 0.05, 0.2, 0.4, 0.6):
        t.dx = t.dy = 0.0
        for _ in range(60):
            dx, _ = t.update(raw, 0.0, 1 / 60)
        print(f"    {raw:+.2f} -> {dx:+.3f}")
