"""Capture a sweep: park the synthetic head, savestate, repeat.

Drives the running game through a set of known head positions and takes a PCSX2
savestate at each, so hunt.py can diff them offline and find where the tracker's
output lives in EE RAM.

    py snap.py --axis dx --out sweeps/dx
    py snap.py --axis dy --out sweeps/dy --settle 3.0

Prerequisites, all of which are checked before anything is captured:
  * pump.py already running and owning the virtual camera
  * PCSX2 running the game, sitting somewhere the tracker is live
    (SENSOR ADJUSTMENT, or in a stage)
  * PINE enabled -- PCSX2.ini [EmuCore] EnablePINE = true, PINESlot = 28011

WHY THE ORDER IS SHUFFLED
-------------------------
Visiting positions in ascending order makes every frame counter, timer and
progress bar in 32 MB of RAM correlate perfectly with the commanded position,
and the hunt drowns. So the visit order is shuffled until it barely correlates
with time, and at least one position is visited twice so hunt.py can demand
that a candidate return to its earlier value. See hunt.py's header.

The optical reading from probe.py is recorded next to each snapshot. That makes
the game's OWN tracker estimate available as the correlation target, which beats
the commanded value whenever the tracker is non-linear -- and the dy axis is
known to be.
"""
import argparse
import json
import os
import random
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RE_DIR = os.path.dirname(HERE)
SYNTH = os.path.normpath(os.path.join(RE_DIR, '..', 'synth'))
REPO = os.path.normpath(os.path.join(RE_DIR, '..', '..'))
SSTATES = os.path.join(REPO, 'PCSX2', 'sstates')

sys.path.insert(0, HERE)
sys.path.insert(0, SYNTH)
import pine as P

CONTROL = os.path.join(SYNTH, 'control.json')

DEFAULT_VALUES = [-0.8, -0.4, 0.0, 0.4, 0.8]


def set_control(**kw):
    """Update control.json the way setctl.py does -- no BOM, pump hot-reloads it."""
    cur = {}
    if os.path.exists(CONTROL):
        try:
            with open(CONTROL, encoding='utf-8-sig') as f:
                cur = json.load(f)
        except Exception:
            cur = {}
    cur.update(kw)
    with open(CONTROL, 'w', encoding='utf-8') as f:
        json.dump(cur, f)
    return cur


def plan_order(values, repeats, seed, max_time_corr=0.35, tries=4000):
    """A visit order that does not look like the passage of time.

    Returns a list of commanded values including `repeats` extra visits to the
    neutral-most value, shuffled until |corr(position_in_sequence, value)| is
    small. Without this, monotonic counters are indistinguishable from the
    tracker output.
    """
    neutral = min(values, key=abs)
    seq = list(values) + [neutral] * repeats
    rng = random.Random(seed)
    best, best_r = None, 2.0
    idx = np.arange(len(seq), dtype=float)
    for _ in range(tries):
        rng.shuffle(seq)
        r = abs(float(np.corrcoef(idx, np.asarray(seq, dtype=float))[0, 1]))
        if r < best_r:
            best, best_r = list(seq), r
        if r <= max_time_corr:
            return list(seq), r
    return best, best_r


def state_snapshot(d):
    """{path: mtime} for every savestate currently on disk."""
    out = {}
    if not os.path.isdir(d):
        return out
    for n in os.listdir(d):
        if n.lower().endswith('.p2s'):
            p = os.path.join(d, n)
            try:
                out[p] = os.path.getmtime(p)
            except OSError:
                pass
    return out


def wait_for_state(d, before, timeout=25.0, quiet=0.6):
    """Block until a .p2s is written, then until it stops growing.

    MsgSaveState is fire-and-forget -- PCSX2 queues it onto the CPU thread and
    replies immediately -- so the file is not on disk when save_state() returns,
    and reading it too early yields a truncated zip.
    """
    deadline = time.time() + timeout
    target = None
    while time.time() < deadline:
        now = state_snapshot(d)
        changed = [p for p, m in now.items() if before.get(p) is None or m > before[p]]
        if changed:
            target = max(changed, key=lambda p: now[p])
            break
        time.sleep(0.1)
    if target is None:
        raise TimeoutError(f"no new savestate appeared in {d} within {timeout}s")

    last_size, stable_since = -1, time.time()
    while time.time() < deadline:
        try:
            size = os.path.getsize(target)
        except OSError:
            size = -1
        if size == last_size and size > 0:
            if time.time() - stable_since >= quiet:
                return target
        else:
            last_size, stable_since = size, time.time()
        time.sleep(0.1)
    raise TimeoutError(f"{target} never settled to a stable size")


