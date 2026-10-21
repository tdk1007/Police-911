"""Head-tracked, wide-FOV render camera for VR (code cave + live slots).

The game rebuilds its render view every frame in 0x1B9180:

    0x001B92A4  jal   glLoadIdentity        ; delay slot: s0 = 0x2C60E0 (camera pose)
    0x001B92AC  glRotatef(-roll, 0,0,1) ; glRotatef(-pitch, 1,0,0) ; glRotatef(-yaw, 0,1,0)
    0x001B9314  glTranslatef(-x, -y, -z)

We retarget that one jal to a cave that does glLoadIdentity, then an eye-space
translate + roll/pitch/yaw taken from SLOTS. Calls made straight after identity
act in eye space, which is exactly where head rotation belongs. Only the render
view changes; the game's logic camera at 0x2C60E0 is untouched.

Three more spots load constants from SLOTS instead of building them inline:

    glFrustum  0x1CEF84  horizontal scale 0.3      (PCSX2's widescreen patch edits this)
    glFrustum  0x1CEFC8  vertical   scale 0.282    (later times 8/7)
    culling    0x1496C0  k_h 0.375   plane angle = 90 - k * FOV  (degrees)
    culling    0x1498B4  k_v 0.28

so FOV and culling can be changed live. A smaller scale = wider FOV
(tan(half-FOV) grows by 1/scale). A smaller k = wider culling planes.

Memory: the ELF's crt0 zero-fills BSS up to 0x500000 and calls SetupHeap(0x500000),
and no code addresses 0x4A8000-0x4FFFFF (lui scan 2026-10-20), so the cave and the
slots live there. All four savestates read zero there too.

    py vrcam.py --selftest        offline: original words match the ELF, encodings sane
    py vrcam.py --status
    py vrcam.py --on | --off
    py vrcam.py --pose YAW PITCH ROLL      degrees, head frame
    py vrcam.py --fov 1.5                  widen (tan scale), --fov 1 = stock
    py vrcam.py --cull 0.0 0.0             culling k_h k_v, stock = 0.375 0.28
    py vrcam.py --sweep yaw 20             -20..+20 deg, slow, for screenshots
"""
import argparse
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pine as P

ELF = os.path.join(HERE, '..', '..', '..', 'extracted', 'SLES_502.85')
ELF_DELTA = 0xFFF80                     # vaddr = file offset + 0xFFF80

GL_LOAD_IDENTITY = 0x001CF170
GL_ROTATEF = 0x001CE280
GL_TRANSLATEF = 0x001CEBD0

CAVE = 0x004F0000
SLOTS = 0x004F8000
# slot layout (offsets from SLOTS)
S_HSCALE = 0x00      # double, glFrustum horizontal scale
S_VSCALE = 0x08      # double, glFrustum vertical scale
S_CULL_H = 0x10      # double, culling k (horizontal planes)
S_CULL_V = 0x18      # double, culling k (vertical planes)
S_TX = 0x20          # float x3, eye-space translate applied first (already negated)
S_ROLL = 0x2C        # float, passed straight to glRotatef (already negated)
S_PITCH = 0x30
S_YAW = 0x34
S_APPLIED = 0x38     # u32, cave bumps this once per rendered view
S_POSE_SEQ = 0x40    # u32, writer bumps this with every pose
S_POSE_USED = 0x44   # u32, cave copies POSE_SEQ here when it applies a pose

STOCK = {
    S_HSCALE: 0x3FD3333340000000,       # 0.30000001192
    S_VSCALE: 0x3FD20C49C0000000,       # 0.28200000525
    S_CULL_H: 0x3FD8000000000000,       # 0.375
    S_CULL_V: 0x3FD1EB851EB851EC,       # 0.28
}

NOP = 0x00000000


def _jal(target):
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def _lui(rt, imm):
    return 0x3C000000 | (rt << 16) | (imm & 0xFFFF)


def _ld(rt, base, off):             # MIPS III ld, present on the R5900
    return 0xDC000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)


def _slot_off(o):                   # SLOTS + o as a signed offset from 0x500000
    return (SLOTS + o - 0x500000) & 0xFFFF


