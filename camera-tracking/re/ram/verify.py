"""Confirm a candidate by WRITING it and watching the game's own dot move.

Correlation only proves a value moves when the head moves. It cannot tell the
tracker's output from anything computed downstream of it, from a copy, or from a
coincidence. Writing settles it: if forcing the address makes the red dot move,
the game is reading that value.

    py verify.py sweeps/dx/candidates.json --axis dx
    py verify.py --addr 0x0042F460 --enc i32 --axis dx

Values are HAMMERED, not written once. The game recomputes its tracker output
every frame from the camera image, so a single write is overwritten before the
next frame is drawn. Writing continuously at a few hundred hertz wins the race
often enough to see the dot move -- and if it does not, that is itself the
finding: the address is downstream of a writer we will have to NOP.

The feed is parked still during the test so the only thing that can move the dot
is us.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SYNTH = os.path.normpath(os.path.join(HERE, '..', '..', 'synth'))
sys.path.insert(0, HERE)
sys.path.insert(0, SYNTH)

import pine as P
import probe
import snapshot

SIZES = {'i16': 2, 'u16': 2, 'i32': 4, 'f32': 4}


def panel_from_oracle(img, meta):
    o = probe.load_oracle().get('panel')
    if not o:
        return None
    w = float(meta.get('width') or img.shape[1])
    h = float(meta.get('height') or img.shape[0])
    return (o['fx0'] * w, o['fx1'] * w, o['fy0'] * h, o['fy1'] * h)


def read_dot(axis):
    img, meta = probe.grab(with_meta=True)
    c = probe.tracker_dot(img, panel_from_oracle(img, meta))
    if not c:
        return None
    return c['x'] if axis == 'dx' else c['y']


def hammer(p, addr, value, enc, seconds):
    """Write the same value as fast as the socket allows.

    No sleep between writes. An earlier version paced itself with
    time.sleep(1/400), which on Windows rounds up to the ~15 ms timer
    granularity -- so it actually wrote about 66 times a second, roughly once per
    game frame, and had almost no chance of landing between the game's own write
    and its read. The PINE round trip is the only rate limit worth having here;
    it gives thousands of writes per second.
    """
    size = SIZES[enc]
    mask = (1 << (size * 8)) - 1
    end = time.time() + seconds
    n = 0
    if enc == 'f32':
        while time.time() < end:
            p.write_f32(addr, float(value))
            n += 1
    else:
        v = int(value) & mask
        while time.time() < end:
            p.write(addr, v, size)
            n += 1
    return n


def test_address(p, addr, enc, axis, targets, hold=1.6):
    """Force the address through `targets`; report where the dot went."""
    size = SIZES[enc]
    original = p.read_f32(addr) if enc == 'f32' else p.read(addr, size)
    seen = []
    try:
        for t in targets:
            hammer(p, addr, t, enc, hold)
            d = read_dot(axis)
            seen.append((t, d))
    finally:
        if enc == 'f32':
            p.write_f32(addr, original)
        else:
            p.write(addr, int(original), size)
    return original, seen


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('candidates', nargs='?', help='candidates.json from hunt.py')
    ap.add_argument('--addr', type=lambda s: int(s, 0), help='test one address instead')
    ap.add_argument('--enc', default='i32', choices=list(SIZES))
    ap.add_argument('--axis', choices=['dx', 'dy'], default='dx')
    ap.add_argument('--hold', type=float, default=1.6)
    ap.add_argument('--max', type=int, default=10, help='how many clusters to test')
    ap.add_argument('--port', type=int, default=P.DEFAULT_SLOT)
    args = ap.parse_args()

    if args.addr is not None:
        tests = [(args.addr, args.enc, None)]
    else:
        if not args.candidates:
            raise SystemExit('give a candidates.json, or --addr')
        with open(args.candidates, encoding='utf-8-sig') as f:
            data = json.load(f)
        cands = data['candidates']
        # one representative per cluster: highest |r|, preferring wider encodings
        by_addr = {}
        for c in cands:
            k = c['addr']
            if k not in by_addr or abs(c['r']) > abs(by_addr[k]['r']):
                by_addr[k] = c
        addrs = sorted(by_addr)
        clusters, cur = [], [addrs[0]]
        for a in addrs[1:]:
            if a - cur[-1] <= 0x40:
                cur.append(a)
            else:
                clusters.append(cur)
                cur = [a]
        clusters.append(cur)
        tests = []
        for g in clusters:
            best = max((by_addr[a] for a in g), key=lambda c: abs(c['r']))
            tests.append((best['addr'], best['encoding'], best))
        tests.sort(key=lambda t: -abs(t[2]['r']))
        tests = tests[:args.max]

    print(f"verify: {len(tests)} address(es), axis={args.axis}, "
          f"hold={args.hold}s each\n")

    # park the feed: nothing but our writes may move the dot
    control = os.path.join(SYNTH, 'control.json')
    cur = json.load(open(control, encoding='utf-8-sig'))
    saved = dict(cur)
    cur.update({'anim': 'none', 'dx': 0.0, 'dy': 0.0, 'jitter': 0.02})
    json.dump(cur, open(control, 'w', encoding='utf-8'))
    time.sleep(4.0)

    results = []
    try:
        with P.Pine(port=args.port) as p:
            if p.status() != P.STATUS_RUNNING:
                raise SystemExit('PCSX2 is not running a game')
            base = read_dot(args.axis)
            print(f"baseline dot_{args.axis[-1]} = {base}\n")

            for addr, enc, c in tests:
                cur_val = p.read_f32(addr) if enc == 'f32' else p.read(addr, SIZES[enc])
                # Stay inside the range the variable PRODUCED during the sweep.
                # Writing arbitrary offsets is how this crashed PCSX2: a value
                # that is really a pointer or an index does not tolerate +40.
                if c and c.get('values'):
                    lo, hi = min(c['values']), max(c['values'])
                else:
                    lo, hi = cur_val, cur_val
                targets = [cur_val, lo, hi, cur_val]
                region = snapshot.describe(addr)
                print(f"0x{addr:08X} {enc:>3s}  now={cur_val}  "
                      f"{'(' + region + ')' if region else ''}")
                orig, seen = test_address(p, addr, enc, args.axis, targets, args.hold)
                xs = [t for t, d in seen if d is not None]
                ds = [d for t, d in seen if d is not None]
                for t, d in seen:
                    print(f"      wrote {t:>12.1f} -> dot {d if d is None else round(d,1)}")
                moved = (max(ds) - min(ds)) if len(ds) > 1 else 0.0
                r = float(np.corrcoef(xs, ds)[0, 1]) if len(set(ds)) > 1 else 0.0
                verdict = ('MOVES THE DOT' if moved > 3.0 else 'no effect')
                print(f"      -> dot moved {moved:.1f} px, r={r:+.3f}   {verdict}\n")
                results.append((addr, enc, moved, r))
    finally:
        json.dump(saved, open(control, 'w', encoding='utf-8'))

    print("=" * 62)
    hits = [x for x in results if x[2] > 3.0]
    if hits:
        for addr, enc, moved, r in sorted(hits, key=lambda x: -x[2]):
            print(f"  0x{addr:08X} {enc}  moved the dot {moved:.1f} px (r={r:+.3f})")
        print("\nThese are downstream of the camera image and upstream of the display.")
        print("Next: find the instruction that writes them (PCSX2 debugger, write")
        print("breakpoint) and NOP it, so our writes are not overwritten every frame.")
    else:
        print("  No address moved the dot.")
        print("  Most likely the game recomputes these every frame faster than we can")
        print("  write. That does NOT mean they are wrong -- it means the writer has to")
        print("  be NOPed first. Pick the highest-correlation candidate and set a write")
        print("  breakpoint on it in the PCSX2 debugger.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
