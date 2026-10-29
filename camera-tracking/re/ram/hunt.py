"""Find the EE address that holds the game's tracked head position.

Takes a set of savestates captured while the synthetic head sat at known
positions, and looks for any value in the PS2's 32 MB of RAM that tracks the
commanded position across all of them.

    py hunt.py sweeps/dx/manifest.json --top 40

THE DECOY PROBLEM, and why snap.py shuffles the command order
-------------------------------------------------------------
A frame counter, a timer, an RNG feeding a ring buffer -- all of these climb
steadily as snapshots are taken. If the sweep visits dx in order
(-0.8, -0.4, 0, +0.4, +0.8) then every such counter correlates with dx at
r = 1.000 and buries the real hit under thousands of false ones.

Two defences, and the hunt leans on both:

  1. snap.py visits the commanded positions in a SHUFFLED order, so "rises with
     time" and "rises with dx" stop being the same shape.
  2. the sweep revisits some positions more than once, and --repeat-tol then
     demands that a candidate return to its earlier value when the command
     returns to an earlier position. A counter never comes back down; the
     tracker's output must.

Encodings scanned: float32 and int32 on 4-byte alignment, int16 on 2-byte.
That covers how a 2003 PS2 title would plausibly store a coordinate. EE RAM is
mirrored at 0x00000000, so a byte offset into eeMemory.bin is the same number
PINE wants as an address.
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snapshot

# element counts per pass; 1M elements x 8 dumps x 8 B = 64 MB per working array
CHUNK = 1 << 20

ENCODINGS = {
    'f32': np.dtype('<f4'),
    'i32': np.dtype('<i4'),
    'i16': np.dtype('<i2'),
    'u16': np.dtype('<u2'),
}


def load_manifest(path):
    with open(path, encoding='utf-8-sig') as f:
        man = json.load(f)
    snaps = man['snapshots']
    if len(snaps) < 4:
        raise SystemExit(f"need at least 4 snapshots to fit anything, got {len(snaps)}")
    base = os.path.dirname(os.path.abspath(path))
    for s in snaps:
        if not os.path.isabs(s['path']):
            s['path'] = os.path.normpath(os.path.join(base, s['path']))
    return man, snaps


def scan_encoding(paths, x, dtype, lo_off, hi_off, min_r, min_range,
                  max_abs, verbose=True):
    """Correlate every aligned value in the dumps against the command vector."""
    itemsize = dtype.itemsize
    maps = [np.memmap(p, dtype=dtype, mode='r') for p in paths]
    n = len(maps)
    total = maps[0].size
    start_el = lo_off // itemsize
    stop_el = min(hi_off // itemsize, total)

    xc = x - x.mean()
    xnorm = float(np.sqrt((xc * xc).sum()))
    if xnorm == 0:
        raise SystemExit("every snapshot used the same command -- nothing to correlate")
    is_float = dtype.kind == 'f'

    cand_idx, cand_r, cand_vals = [], [], []
    for s in range(start_el, stop_el, CHUNK):
        e = min(stop_el, s + CHUNK)
        block = np.empty((n, e - s), dtype=np.float64)
        # Random bytes viewed as float32 are full of NaN and Inf. We filter them
        # explicitly a few lines down, so silence the cast warning rather than let
        # it fire millions of times and bury the progress line.
        with np.errstate(invalid='ignore', over='ignore'):
            for i, mm in enumerate(maps):
                block[i] = mm[s:e]

        if is_float:
            good = np.isfinite(block).all(axis=0)
            np.nan_to_num(block, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
            good &= (np.abs(block) <= max_abs).all(axis=0)
        else:
            good = np.ones(e - s, dtype=bool)

        vmin = block.min(axis=0)
        vmax = block.max(axis=0)
        rng = vmax - vmin
        good &= rng >= min_range

        if not good.any():
            continue

        centered = block - block.mean(axis=0)
        sxv = (xc[:, None] * centered).sum(axis=0)
        svv = (centered * centered).sum(axis=0)
        denom = xnorm * np.sqrt(svv)
        with np.errstate(invalid='ignore', divide='ignore'):
            r = np.where(denom > 0, sxv / denom, 0.0)
        good &= np.abs(r) >= min_r

        hit = np.flatnonzero(good)
        if hit.size:
            cand_idx.append(hit + s)
            cand_r.append(r[hit])
            cand_vals.append(block[:, hit].T.copy())
        if verbose and ((s - start_el) // CHUNK) % 8 == 0:
            done = (s - start_el) / max(1, stop_el - start_el)
            print(f"    {done * 100:5.1f}%  candidates so far: "
                  f"{sum(c.size for c in cand_idx)}".ljust(58), end='\r', flush=True)

    if verbose:
        print('\r' + ' ' * 78 + '\r', end='', flush=True)
    if not cand_idx:
        return []
    idx = np.concatenate(cand_idx)
    rs = np.concatenate(cand_r)
    vals = np.concatenate(cand_vals, axis=0)
    return [{"offset": int(i) * itemsize, "r": float(rr), "values": v.tolist()}
            for i, rr, v in zip(idx, rs, vals)]


def repeat_filter(cands, commands, tol):
    """Drop anything that does not come back when the command comes back.

    Groups snapshots by commanded position; a genuine tracker output must agree
    with itself within `tol` of its own full range at every repeated position.
    This is what kills monotonic counters that survived the shuffle by luck.
    """
    groups = {}
    for i, c in enumerate(commands):
        groups.setdefault(round(float(c), 6), []).append(i)
    repeated = [g for g in groups.values() if len(g) > 1]
    if not repeated:
        return cands, 0

    kept = []
    for cand in cands:
        v = np.asarray(cand['values'], dtype=np.float64)
        span = v.max() - v.min()
        if span <= 0:
            continue
        worst = max(float(v[g].max() - v[g].min()) for g in repeated)
        if worst <= tol * span:
            cand['repeat_spread'] = round(worst / span, 4)
            kept.append(cand)
    return kept, len(repeated)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('manifest')
    ap.add_argument('--encodings', default='f32,i32,i16,u16')
    ap.add_argument('--min-r', type=float, default=0.995,
                    help='minimum |Pearson r| against the commanded position')
    ap.add_argument('--min-range', type=float, default=2.0,
                    help='value must move at least this much across the sweep')
    ap.add_argument('--max-abs', type=float, default=1e6,
                    help='reject float32 values bigger than this as misread bytes')
    ap.add_argument('--repeat-tol', type=float, default=0.15,
                    help='at a repeated command, allow this fraction of the '
                         'full range as spread (0 disables the check)')
    ap.add_argument('--lo', type=lambda s: int(s, 0), default=0x00000000)
    ap.add_argument('--hi', type=lambda s: int(s, 0), default=snapshot.EE_SIZE)
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--against', choices=['command', 'dot'], default='command',
                    help="what to correlate against: the position we commanded, or "
                         "the dot the game's own tracker drew (recorded by snap.py). "
                         "'dot' is better wherever the tracker is non-linear, which "
                         "the dy axis measurably is.")
    ap.add_argument('--out', default=None, help='write full candidate list as JSON')
    args = ap.parse_args()

    man, snaps = load_manifest(args.manifest)
    # repeat grouping always keys off the COMMANDED position: "did it come back
    # when we put the head back?" is a question about the command, not the reading
    commands = [float(s['command']) for s in snaps]

    if args.against == 'dot':
        key = 'dot_x' if man.get('axis', 'dx') == 'dx' else 'dot_y'
        missing = [s['label'] for s in snaps if key not in s]
        if missing:
            raise SystemExit(f"--against dot needs {key} on every snapshot; missing "
                             f"for {missing[:4]}. Re-run snap.py without --no-probe.")
        target = [float(s[key]) for s in snaps]
        print(f"hunt: correlating against the game's own {key}")
    else:
        target = commands
    x = np.asarray(target, dtype=np.float64)

    print(f"hunt: axis={man.get('axis', '?')}  {len(snaps)} snapshots")
    print(f"      commands (in capture order): "
          f"{', '.join(f'{c:+.2f}' for c in commands)}")
    order_r = abs(np.corrcoef(np.arange(len(x)), x)[0, 1]) if len(set(target)) > 1 else 1.0
    if order_r > 0.6:
        print(f"      WARNING: command order correlates with time at r={order_r:.3f}. "
              f"Counters and timers will masquerade as hits. Re-capture with a "
              f"shuffled order (snap.py does this by default).")
    else:
        print(f"      command/time correlation r={order_r:.3f} -- counters will not "
              f"look like the tracker. Good.")

    paths = []
    for s in snaps:
        paths.append(snapshot.extract_ee(s['path']))
    print(f"      EE dumps extracted: {len(paths)}")

    all_cands = []
    for name in args.encodings.split(','):
        name = name.strip()
        if name not in ENCODINGS:
            raise SystemExit(f"unknown encoding {name!r}; pick from {list(ENCODINGS)}")
        print(f"  scanning {name} ...")
        cands = scan_encoding(paths, x, ENCODINGS[name], args.lo, args.hi,
                              args.min_r, args.min_range, args.max_abs)
        print(f"    {name}: {len(cands)} raw candidates")
        if args.repeat_tol > 0:
            cands, ngroups = repeat_filter(cands, commands, args.repeat_tol)
            if ngroups:
                print(f"    {name}: {len(cands)} survive the repeat check "
                      f"({ngroups} repeated position(s))")
            else:
                print(f"    {name}: no repeated positions in this sweep -- "
                      f"repeat check skipped, decoys NOT filtered")
        for c in cands:
            c['encoding'] = name
        all_cands.extend(cands)

    for c in all_cands:
        c['addr'] = snapshot.offset_to_addr(c['offset'])
        c['region'] = snapshot.describe(c['addr'])
        v = np.asarray(c['values'])
        c['span'] = float(v.max() - v.min())
        # least-squares slope of value against command: the transfer function
        c['slope'] = float(np.polyfit(x, v, 1)[0])

    # a hit inside a known camera region beats a slightly-better-correlated
    # hit in anonymous heap, so region presence sorts first
    all_cands.sort(key=lambda c: (bool(c['region']), abs(c['r']), c['span']),
                   reverse=True)

    print(f"\n=== {len(all_cands)} candidates, top {min(args.top, len(all_cands))} ===")
    if not all_cands:
        print("  nothing survived. Loosen --min-r, lower --min-range, or check that "
              "the sweep actually moved the tracker (probe.py should have seen the "
              "red dot move between snapshots).")
    for c in all_cands[:args.top]:
        vals = ' '.join(f'{v:>10.3f}' for v in c['values'])
        print(f"  0x{c['addr']:08X}  {c['encoding']:>3s}  r={c['r']:+.5f}  "
              f"slope={c['slope']:+.3f}  span={c['span']:.3f}")
        print(f"              values: {vals}")
        if c['region']:
            print(f"              in: {c['region']}")

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump({"manifest": os.path.abspath(args.manifest),
                       "axis": man.get('axis'),
                       "commands": commands,
                       "candidates": all_cands}, f, indent=1)
        print(f"\nwrote {len(all_cands)} candidates -> {args.out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
