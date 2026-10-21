"""Drive the game's head tracker directly from memory.

The game computes a head position from the camera image every frame and stores
it at HEAD_X / HEAD_Y. Two branch instructions decide whether it stores a fresh
reading or holds the previous one:

    0x001BC808  bnez  $s0, 0x1bc824      ; a head was found -> go store it
    0x001BC810  bnez  $s1, 0x1bc824
    0x001BC818  lw    $s1, -0x6f7c($gp)  ; otherwise RELOAD the previous values
    0x001BC81C  b     0x1bc82c
    0x001BC820  lw    $s0, -0x6f78($gp)
    0x001BC824  sw    $s0, -0x6f78($gp)  ; <- the stores we want to never happen
    0x001BC828  sw    $s1, -0x6f7c($gp)
    0x001BC82C  jal   0x1042e0
    0x001BC838  sw    $s0, -0x6f58($gp)  ; copies, fed from $s0/$s1
    0x001BC840  sw    $s1, -0x6f5c($gp)

NOP the two guards and the code takes the reload path unconditionally. It then
loads whatever WE put at HEAD_X / HEAD_Y into $s0/$s1, skips its own stores, and
propagates our values to every downstream copy on its own.

Note this is better than NOPing the two stores: the copies at 0x001BC838 /
0x001BC840 are written from the registers, not re-read from memory, so killing
only the stores would leave the copies carrying camera-derived values.

Verified live 2026-09-13 on SLES-50285 (CRC 08A1C938):
  head_x -> on-screen dot  r = -0.99922 over 140 px
  head_y -> on-screen dot  r = +0.99799 over  78 px
and writing the solved pair put the dot inside the game's calibration ring,
which turned GREEN, while the synthetic camera blob sat somewhere else entirely.

    py hook.py --status
    py hook.py --on
    py hook.py --set 248 71
    py hook.py --off
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pine as P

# --- the hook -------------------------------------------------------------
GUARDS = (0x001BC808, 0x001BC810)
GUARD_ORIGINAL = (0x16000006, 0x16200004)      # bnez $s0,+6 / bnez $s1,+4
NOP = 0x00000000

HEAD_X = 0x0029F0F8          # int32, camera-image pixels, larger = further right
HEAD_Y = 0x0029F0F4          # int32, larger = further down

# Measured on the SENSOR ADJUSTMENT screen. head_x is MIRRORED on screen.
NEUTRAL = (248, 71)          # puts the dot in the game's calibration ring
X_RANGE = (0, 500)           # beyond ~600 the dot leaves the preview entirely
Y_RANGE = (40, 240)


def is_hooked(p):
    return tuple(p.read32(a) for a in GUARDS) == (NOP, NOP)


def enable(p):
    """NOP the guards. Returns False if the code does not look as expected."""
    words = tuple(p.read32(a) for a in GUARDS)
    if words == (NOP, NOP):
        return True
    if words != GUARD_ORIGINAL:
        raise RuntimeError(
            f"guards at {[hex(a) for a in GUARDS]} read {[hex(w) for w in words]}, "
            f"expected {[hex(w) for w in GUARD_ORIGINAL]}. Refusing to patch code "
            f"that is not what this hook was written against.")
    for a in GUARDS:
        p.write32(a, NOP)
    return True


def disable(p):
    """Put the original instructions back; the camera drives the tracker again."""
    for a, w in zip(GUARDS, GUARD_ORIGINAL):
        p.write32(a, w)


def set_head(p, x=None, y=None):
    """Write a head position. Clamped to the range the game actually uses."""
    if x is not None:
        p.write32(HEAD_X, int(max(X_RANGE[0], min(X_RANGE[1], x))))
    if y is not None:
        p.write32(HEAD_Y, int(max(Y_RANGE[0], min(Y_RANGE[1], y))))


def get_head(p):
    return p.read32(HEAD_X), p.read32(HEAD_Y)


def from_normalised(dx, dy):
    """(-1..+1, -1..+1) -> (head_x, head_y), neutral-centred.

    dx: -1 lean left, +1 lean right.  dy: -1 tall, +1 ducked.
    Sign of dx is flipped because head_x grows to the right in the camera image
    while the game mirrors it for display, and leaning right must read as right.
    Verified in play 2026-10-12: head_x=500 clears "MOVE LEFT", head_x=0 peeks right.
    (Until then this function had no flip at all, so dx=-1 leaned right.)
    """
    nx, ny = NEUTRAL
    x = nx - dx * min(nx - X_RANGE[0], X_RANGE[1] - nx)
    y = ny + dy * (Y_RANGE[1] - ny)
    return int(round(x)), int(round(y))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--status', action='store_true')
    g.add_argument('--on', action='store_true', help='NOP the guards')
    g.add_argument('--off', action='store_true', help='restore the game s own tracker')
    g.add_argument('--set', nargs=2, type=int, metavar=('X', 'Y'))
    g.add_argument('--norm', nargs=2, type=float, metavar=('DX', 'DY'),
                   help='set from normalised -1..+1 coordinates')
    g.add_argument('--demo', action='store_true', help='sweep left-right-centre')
    ap.add_argument('--port', type=int, default=P.DEFAULT_SLOT)
    args = ap.parse_args()

    with P.Pine(port=args.port) as p:
        if p.status() != P.STATUS_RUNNING:
            raise SystemExit('PCSX2 is not running a game')
        if args.status:
            words = [p.read32(a) for a in GUARDS]
            print(f"guards : {[hex(w) for w in words]} "
                  f"({'HOOKED' if is_hooked(p) else 'original'})")
            print(f"head   : x={p.read32(HEAD_X)} y={p.read32(HEAD_Y)}")
        elif args.on:
            enable(p)
            print('hook ON -- the camera no longer drives the tracker')
        elif args.off:
            disable(p)
            print('hook OFF -- the camera drives the tracker again')
        elif args.set:
            enable(p)
            set_head(p, args.set[0], args.set[1])
            print(f'head = {get_head(p)}')
        elif args.norm:
            enable(p)
            x, y = from_normalised(args.norm[0], args.norm[1])
            set_head(p, x, y)
            print(f'norm {args.norm} -> head = ({x}, {y})')
        elif args.demo:
            enable(p)
            try:
                for label, dx in (('centre', 0.0), ('left', -1.0), ('centre', 0.0),
                                  ('right', 1.0), ('centre', 0.0)):
                    x, y = from_normalised(dx, 0.0)
                    print(f'  {label:7s} dx={dx:+.1f} -> head_x={x}')
                    t = time.time()
                    while time.time() - t < 1.5:
                        set_head(p, x, y)
            finally:
                disable(p)
                print('hook OFF')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
