"""Decoupled render for 90 Hz VR: sim at 50 Hz game time, render every vsync (x2 for stereo).

The game is frame-locked to 50 Hz PAL vsyncs (RE_FINDINGS.md, "frame timing"). With
PCSX2's PAL rate raised to 90 Hz (FrameratePAL = 90), this patch keeps game speed
exact and spends the extra vsyncs on render-only passes:

    0x0013339C  jal sceneStep  -> jal SIM_CAVE
        acc += 50 * (vsyncs elapsed);  step only while acc >= hz * interval
        after a step: save the render's one-shot queue pointers
        no step:      restore them, so the re-render draws the same HUD/2D items
    0x001333A4  jal renderScene -> jal RENDER_CAVE
        sets the vrcam eye offset for the current pass (stereo), then renders
    0x00133114  jal waitVsync   -> jal WAIT_CAVE
        stereo: after pass 0 (eye L) loop again without waiting; pass 1 (eye R) waits
    0x001D4CBC  lw v1,8(v0) (interval) -> li v1,1     the loop waits exactly one vsync

The game itself still reads its interval (1 or 2) for its per-tick deltas, so sim
steps run at 50/interval per second, exactly like on hardware.

The one-shot render state (verified in Ghidra 2026-10-21) is reset by pointer, not cleared:
    0x2C9B70  2D queue end (reset to 0x2C9B74 in 0x14A4B0)
    0x2C9B60  two flag bytes (cleared in 0x14A470)
    0x49F440  callback queue count (zeroed in 0x220890)
    0x3A2EF8  draw hook (zeroed in 0x179F40)
so restoring the four values brings the queues back with their data intact.

    py vr90.py --selftest
    py vr90.py --on [--hz 90] [--stereo]     (vrcam must be on for --stereo)
    py vr90.py --off
    py vr90.py --measure [SECONDS]           sim steps / renders / vsyncs per second
"""
import argparse
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pine as P
import vrcam as V

SCENE_STEP = 0x001335D0
RENDER_SCENE = 0x00133690
VSYNC_WAIT = 0x001D4C80
VSYNC_TOTAL = 0x002C6054
INTERVAL = 0x002C6058

SIM_CAVE = V.CAVE + 0x400
RENDER_CAVE = V.CAVE + 0x600
B = V.SLOTS + 0x80                  # vr90 slots
S_HZ = 0x00          # u32 vsync rate the accumulator assumes; 0 = always step (patch inert)
S_LAST = 0x04        # u32 vsync total at the last call
S_ACC = 0x08         # s32 accumulator, 50 per vsync
S_SIMS = 0x0C        # u32 sim steps taken
S_RENDERS = 0x10     # u32 render passes
S_STEREO = 0x14      # u32 0 = mono, 1 = two passes
S_PASS = 0x18        # u32 current pass: 0 = L/mono, 1 = R (for the VR fork)
S_EYE_L = 0x1C       # float eye x for pass 0 (game units, head frame)
S_EYE_R = 0x20       # float eye x for pass 1
S_Q2D = 0x30         # saved 0x2C9B70
S_QFLAGS = 0x34      # saved 0x2C9B60 (u16)
S_QCB = 0x38         # saved 0x49F440
S_QHOOK = 0x3C       # saved 0x3A2EF8
S_SKIPS = 0x40       # u32 render-only passes (no sim step before them)
S_QTEXT = 0x44       # saved 0x29F0D4 (HUD text list write pointer)
S_QTEXT0 = 0x48      # saved 0x417990 (first word, overwritten by the 0xFFFFFFFF terminator)
S_QQUAD = 0x4C       # saved 0x29F0E8 (HUD quad list write pointer)
S_QQFLAG = 0x50      # saved 0x29F0D1 (byte, quad list enable)

QUEUE = [(0x002C9B70, S_Q2D, 'w'), (0x002C9B60, S_QFLAGS, 'h'),
         (0x0049F440, S_QCB, 'w'), (0x003A2EF8, S_QHOOK, 'w'),
         # HUD pass 0x1B4B80: text/sprite list 0x417990.. (0x1B4C10) and quad list 0x4206A0..
         # (0x1BAC90); both reset their write pointer at the end
         (0x0029F0D4, S_QTEXT, 'w'), (0x00417990, S_QTEXT0, 'w'),
         (0x0029F0E8, S_QQUAD, 'w'), (0x0029F0D1, S_QQFLAG, 'b')]

R = dict(zero=0, at=1, v0=2, v1=3, a0=4, a1=5, t0=8, t1=9, t2=10, t3=11, t4=12, t5=13,
         t6=14, t7=15, s0=16, s1=17, sp=29, ra=31)


