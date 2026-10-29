"""Prove the hunt finds a planted tracker variable and rejects the decoys.

Builds synthetic savestates -- real zips with a real 32 MB eeMemory.bin -- in
which we know exactly where the answer is, then runs the actual hunt against
them. The interesting part is not that it finds the planted value; it is that
the frame counter and the wall clock, which climb monotonically as snapshots
are taken, do NOT come back as hits.

    py hunt_selftest.py [workdir]
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hunt
import snapshot

# Where we plant things. TRACKER_F32 sits inside the camera state struct so the
# run also exercises snapshot.describe()'s region annotation.
TRACKER_F32 = 0x0026B7A0
TRACKER_I16 = 0x00200000
COUNTER_I32 = 0x00300000          # decoy: frame counter, climbs with time
CLOCK_F32 = 0x00300010            # decoy: seconds elapsed, climbs with time
NOISE_AT = 0x00400000
NOISE_LEN = 1 << 20

# Deliberately NOT in ascending order, and 0.0 is visited twice -- exactly what
# snap.py will produce, and what the repeat check needs.
COMMANDS = [0.0, -0.8, 0.4, -0.4, 0.8, 0.0, -0.6, 0.6]


def build_dump(path, command, frame, seconds, rng):
    ram = np.zeros(snapshot.EE_SIZE, dtype=np.uint8)

    # plausible junk so the scan has something to reject
    ram[NOISE_AT:NOISE_AT + NOISE_LEN] = rng.integers(0, 256, NOISE_LEN, dtype=np.uint8)

    def poke(addr, raw):
        ram[addr:addr + len(raw)] = np.frombuffer(raw, dtype=np.uint8)

    # the planted answers: a linear, mirrored response like the real one
    poke(TRACKER_F32, struct.pack('<f', -255.78 * command + 3498.79))
    poke(TRACKER_I16, struct.pack('<h', int(round(-120 * command + 160))))
    # the decoys
    poke(COUNTER_I32, struct.pack('<i', frame))
    poke(CLOCK_F32, struct.pack('<f', seconds))

    ee = path + '.eeMemory.tmp'
    ram.tofile(ee)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(ee, snapshot.EE_MEMBER)
        z.writestr('PCSX2 Savestate Version.id', b'\x00' * 4)
    os.remove(ee)


def main():
    workdir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='hunt_selftest_')
    os.makedirs(workdir, exist_ok=True)
    rng = np.random.default_rng(20260913)
    print(f"hunt_selftest: building {len(COMMANDS)} synthetic savestates in {workdir}")

    snaps = []
    for i, cmd in enumerate(COMMANDS):
        p = os.path.join(workdir, f'slot{i}.p2s')
        build_dump(p, cmd, frame=1000 + 137 * i, seconds=12.5 + 4.25 * i, rng=rng)
        snaps.append({"label": f"dx={cmd:+.2f}", "command": cmd, "path": p, "index": i})
        print(f"  {i + 1}/{len(COMMANDS)}", end='\r', flush=True)

    manifest = os.path.join(workdir, 'manifest.json')
    with open(manifest, 'w', encoding='utf-8') as f:
        json.dump({"axis": "dx", "snapshots": snaps}, f, indent=1)

    out = os.path.join(workdir, 'candidates.json')
    argv = sys.argv
    sys.argv = ['hunt.py', manifest, '--out', out, '--top', '10']
    try:
        hunt.main()
    finally:
        sys.argv = argv

    with open(out, encoding='utf-8') as f:
        cands = json.load(f)['candidates']
    found = {c['addr']: c for c in cands}

    checks, failures = 0, []

    def check(label, ok, detail=''):
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f'{label}{(" -- " + detail) if detail else ""}')

    check('planted f32 found', TRACKER_F32 in found,
          f'0x{TRACKER_F32:08X} missing from {len(cands)} candidates')
    check('planted i16 found', TRACKER_I16 in found,
          f'0x{TRACKER_I16:08X} missing from {len(cands)} candidates')
    check('frame counter rejected', COUNTER_I32 not in found,
          'a monotonic counter survived -- the shuffle/repeat defence is not working')
    check('wall clock rejected', CLOCK_F32 not in found,
          'a monotonic timer survived -- the shuffle/repeat defence is not working')

    if TRACKER_F32 in found:
        c = found[TRACKER_F32]
        check('f32 encoding', c['encoding'] == 'f32', c['encoding'])
        check('f32 slope', abs(c['slope'] - (-255.78)) < 0.5, f"slope={c['slope']:.3f}")
        check('f32 region annotated', bool(c['region']), 'no region label')
        check('f32 correlation', abs(c['r']) > 0.999, f"r={c['r']:.5f}")

    print(f"\n  candidates returned: {len(cands)}")
    for f_ in failures:
        print(f'  FAIL  {f_}')
    print(f"hunt_selftest: {checks - len(failures)}/{checks} checks passed")

    if len(sys.argv) <= 1:
        shutil.rmtree(workdir, ignore_errors=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
