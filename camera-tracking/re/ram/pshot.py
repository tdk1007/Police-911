"""Grab the current frame as a PNG via a PINE savestate (no window focus needed).

A .p2s is a zip holding Screenshot.png from the same frame. Slot 7 is scratch.

    py pshot.py out.png [--slot 7] [--port 28011]
"""
import argparse
import glob
import os
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pine as P


def state_path(slot, sstates):
    hits = glob.glob(os.path.join(sstates, f'*.{slot:02d}.p2s'))
    return hits[0] if hits else None


def shot(p, out, slot=7, sstates=None, timeout=15.0):
    old = state_path(slot, sstates)
    t0 = os.path.getmtime(old) if old else 0.0
    p.save_state(slot)
    end = time.time() + timeout
    while time.time() < end:
        f = state_path(slot, sstates)
        if f and os.path.getmtime(f) > t0:
            time.sleep(0.3)                      # let the writer finish
            try:
                with zipfile.ZipFile(f) as z:
                    open(out, 'wb').write(z.read('Screenshot.png'))
                return out
            except (zipfile.BadZipFile, KeyError, PermissionError):
                pass
        time.sleep(0.2)
    raise TimeoutError('savestate never appeared')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--slot', type=int, default=7)
    ap.add_argument('--port', type=int, default=P.DEFAULT_SLOT)
    ap.add_argument('--sstates', default=os.path.join(HERE, '..', '..', '..', 'pcsx2-vr', 'bin', 'sstates'))
    a = ap.parse_args()
    with P.Pine(port=a.port) as p:
        print(shot(p, a.out, a.slot, a.sstates))


if __name__ == '__main__':
    main()