# --- tiny assembler ---------------------------------------------------------
def _i(op, rs, rt, imm):
    return (op << 26) | (R[rs] << 21) | (R[rt] << 16) | (imm & 0xFFFF)


def _r(rs, rt, rd, sh, fn):
    return (R[rs] << 21) | (R[rt] << 16) | (R[rd] << 11) | (sh << 6) | fn


def lui(rt, imm): return _i(0x0F, 'zero', rt, imm)
def addiu(rt, rs, imm): return _i(0x09, rs, rt, imm)
def lw(rt, off, base): return _i(0x23, base, rt, off)
def sw(rt, off, base): return _i(0x2B, base, rt, off)
def lhu(rt, off, base): return _i(0x25, base, rt, off)
def sh(rt, off, base): return _i(0x29, base, rt, off)
def lbu(rt, off, base): return _i(0x24, base, rt, off)
def sb(rt, off, base): return _i(0x28, base, rt, off)
def addu(rd, rs, rt): return _r(rs, rt, rd, 0, 0x21)
def subu(rd, rs, rt): return _r(rs, rt, rd, 0, 0x23)
def slt(rd, rs, rt): return _r(rs, rt, rd, 0, 0x2A)
def sll(rd, rt, n): return _r('zero', rt, rd, n, 0x00)
def mult(rs, rt): return _r(rs, rt, 'zero', 0, 0x18)
def mflo(rd): return _r('zero', 'zero', rd, 0, 0x12)
def jal(t): return 0x0C000000 | ((t >> 2) & 0x03FFFFFF)
def jr(rs): return _r(rs, 'zero', 'zero', 0, 0x08)
def sq(rt, off, base): return _i(0x1F, base, rt, off)
def lq(rt, off, base): return _i(0x1E, base, rt, off)


NOP = 0


def assemble(base, prog):
    """prog: words, ('label', name), or ('beq'|'bne', rs, rt, label) / ('b', label)."""
    labels, pc = {}, base
    for x in prog:
        if isinstance(x, tuple) and x[0] == 'label':
            labels[x[1]] = pc
        else:
            pc += 4
    out, pc = [], base
    for x in prog:
        if isinstance(x, tuple):
            if x[0] == 'label':
                continue
            if x[0] == 'b':
                x = ('beq', 'zero', 'zero', x[1])
            op = {'beq': 0x04, 'bne': 0x05}[x[0]]
            off = (labels[x[3]] - (pc + 4)) >> 2
            out.append(_i(op, x[1], x[2], off))
        else:
            out.append(x)
        pc += 4
    return out


def _so(o):                          # slot offset from t0 = 0x500000
    return (B + o - 0x500000) & 0xFFFF


def _abs(a):                         # (hi, lo) for lui/offset addressing of an absolute address
    lo = a & 0xFFFF
    hi = (a >> 16) + (1 if lo & 0x8000 else 0)
    return hi & 0xFFFF, lo


def _queue(save):
    code = []
    for addr, o, kind in QUEUE:
        hi, lo = _abs(addr)
        code.append(lui('t1', hi))
        ld, st = {'w': (lw, sw), 'h': (lhu, sh), 'b': (lbu, sb)}[kind]
        if save:
            code += [ld('t2', lo, 't1'), st('t2', _so(o), 't0')]
        else:
            code += [ld('t2', _so(o), 't0'), st('t2', lo, 't1')]
    return code