def read_dot(probe, panel=None):
    """Where the game thinks the head is, read off its own screen. None if unclear.

    Delegates to probe.tracker_dot, which knows how to reject the calibration
    ring -- whose thin arcs otherwise pass a naive "is it solid?" test and get
    reported as the tracker's estimate.
    """
    try:
        img, meta = probe.grab(with_meta=True)
    except Exception as e:
        print(f"    (probe: {e})")
        return None
    if panel is None:
        o = probe.load_oracle().get('panel')
        if o:
            w = float(meta.get('width') or img.shape[1])
            h = float(meta.get('height') or img.shape[0])
            panel = (o['fx0'] * w, o['fx1'] * w, o['fy0'] * h, o['fy1'] * h)
    c = probe.tracker_dot(img, panel)
    if not c:
        return None
    return {"x": c['x'], "y": c['y'], "area": c['area'], "fill": c['fill']}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--axis', choices=['dx', 'dy'], default='dx')
    ap.add_argument('--values', default=','.join(str(v) for v in DEFAULT_VALUES),
                    help='commanded positions to visit')
    ap.add_argument('--repeats', type=int, default=2,
                    help='extra visits to the neutral position, for the repeat check')
    ap.add_argument('--seed', type=int, default=911)
    ap.add_argument('--settle', type=float, default=4.0,
                    help='seconds to let the tracker converge after moving the head. '
                         'MEASURED, not guessed: at 2.5 s the tracker had not caught up '
                         'and a dx=-0.8 sample read back 135 px away from the target, '
                         'looking exactly like a tracker that had lost lock. At 4.0 s '
                         'the same sweep correlates at r=-0.998. Do not lower it.')
    ap.add_argument('--slot', type=int, default=9,
                    help='savestate slot to reuse. WARNING: overwrites that slot')
    ap.add_argument('--out', required=True, help='directory for the sweep')
    ap.add_argument('--port', type=int, default=P.DEFAULT_SLOT)
    ap.add_argument('--sstates', default=SSTATES)
    ap.add_argument('--no-probe', action='store_true',
                    help='skip the optical reading (faster, but loses the dot data)')
    args = ap.parse_args()

    values = [float(v) for v in args.values.split(',')]
    order, time_r = plan_order(values, args.repeats, args.seed)
    other = 'dy' if args.axis == 'dx' else 'dx'

    print(f"snap: axis={args.axis}  {len(order)} snapshots  slot={args.slot}")
    print(f"      order: {', '.join(f'{v:+.2f}' for v in order)}")
    print(f"      command/time correlation r={time_r:.3f}", end='')
    print('  -- good' if time_r <= 0.4 else '  -- HIGH, counters may masquerade as hits')

    probe = None
    if not args.no_probe:
        try:
            import probe as probe_mod
            probe = probe_mod
        except Exception as e:
            print(f"      (probe unavailable: {e}; continuing without optical readings)")

    with P.Pine(port=args.port) as p:
        status = p.status()
        if status != P.STATUS_RUNNING:
            raise SystemExit(f"PCSX2 is not running a game (status={status}). "
                             "Boot the game and get the tracker on screen first.")
        print(f"      PINE: {p.version()} / {p.title()} [{p.game_id()}]")

        os.makedirs(args.out, exist_ok=True)
        snaps = []
        for i, cmd in enumerate(order):
            set_control(**{args.axis: cmd, other: 0.0,
                           'anim': 'none', 'jitter': 0.03, 'jitter_hz': 3.0})
            time.sleep(args.settle)

            dot = read_dot(probe) if probe else None

            before = state_snapshot(args.sstates)
            p.save_state(args.slot)
            src = wait_for_state(args.sstates, before)
            dst = os.path.join(args.out, f"snap{i:02d}.p2s")
            shutil.copy2(src, dst)

            rec = {"index": i, "label": f"{args.axis}={cmd:+.2f}", "command": cmd,
                   "path": os.path.basename(dst), "t": time.time()}
            if dot:
                rec["dot_x"], rec["dot_y"] = dot["x"], dot["y"]
            snaps.append(rec)
            dotstr = (f"  dot=({dot['x']:7.1f},{dot['y']:7.1f})" if dot
                      else "  dot=?")
            print(f"  [{i + 1:2d}/{len(order)}] {args.axis}={cmd:+.2f}{dotstr}"
                  f"  -> {os.path.basename(dst)}")

    man = {"axis": args.axis, "values": values, "repeats": args.repeats,
           "seed": args.seed, "settle": args.settle, "time_corr": time_r,
           "snapshots": snaps}
    mpath = os.path.join(args.out, 'manifest.json')
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump(man, f, indent=1)
    print(f"\nwrote {mpath}")

    if any('dot_x' in s for s in snaps):
        key = 'dot_x' if args.axis == 'dx' else 'dot_y'
        xs = [s['command'] for s in snaps if key in s]
        ds = [s[key] for s in snaps if key in s]
        if len(set(ds)) > 1:
            r = float(np.corrcoef(xs, ds)[0, 1])
            print(f"optical check: {key} vs {args.axis} r={r:+.4f} over "
                  f"{max(ds) - min(ds):.1f} px")
            if abs(r) < 0.8:
                print("  WARNING: the game's dot barely followed the commanded head. "
                      "The memory hunt will find nothing until this is fixed -- "
                      "check the feed is live and the tracker is on screen.")
        else:
            print("optical check: the dot never moved. Fix that before hunting.")
    print(f"\nnext: py hunt.py {os.path.join(args.out, 'manifest.json')} "
          f"--out {os.path.join(args.out, 'candidates.json')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
