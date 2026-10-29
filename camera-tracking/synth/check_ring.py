"""Is the game's head marker sitting inside its calibration ring?

That is the game's own definition of "the player is standing in the right place",
so it is the pass/fail for our neutral calibration.

    py check_ring.py            # pass/fail against the stored oracle
    py check_ring.py --learn    # record where the ring is, as fractions

Positions are stored in oracle.json as FRACTIONS of the PCSX2 client area, not
as screen pixels. The previous version hardcoded (3481.5, 649.0) -- absolute
coordinates on a 4K desktop -- so it quietly started lying the moment the window
moved, was resized, or landed on a different monitor.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import grab, red_clusters, to_frac, from_frac, load_oracle, save_oracle

# how close the dot must be to the ring centre, as a fraction of client height
DEFAULT_TOL = 0.03


def find_dot(shots=5, delay=0.4, panel=None):
    """The tracker's estimate: the FILLED red mark. The ring is hollow arcs.

    Returns (cluster, img, meta) or (None, img, meta).
    """
    best, img, meta = None, None, {}
    for _ in range(shots):
        img, meta = grab(with_meta=True)
        for r in red_clusters(img, min_area=80, max_area=900):
            if r["w"] < 10 or r["h"] < 10 or r["fill"] <= 0.85:
                continue
            if panel:
                fy = r["y"] / float(meta.get('height') or img.shape[0])
                if not (panel[0] <= fy <= panel[1]):
                    continue
            best = r
        time.sleep(delay)
    return best, img, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--learn', action='store_true',
                    help='record the CURRENT dot position as the ring centre')
    ap.add_argument('--tol', type=float, default=None,
                    help='accept radius as a fraction of client height')
    ap.add_argument('--shots', type=int, default=5)
    args = ap.parse_args()

    oracle = load_oracle()
    panel = None
    if 'panel' in oracle:
        panel = (oracle['panel']['fy0'], oracle['panel']['fy1'])

    try:
        dot, img, meta = find_dot(args.shots, panel=panel)
    except RuntimeError as e:
        print(f"check_ring: {e}")
        return 1
    if not dot:
        print("no tracker dot found. Is the SENSOR ADJUSTMENT screen up, and is "
              "the pump feeding a moving target?")
        return 1

    fx, fy = to_frac(dot["x"], dot["y"], img, meta)
    w, h = meta.get('width', img.shape[1]), meta.get('height', img.shape[0])
    print(f"client area : {w} x {h}")
    print(f"tracker dot : ({dot['x']:.1f}, {dot['y']:.1f}) px = "
          f"({fx:.4f}, {fy:.4f}) of client")

    if args.learn:
        tol = args.tol if args.tol is not None else DEFAULT_TOL
        save_oracle({"ring": {"fx": round(fx, 5), "fy": round(fy, 5),
                              "ftol": round(tol, 5)},
                     "learned_at": {"width": w, "height": h}})
        print(f"\nrecorded ring centre at ({fx:.4f}, {fy:.4f}), tolerance "
              f"{tol:.4f} of height ({tol * h:.0f} px here) -> oracle.json")
        print("NOTE: this records where the dot IS. Only run --learn when the dot "
              "is genuinely sitting in the game's ring.")
        return 0

    ring = oracle.get('ring')
    if not ring:
        print("\nno ring recorded yet. Put the dot in the game's ring and run:\n"
              "    py check_ring.py --learn")
        return 2

    tol = args.tol if args.tol is not None else ring.get('ftol', DEFAULT_TOL)
    rx, ry = from_frac(ring['fx'], ring['fy'], img, meta)
    # distance in pixels, but compared against a tolerance expressed in
    # fractions of height, so the verdict is resolution-independent
    d_px = ((dot["x"] - rx) ** 2 + (dot["y"] - ry) ** 2) ** 0.5
    d_frac = d_px / float(h)

    print(f"ring centre : ({rx:.1f}, {ry:.1f}) px = "
          f"({ring['fx']:.4f}, {ring['fy']:.4f}) of client")
    print(f"distance    : {d_px:.1f} px = {d_frac:.4f} of height "
          f"(tolerance {tol:.4f} = {tol * h:.0f} px)")
    if d_frac <= tol:
        print("\nRESULT: INSIDE THE RING -- neutral is calibrated")
        return 0
    dxf = (dot["x"] - rx) / float(w)
    dyf = (dot["y"] - ry) / float(h)
    print(f"\nRESULT: outside by {(d_frac - tol) * h:.0f} px -- neutral needs nudging")
    print(f"        dot is {dxf:+.4f} of width, {dyf:+.4f} of height from centre")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