_vh, _vl = _abs(VSYNC_TOTAL)
SIM_CODE = assemble(SIM_CAVE, [
    addiu('sp', 'sp', -0x20), sq('ra', 0x10, 'sp'), sq('a0', 0x00, 'sp'),
    lui('t0', 0x50),
    lw('t1', _so(S_STEREO), 't0'),                     # stereo pass 1 (eye R) never steps
    ('beq', 't1', 'zero', 'mono'), NOP,
    lw('t1', _so(S_PASS), 't0'),
    ('bne', 't1', 'zero', 'again'), NOP,
    ('label', 'mono'),
    lw('t1', _so(S_HZ), 't0'),
    ('beq', 't1', 'zero', 'step'), NOP,
    lui('t2', _vh), lw('t3', _vl, 't2'),               # t3 = vsync total
    lw('t4', _so(S_LAST), 't0'), sw('t3', _so(S_LAST), 't0'),
    subu('t3', 't3', 't4'),                            # elapsed
    sll('t4', 't3', 5), sll('t5', 't3', 4), addu('t4', 't4', 't5'),
    sll('t5', 't3', 1), addu('t4', 't4', 't5'),        # 50 * elapsed
    lw('t5', _so(S_ACC), 't0'), addu('t5', 't5', 't4'),
    lw('t6', _vl + 4, 't2'),                           # interval
    mult('t6', 't1'), mflo('t6'),                      # threshold = hz * interval
    slt('t7', 't5', 't6'),
    ('bne', 't7', 'zero', 'skip'), NOP,
    subu('t5', 't5', 't6'),
    slt('t7', 't5', 't6'),                             # still >= threshold: we fell behind,
    ('bne', 't7', 'zero', 'keep'), NOP,                # drop the backlog (no catch-up,
    addiu('t5', 'zero', 0),                            # like the stock vsync wait)
    ('label', 'keep'),
    sw('t5', _so(S_ACC), 't0'),
    ('label', 'step'),
    lq('a0', 0x00, 'sp'),
    jal(SCENE_STEP), NOP,
    lui('t0', 0x50),
    lw('t1', _so(S_SIMS), 't0'), addiu('t1', 't1', 1), sw('t1', _so(S_SIMS), 't0'),
    *_queue(save=True),
    ('b', 'out'), NOP,
    ('label', 'skip'),
    sw('t5', _so(S_ACC), 't0'),
    ('label', 'again'),
    lw('t1', _so(S_SKIPS), 't0'), addiu('t1', 't1', 1), sw('t1', _so(S_SKIPS), 't0'),
    *_queue(save=False),
    ('label', 'out'),
    lq('ra', 0x10, 'sp'), jr('ra'), addiu('sp', 'sp', 0x20),
])

_tx = (V.SLOTS + V.S_TX - 0x500000) & 0xFFFF
# Stereo = two whole main-loop iterations per vsync: pass 0 (sim gate + eye L), then
# pass 1 (eye R, never a sim step), and only then the vsync wait. Each eye goes through
# the game's own per-frame sequence (frameBegin kick/flip, pads, sound pump, render,
# post hook, GS sync) and is its own GS frame; the 2 MB packet buffer only ever holds
# one pass (a busy pass is ~1 MB). An earlier version kicked eye L from inside the
# render call and lost some HUD text in eye L.
RENDER_CODE = assemble(RENDER_CAVE, [
    lui('t0', 0x50),
    lw('t1', _so(S_STEREO), 't0'),
    ('beq', 't1', 'zero', 'go'), NOP,
    lw('t1', _so(S_PASS), 't0'),
    ('bne', 't1', 'zero', 'right'), NOP,
    lw('t1', _so(S_EYE_L), 't0'),
    ('b', 'set'), NOP,
    ('label', 'right'),
    lw('t1', _so(S_EYE_R), 't0'),
    ('label', 'set'),
    sw('t1', _tx, 't0'),
    ('label', 'go'),
    lw('t1', _so(S_RENDERS), 't0'), addiu('t1', 't1', 1), sw('t1', _so(S_RENDERS), 't0'),
    0x08000000 | ((RENDER_SCENE >> 2) & 0x03FFFFFF), NOP,       # j renderScene (tail call)
])

WAIT_CAVE = V.CAVE + 0x700
WAIT_CODE = assemble(WAIT_CAVE, [
    lui('t0', 0x50),
    lw('t1', _so(S_STEREO), 't0'),
    ('beq', 't1', 'zero', 'wait'), NOP,
    lw('t1', _so(S_PASS), 't0'),
    ('bne', 't1', 'zero', 'wait'), NOP,
    addiu('t1', 'zero', 1), sw('t1', _so(S_PASS), 't0'),      # eye L done: go again, no wait
    jr('ra'), NOP,
    ('label', 'wait'),
    sw('zero', _so(S_PASS), 't0'),
    0x08000000 | ((VSYNC_WAIT >> 2) & 0x03FFFFFF), NOP,         # j waitVsync (tail call)
])

PATCHES = [
    (0x0013339C, [jal(SCENE_STEP)], [jal(SIM_CAVE)]),
    (0x001333A4, [jal(RENDER_SCENE)], [jal(RENDER_CAVE)]),
    (0x00133114, [jal(VSYNC_WAIT)], [jal(WAIT_CAVE)]),
    (0x001D4CBC, [lw('v1', 8, 'v0')], [addiu('v1', 'zero', 1)]),
]