A0, V0, T0, T1, T2, SP, RA = 4, 2, 8, 9, 10, 29, 31


def _lwc1(ft, base, off):
    return 0xC4000000 | (base << 21) | (ft << 16) | (off & 0xFFFF)


def _mtc1(rt, fs):
    return 0x44800000 | (rt << 16) | (fs << 11)


def _lw(rt, base, off):
    return 0x8C000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)


def _sw(rt, base, off):
    return 0xAC000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)


def _addiu(rt, rs, imm):
    return 0x24000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _rot(slot, axis):
    """lui t0 ; lwc1 f12,slot ; axis into f13..f15 ; jal glRotatef (axis f15 in delay slot)."""
    ax = [_mtc1(V0 if axis == i else 0, 13 + i) for i in range(3)]
    return [_lui(T0, 0x50), _lwc1(12, T0, _slot_off(slot)), _lui(V0, 0x3F80),
            ax[0], ax[1], _jal(GL_ROTATEF), ax[2]]


CAVE_CODE = (
    [_addiu(SP, SP, -0x20),
     0x7C000000 | (SP << 21) | (RA << 16) | 0x10,           # sq ra,0x10(sp)
     _jal(GL_LOAD_IDENTITY), NOP,
     _lui(T0, 0x50),
     _lwc1(12, T0, _slot_off(S_TX)),
     _lwc1(13, T0, _slot_off(S_TX + 4)),
     _jal(GL_TRANSLATEF),
     _lwc1(14, T0, _slot_off(S_TX + 8))]                    # delay slot
    + _rot(S_ROLL, 2) + _rot(S_PITCH, 0) + _rot(S_YAW, 1)
    + [_lui(T0, 0x50),
       _lw(T1, T0, _slot_off(S_APPLIED)), _addiu(T1, T1, 1), _sw(T1, T0, _slot_off(S_APPLIED)),
       _lw(T2, T0, _slot_off(S_POSE_SEQ)), _sw(T2, T0, _slot_off(S_POSE_USED)),
       0x78000000 | (SP << 21) | (RA << 16) | 0x10,         # lq ra,0x10(sp)
       0x03E00008,                                          # jr ra
       _addiu(SP, SP, 0x20)]
)


def _ld_slot(o, nops):
    return [_lui(A0, 0x50), _ld(A0, A0, _slot_off(o))] + [NOP] * nops


# (address, original words, patched words). Every site keeps its length.
PATCHES = [
    (0x001B92A4, [_jal(GL_LOAD_IDENTITY)], [_jal(CAVE)]),
    (0x001CEF84, [0x3C043FD3, 0x34843333, 0x00042438, 0x34844000, 0x00042438], _ld_slot(S_HSCALE, 3)),
    (0x001CEFC8, [0x3C043FD2, 0x34840C49, 0x00042438, 0x3484C000, 0x00042438], _ld_slot(S_VSCALE, 3)),
    (0x001496C0, [0x3C043FD8, 0x0004203C], _ld_slot(S_CULL_H, 0)),
    (0x001498B4, [0x3C043FD1, 0x3484EB85, 0x00042438, 0x34841EB8, 0x00042438, 0x348451EC],
     _ld_slot(S_CULL_V, 4)),
]


def _f2d(x):
    return struct.unpack('<Q', struct.pack('<d', x))[0]


def _d2f(q):
    return struct.unpack('<d', struct.pack('<Q', q))[0]


# --- live -----------------------------------------------------------------
def _words(p, addr, n):
    return [p.read32(addr + 4 * i) for i in range(n)]


def state(p):
    """'on', 'off', or raise if the code is neither (wrong disc / other patch)."""
    on = off = True
    for addr, orig, new in PATCHES:
        w = _words(p, addr, len(orig))
        on &= w == new
        off &= w == orig
    if on:
        return 'on'
    if off:
        return 'off'
    raise RuntimeError('vrcam sites match neither the original nor the patched code; refusing')


