"""Check the transfer layer behaves, especially that it does not flap.

No game, no camera. Feeds synthetic pose signals through Transfer and asserts
the properties that make the rig playable rather than merely functional.

The one that matters most is the boundary-dither test: a player standing exactly
on a zone edge with a little natural sway must NOT make the cop flicker between
two poses. That is the failure mode a naive quantiser has, and it is worse than
having no zones at all.

    py transfer_selftest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transfer import Transfer, Hysteretic, Schmitt, apply_deadzone

DT = 1 / 60.0


def settle(t, lean, crouch=0.0, seconds=1.0):
    n = max(1, int(seconds / DT))
    out = (0.0, 0.0)
    for _ in range(n):
        out = t.update(lean, crouch, DT)
    return out


def main():
    checks, failures = 0, []

    def check(label, ok, detail=''):
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f'{label}{(" -- " + detail) if detail else ""}')

    # ---------------------------------------------------------------- deadzone
    check('deadzone zeroes small input', apply_deadzone(0.05, 0.1) == 0.0)
    check('deadzone is continuous at its edge',
          abs(apply_deadzone(0.1001, 0.1)) < 0.002,
          f'got {apply_deadzone(0.1001, 0.1):.4f} -- a step here means no rescaling')
    check('deadzone preserves full deflection',
          abs(apply_deadzone(1.0, 0.1) - 1.0) < 1e-9)
    check('deadzone is symmetric',
          apply_deadzone(-0.5, 0.1) == -apply_deadzone(0.5, 0.1))

    # ------------------------------------------------------------- continuous
    t = Transfer({"lean_max": 0.5, "zone_snap": False, "duck_snap": False,
                  "slew": 0.0})
    check('neutral is still', settle(t, 0.0)[0] == 0.0)
    dx_full, _ = settle(t, 0.5)
    check('full lean reaches full command', abs(dx_full - 1.0) < 1e-6,
          f'got {dx_full:.4f}')
    dx_neg, _ = settle(t, -0.5)
    check('lean is symmetric', abs(dx_neg + 1.0) < 1e-6, f'got {dx_neg:.4f}')

    prev = -2.0
    for raw in [x / 100.0 for x in range(-50, 51, 5)]:
        t.dx = t.dy = 0.0
        v = settle(t, raw, seconds=0.2)[0]
        check_mono = v >= prev - 1e-9
        if not check_mono:
            failures.append(f'response not monotonic at raw={raw}')
            checks += 1
            break
        prev = v
    else:
        checks += 1

    # ------------------------------------------------------------------- slew
    t = Transfer({"lean_max": 0.5, "zone_snap": False, "duck_snap": False,
                  "slew": 4.0, "deadzone": 0.0, "curve": 1.0})
    t.dx = 0.0
    one_step = t.update(0.5, 0.0, DT)[0]
    check('slew limits a step input', abs(one_step - 4.0 * DT) < 1e-6,
          f'moved {one_step:.4f} in one frame, expected {4.0 * DT:.4f}')
    check('slew still reaches the target', abs(settle(t, 0.5, seconds=1.0)[0] - 1.0) < 1e-6)

    # -------------------------------------------------- zone snap + hysteresis
    t = Transfer({"lean_max": 0.5, "zone_snap": True, "duck_snap": False,
                  "slew": 0.0, "deadzone": 0.0, "curve": 1.0,
                  "zone_edges": [-0.45, -0.15, 0.15, 0.45],
                  "zone_hysteresis": 0.07, "zone_dwell": 0.0})
    vals = sorted(set(round(settle(t, r / 10.0, seconds=0.3)[0], 4)
                      for r in range(-5, 6)))
    check('zone snap produces few discrete outputs', 2 <= len(vals) <= 5,
          f'got {len(vals)} distinct outputs: {vals}')

    # THE test: sway across a boundary and count how often the zone changes.
    # edge at +0.15 of command == raw 0.075 with lean_max 0.5
    h = Hysteretic([-0.45, -0.15, 0.15, 0.45], hysteresis=0.07, dwell=0.0)
    changes = 0
    last = h.zone
    for i in range(600):
        dither = 0.15 + (0.02 if i % 2 else -0.02)     # +/-0.02 about the edge
        z = h.update(dither, DT)
        if z != last:
            changes += 1
            last = z
    check('hysteresis stops boundary chatter', changes <= 1,
          f'zone changed {changes} times while dithering +/-0.02 about an edge')

    # and it must still be possible to actually change zones
    h2 = Hysteretic([-0.15, 0.15], hysteresis=0.07, dwell=0.0)
    start = h2.zone
    for _ in range(10):
        h2.update(0.9, DT)
    check('hysteresis still permits a real move', h2.zone != start,
          'a decisive lean failed to change zone')

    # dwell must rate-limit a fast swing
    h3 = Hysteretic([-0.15, 0.15], hysteresis=0.0, dwell=0.30)
    changes3 = 0
    last3 = h3.zone
    for i in range(600):
        v = 0.9 if (i // 6) % 2 else -0.9        # slam back and forth every 0.1 s
        z = h3.update(v, DT)
        if z != last3:
            changes3 += 1
            last3 = z
    # 10 s at 0.30 s minimum dwell can allow at most ~33 changes; without the
    # dwell this signal would produce ~100
    check('dwell rate-limits fast swings', changes3 <= 40,
          f'{changes3} changes in 10 s with a 0.30 s dwell')

    # ------------------------------------------------------------------- duck
    s = Schmitt(on=0.55, off=0.40, dwell=0.0)
    check('duck does not engage below the on threshold', s.update(0.5, DT) is False)
    check('duck engages above it', s.update(0.6, DT) is True)
    check('duck HOLDS between the thresholds', s.update(0.45, DT) is True,
          'a single threshold would have dropped it here')
    check('duck releases below the off threshold', s.update(0.35, DT) is False)

    flaps = 0
    s2 = Schmitt(on=0.55, off=0.40, dwell=0.0)
    prev_state = s2.state
    for i in range(600):
        v = 0.55 + (0.03 if i % 2 else -0.03)
        st = s2.update(v, DT)
        if st != prev_state:
            flaps += 1
            prev_state = st
    check('duck does not flap on its threshold', flaps <= 1,
          f'{flaps} transitions while dithering about the on threshold')

    # ------------------------------------------------------- calibration load
    t = Transfer.from_capture(os.path.join(os.path.dirname(__file__),
                                           'no_such_capture.json'))
    check('missing capture falls back to defaults, does not crash',
          t.cfg['lean_max'] > 0)

    import json, tempfile
    # Genuinely asymmetric: 0.50 of travel to the left, 0.70 to the right. Real
    # players are not symmetric, and an earlier version of this test used values
    # that happened to be equidistant, so it proved nothing.
    cap = {"poses": {
        "neutral":    {"nose_dx_shoulders": 0.10, "nose_dy_shoulders": -0.20},
        "lean_left":  {"nose_dx_shoulders": -0.40},
        "lean_right": {"nose_dx_shoulders": 0.80},
        "squat":      {"nose_dy_shoulders": 0.40},
    }}
    fd, p = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(cap, f)
    try:
        t = Transfer.from_capture(p, {"zone_snap": False, "duck_snap": False,
                                      "slew": 0.0, "deadzone": 0.0, "curve": 1.0})
        check('capture sets neutral', abs(t.cfg['lean_neutral'] - 0.10) < 1e-9)
        # span is the MEAN of the two travels: (0.50 + 0.70) / 2
        check('capture averages both travels into the span',
              abs(t.cfg['lean_max'] - 0.60) < 1e-9, f"got {t.cfg['lean_max']}")
        check('capture sets crouch span',
              abs(t.cfg['crouch_max'] - 0.60) < 1e-9, f"got {t.cfg['crouch_max']}")

        # An asymmetric player: averaging means the shorter side falls a little
        # short of full deflection and the longer side saturates. Both must still
        # be usable -- near the limit, and never beyond it.
        r = settle(t, 0.80)[0]
        l = settle(t, -0.40)[0]
        check('long side saturates at the clamp', abs(r - 1.0) < 1e-6, f'got {r:.4f}')
        check('short side still reaches most of the range', 0.80 <= -l < 1.0,
              f'got {l:.4f} -- the weaker lean should reach ~0.83, not be crippled')
        check('neither side exceeds the clamp', abs(r) <= 1.0 and abs(l) <= 1.0)
    finally:
        os.remove(p)

    for f in failures:
        print(f'  FAIL  {f}')
    print(f"transfer_selftest: {checks - len(failures)}/{checks} checks passed")
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