def _f(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def state(p):
    on = off = True
    for addr, orig, new in PATCHES:
        w = [p.read32(addr + 4 * i) for i in range(len(orig))]
        on &= w == new
        off &= w == orig
    if on:
        return 'on'
    if off:
        return 'off'
    raise RuntimeError('vr90 sites match neither the original nor the patched code; refusing')


def enable(p, hz=90, stereo=False, ipd=6.4):
    if stereo and V.state(p) != 'on':
        raise RuntimeError('--stereo writes the vrcam eye offset: run vrcam.py --on first')
    p.write_many([(B + S_HZ, hz), (B + S_LAST, p.read32(VSYNC_TOTAL)), (B + S_ACC, 0),
                  (B + S_STEREO, 1 if stereo else 0),
                  # vrcam's S_TX holds the NEGATED eye position
                  (B + S_EYE_L, _f(+ipd / 2)), (B + S_EYE_R, _f(-ipd / 2))])
    if state(p) == 'on':
        return
    # seed the saved queue state with the live values, in case a skip comes first
    for addr, o, kind in QUEUE:
        p.write32(B + o, {'w': p.read32, 'h': p.read16, 'b': p.read8}[kind](addr))
    for base, code in ((SIM_CAVE, SIM_CODE), (RENDER_CAVE, RENDER_CODE), (WAIT_CAVE, WAIT_CODE)):
        for i, w in enumerate(code):
            p.write32(base + 4 * i, w)
        if [p.read32(base + 4 * i) for i in range(len(code))] != code:
            raise RuntimeError(f'cave readback mismatch @ {base:08x}')
    for addr, orig, new in PATCHES:
        for i, w in enumerate(new):
            p.write32(addr + 4 * i, w)


def disable(p):
    for addr, orig, new in reversed(PATCHES):
        for i, w in enumerate(orig):
            p.write32(addr + 4 * i, w)
    p.write32(B + S_STEREO, 0)


def counters(p):
    return {k: p.read32(a) for k, a in (('vsync', VSYNC_TOTAL), ('sims', B + S_SIMS),
                                        ('renders', B + S_RENDERS), ('skips', B + S_SKIPS),
                                        ('frames', 0x00499830))}


def measure(p, secs=5.0):
    a, t0 = counters(p), time.perf_counter()
    time.sleep(secs)
    b, dt = counters(p), time.perf_counter() - t0
    rate = {k: (b[k] - a[k]) / dt for k in a}
    rate['interval'] = p.read32(INTERVAL)
    return rate


def selftest():
    ok = True
    data = open(V.ELF, 'rb').read()
    for addr, orig, new in PATCHES:
        got = [struct.unpack_from('<I', data, addr + 4 * i - V.ELF_DELTA)[0] for i in range(len(orig))]
        good = got == orig and len(new) == len(orig)
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {addr:08x} {got[0]:08x}")
    good = (SIM_CAVE + 4 * len(SIM_CODE) <= RENDER_CAVE
            and V.CAVE + 4 * len(V.CAVE_CODE) <= SIM_CAVE
            and RENDER_CAVE + 4 * len(RENDER_CODE) <= WAIT_CAVE
            and WAIT_CAVE + 4 * len(WAIT_CODE) < V.SLOTS
            and V.SLOTS + V.S_POSE_USED + 4 <= B and B + S_SKIPS + 4 < 0x500000)
    ok &= good
    print(f"{'ok ' if good else 'BAD'} layout: sim {len(SIM_CODE)}w, render {len(RENDER_CODE)}w, "
          f"wait {len(WAIT_CODE)}w, slots @ {B:08x}")
    # known encodings
    for got, want, what in ((lw('v1', 8, 'v0'), 0x8C430008, 'lw v1,8(v0)'),
                            (sq('ra', 0x10, 'sp'), 0x7FBF0010, 'sq ra,0x10(sp)'),
                            (mult('t6', 't1'), 0x01C90018, 'mult t6,t1'),
                            (jr('ra'), 0x03E00008, 'jr ra'),
                            (_abs(0x002C9B70), (0x2D, 0x9B70), 'hi/lo with carry')):
        good = got == want
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {what}")
    print('PASS' if ok else 'FAIL')
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest', action='store_true')
    g.add_argument('--on', action='store_true')
    g.add_argument('--off', action='store_true')
    g.add_argument('--measure', nargs='?', const=5.0, type=float)
    ap.add_argument('--hz', type=int, default=90)
    ap.add_argument('--stereo', action='store_true')
    ap.add_argument('--ipd', type=float, default=6.4, help='game units (~cm)')
    ap.add_argument('--port', type=int, default=P.DEFAULT_SLOT)
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(0 if selftest() else 1)
    with P.Pine(port=a.port) as p:
        if a.on:
            enable(p, a.hz, a.stereo, a.ipd)
            print(f'vr90 ON: hz {a.hz}, {"stereo" if a.stereo else "mono"}')
        elif a.off:
            disable(p)
            print('vr90 OFF')
        else:
            for k, v in measure(p, a.measure).items():
                print(f'{k:9s} {v:7.2f}')


if __name__ == '__main__':
    main()