def enable(p):
    if state(p) == 'on':
        return
    # slots first: the patched glFrustum would read a 0.0 scale otherwise
    for o, q in STOCK.items():
        p.write64(SLOTS + o, q)
    p.write_many([(SLOTS + o, 0) for o in range(S_TX, S_POSE_USED + 4, 4)])
    for i, w in enumerate(CAVE_CODE):
        p.write32(CAVE + 4 * i, w)
    if _words(p, CAVE, len(CAVE_CODE)) != CAVE_CODE:
        raise RuntimeError('cave readback mismatch')
    # call site last, once everything it reaches exists
    for addr, orig, new in reversed(PATCHES):
        for i, w in enumerate(new):
            p.write32(addr + 4 * i, w)


def disable(p):
    for addr, orig, new in PATCHES:
        for i, w in enumerate(orig):
            p.write32(addr + 4 * i, w)


def set_pose(p, yaw=0.0, pitch=0.0, roll=0.0, eye=(0.0, 0.0, 0.0), seq=None):
    """Head orientation in degrees (head frame) + eye offset in game units.

    The view gets the INVERSE of the head transform, so everything is negated
    here, matching how the game itself passes -yaw/-pitch/-roll and -x/-y/-z.
    Sign conventions against the HMD are to be confirmed live (see --sweep).
    """
    vals = [-eye[0], -eye[1], -eye[2], -roll, -pitch, -yaw]
    pairs = [(SLOTS + S_TX + 4 * i, struct.unpack('<I', struct.pack('<f', v))[0])
             for i, v in enumerate(vals)]
    if seq is not None:
        pairs.append((SLOTS + S_POSE_SEQ, seq & 0xFFFFFFFF))
    p.write_many(pairs)


def set_fov_scale(p, h=1.0, v=None):
    """Multiply tan(half-FOV) by h horizontally and v vertically (default v = h)."""
    v = h if v is None else v
    p.write64(SLOTS + S_HSCALE, _f2d(_d2f(STOCK[S_HSCALE]) / h))
    p.write64(SLOTS + S_VSCALE, _f2d(_d2f(STOCK[S_VSCALE]) / v))


def set_cull(p, kh, kv):
    p.write64(SLOTS + S_CULL_H, _f2d(kh))
    p.write64(SLOTS + S_CULL_V, _f2d(kv))


def read_status(p):
    f = lambda o: struct.unpack('<f', struct.pack('<I', p.read32(SLOTS + o)))[0]
    d = lambda o: _d2f(p.read64(SLOTS + o))
    return {
        'state': state(p),
        'fov_scale_h': _d2f(STOCK[S_HSCALE]) / d(S_HSCALE) if d(S_HSCALE) else 0.0,
        'fov_scale_v': _d2f(STOCK[S_VSCALE]) / d(S_VSCALE) if d(S_VSCALE) else 0.0,
        'cull_k': (d(S_CULL_H), d(S_CULL_V)),
        'yaw_pitch_roll': (-f(S_YAW), -f(S_PITCH), -f(S_ROLL)),
        'eye': tuple(-f(S_TX + 4 * i) for i in range(3)),
        'applied': p.read32(SLOTS + S_APPLIED),
        'pose_used': p.read32(SLOTS + S_POSE_USED),
        'game_fov_deg': struct.unpack('<f', struct.pack('<I', p.read32(0x002C6128)))[0],
    }


