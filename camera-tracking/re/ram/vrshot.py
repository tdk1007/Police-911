"""Shots for VR: fire along the gun, not along the head-rotated, widened render view.

The hit test (RE 2026-10-21, fire handler 0x185040 -> ray builder 0x184D80) casts a
world-space ray from the game's own camera pose 0x2C60E0 through the shot coordinates,
with a fixed focal length: 512x512 space centred on 256,
    h = -atan2(x - 256, 402)        v = atan2(-(y - 256) * 384/512 * 0.94 * cos(h), 402)
It never sees vrcam's head rotation or FOV. So in VR the visible crosshair (AIM,
render frame) and the shot (logic frame) need different coordinates. The fire
handler reads the shot from the getter 0x1BA6F0 at two call sites; those two are
retargeted to a cave that calls the getter and then, when a shot is pending and the
bridge has armed it, substitutes the coordinates from SLOTS. The getter's other 12
callers (menus, front end) are untouched.

    py vrshot.py --selftest
    py vrshot.py --on | --off | --status
"""
import argparse
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pine as P
import vrcam as V
from vr90 import (assemble, addiu, lui, lw, sw, sq, lq, jal, jr, NOP)

GET_SHOT = 0x001BA6F0
SITES = (0x001857EC, 0x0018583C)
SHOT_CAVE = V.CAVE + 0x800
B = V.SLOTS + 0x100
S_ON = 0x00       # u32, nonzero: substitute
S_X = 0x04        # s32, shot x in the 512 space
S_Y = 0x08        # s32, shot y
S_USED = 0x0C     # u32, bumped per substituted shot

FOCAL = 402.0
Y_SCALE = 384 / 512 * 0.94
NO_SHOT = -0xFFF


def _so(o):
    return (B + o - 0x500000) & 0xFFFF


CODE = assemble(SHOT_CAVE, [
    addiu('sp', 'sp', -0x20), sq('ra', 0x10, 'sp'), sw('a0', 0x00, 'sp'), sw('a1', 0x04, 'sp'),
    jal(GET_SHOT), NOP,                                 # v0 = its result, kept as is
    lui('t0', 0x50),
    lw('t1', _so(S_ON), 't0'),
    ('beq', 't1', 'zero', 'out'), NOP,
    lw('a0', 0x00, 'sp'), lw('t2', 0, 'a0'),
    addiu('t3', 'zero', NO_SHOT),
    ('beq', 't2', 't3', 'out'), NOP,                    # no shot pending
    lw('t2', _so(S_X), 't0'), sw('t2', 0, 'a0'),
    lw('a1', 0x04, 'sp'), lw('t2', _so(S_Y), 't0'), sw('t2', 0, 'a1'),
    lw('t2', _so(S_USED), 't0'), addiu('t2', 't2', 1), sw('t2', _so(S_USED), 't0'),
    ('label', 'out'),
    lq('ra', 0x10, 'sp'), jr('ra'), addiu('sp', 'sp', 0x20),
])

PATCHES = [(a, [jal(GET_SHOT)], [jal(SHOT_CAVE)]) for a in SITES]


def shot_coords(d):
    """Direction in the game camera's frame (x right, y up, -z forward) -> (x, y) in
    the 512 space the ray builder expects (its inverse)."""
    dx, dy, dz = d
    if dz > -1e-6:
        return None
    h = math.atan2(-dx, -dz)                        # + = left
    v = math.atan2(dy, math.hypot(dx, dz))          # + = up
    x = 256 - FOCAL * math.tan(h)
    y = 256 - math.tan(v) * FOCAL / (Y_SCALE * math.cos(h))
    return int(round(min(max(x, 0), 511))), int(round(min(max(y, 0), 511)))


def state(p):
    w = [p.read32(a) for a, _, _ in PATCHES]
    if w == [n[0] for _, _, n in PATCHES]:
        return 'on'
    if w == [o[0] for _, o, _ in PATCHES]:
        return 'off'
    raise RuntimeError('vrshot sites match neither the original nor the patched code; refusing')


def enable(p, armed=False):
    p.write_many([(B + S_ON, 1 if armed else 0), (B + S_X, 256), (B + S_Y, 256)])
    if state(p) == 'on':
        return
    for i, w in enumerate(CODE):
        p.write32(SHOT_CAVE + 4 * i, w)
    if [p.read32(SHOT_CAVE + 4 * i) for i in range(len(CODE))] != CODE:
        raise RuntimeError('cave readback mismatch')
    for a, _, new in PATCHES:
        p.write32(a, new[0])


def disable(p):
    for a, orig, _ in PATCHES:
        p.write32(a, orig[0])
    p.write32(B + S_ON, 0)


def set_shot(p, xy):
    """xy from shot_coords(), or None to stop substituting."""
    if xy is None:
        p.write32(B + S_ON, 0)
    else:
        p.write_many([(B + S_X, xy[0] & 0xFFFFFFFF), (B + S_Y, xy[1] & 0xFFFFFFFF), (B + S_ON, 1)])


def selftest():
    data = open(V.ELF, 'rb').read()
    ok = True
    for a, orig, _ in PATCHES:
        got = struct.unpack_from('<I', data, a - V.ELF_DELTA)[0]
        good = got == orig[0]
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {a:08x} {got:08x} (jal getShot)")
    import vr90
    good = (vr90.WAIT_CAVE + 4 * len(vr90.WAIT_CODE) <= SHOT_CAVE
            and SHOT_CAVE + 4 * len(CODE) < V.SLOTS and vr90.B + 0x60 <= B and B + 0x10 < 0x500000)
    ok &= good
    print(f"{'ok ' if good else 'BAD'} layout: cave {len(CODE)}w @ {SHOT_CAVE:08x}, slots @ {B:08x}")
    # the inverse really inverts the game's forward formula
    for x, y in ((256, 256), (100, 300), (500, 40), (10, 500)):
        h = -math.atan2(x - 256, FOCAL)
        v = math.atan2(-(y - 256) * Y_SCALE * math.cos(h), FOCAL)
        d = (-math.sin(h) * math.cos(v), math.sin(v), -math.cos(h) * math.cos(v))
        back = shot_coords(d)
        good = back == (x, y)
        ok &= good
        print(f"{'ok ' if good else 'BAD'} ({x},{y}) -> dir -> {back}")
    print('PASS' if ok else 'FAIL')
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest', action='store_true')
    g.add_argument('--on', action='store_true')
    g.add_argument('--off', action='store_true')
    g.add_argument('--status', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(0 if selftest() else 1)
    with P.Pine() as p:
        if a.on:
            enable(p)
            print('vrshot ON (not armed until the bridge sets a shot)')
        elif a.off:
            disable(p)
            print('vrshot OFF')
        else:
            print(state(p), 'armed', p.read32(B + S_ON), 'xy', p.read32(B + S_X), p.read32(B + S_Y),
                  'used', p.read32(B + S_USED))


if __name__ == '__main__':
    main()