# --- offline --------------------------------------------------------------
def selftest():
    data = open(ELF, 'rb').read()
    ok = True

    def word(a):
        return struct.unpack_from('<I', data, a - ELF_DELTA)[0]

    for addr, orig, new in PATCHES:
        got = [word(addr + 4 * i) for i in range(len(orig))]
        good = got == orig and len(new) == len(orig)
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {addr:08x} {len(orig)} words")
    # the built doubles really are the stock constants
    for (addr, orig, _), o in zip(PATCHES[1:], (S_HSCALE, S_VSCALE, S_CULL_H, S_CULL_V)):
        q = 0
        for w in orig:
            op = w >> 26
            if op == 0x0F:
                q = (w & 0xFFFF) << 16
            elif op == 0x0D:
                q |= w & 0xFFFF
            elif w & 0x3F == 0x38:                  # dsll 16
                q <<= 16
            elif w & 0x3F == 0x3C:                  # dsll32
                q <<= 32
        good = q == STOCK[o]
        ok &= good
        print(f"{'ok ' if good else 'BAD'} slot +{o:02x} stock {_d2f(STOCK[o]):.9f}  built {q:016x}")
    for a, name in ((GL_LOAD_IDENTITY, 'glLoadIdentity'), (GL_ROTATEF, 'glRotatef'),
                    (GL_TRANSLATEF, 'glTranslatef')):
        # glRotatef tests for a zero angle first, so allow one word before the frame
        good = any(word(a + 4 * i) >> 16 == 0x27BD and word(a + 4 * i) & 0x8000 for i in range(2))
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {name} @ {a:08x} opens a stack frame")
    good = CAVE + 4 * len(CAVE_CODE) < SLOTS and all(SLOTS + o < 0x500000 for o in range(0, 0x48, 4))
    ok &= good
    print(f"{'ok ' if good else 'BAD'} cave {len(CAVE_CODE)} words @ {CAVE:08x}, slots @ {SLOTS:08x}")
    good = _slot_off(0) == 0x8000 and _ld(A0, A0, _slot_off(0)) == 0xDC848000
    ok &= good
    print(f"{'ok ' if good else 'BAD'} ld a0,-0x8000(a0) = {_ld(A0, A0, _slot_off(0)):08x}")
    print('PASS' if ok else 'FAIL')
    return ok


def pnach_lines():
    """The same patch as pnach lines.

    Everything is patch=1 (re-applied every vsync): crt0 zero-fills up to 0x500000
    after load, which would wipe once-only slot defaults and leave glFrustum
    with a 0.0 scale. The cost: a pnach pins the slots at stock, so anything that
    drives them (PINE, the VR fork) must write after the patch engine each frame.
    """
    out = ['// [VR camera] generated by camera-tracking/re/ram/vrcam.py --pnach']
    for o, q in STOCK.items():
        out += [f'patch=1,EE,{SLOTS + o:08X},word,{q & 0xFFFFFFFF:08X}',
                f'patch=1,EE,{SLOTS + o + 4:08X},word,{q >> 32:08X}']
    out += [f'patch=1,EE,{CAVE + 4 * i:08X},word,{w:08X}' for i, w in enumerate(CAVE_CODE)]
    for addr, _, new in reversed(PATCHES):
        out += [f'patch=1,EE,{addr + 4 * i:08X},word,{w:08X}' for i, w in enumerate(new)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest', action='store_true')
    g.add_argument('--pnach', action='store_true', help='print the patch as pnach lines')
    g.add_argument('--status', action='store_true')
    g.add_argument('--on', action='store_true')
    g.add_argument('--off', action='store_true')
    g.add_argument('--pose', nargs=3, type=float, metavar=('YAW', 'PITCH', 'ROLL'))
    g.add_argument('--fov', nargs='+', type=float, metavar='SCALE')
    g.add_argument('--cull', nargs=2, type=float, metavar=('KH', 'KV'))
    g.add_argument('--sweep', nargs=2, metavar=('AXIS', 'DEG'))
    ap.add_argument('--port', type=int, default=P.DEFAULT_SLOT)
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(0 if selftest() else 1)
    if args.pnach:
        print('\n'.join(pnach_lines()))
        return
    with P.Pine(port=args.port) as p:
        if p.status() != P.STATUS_RUNNING:
            raise SystemExit('PCSX2 is not running a game')
        if args.status:
            for k, v in read_status(p).items():
                print(f'{k:14s} {v}')
        elif args.on:
            enable(p)
            print('vrcam ON (stock FOV, zero pose)')
        elif args.off:
            disable(p)
            print('vrcam OFF (original code restored)')
        elif args.pose:
            set_pose(p, *args.pose)
        elif args.fov:
            set_fov_scale(p, *args.fov[:2])
        elif args.cull:
            set_cull(p, *args.cull)
        elif args.sweep:
            axis, deg = args.sweep[0], float(args.sweep[1])
            for a in (-deg, 0.0, deg, 0.0):
                kw = {axis: a}
                set_pose(p, **kw)
                print(f'{axis} = {a:+.1f}')
                time.sleep(3.0)


if __name__ == '__main__':
    main()
