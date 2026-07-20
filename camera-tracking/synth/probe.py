"""Read the game's tracker off its own SENSOR ADJUSTMENT screen.

The screen renders the tracker's view of the camera plus its head estimate, so it
is a black-box oracle: we command a silhouette position, screenshot, and read
back what the tracker concluded.

Two red things are on that screen:
  * the calibration ZONE  -- a hollow ring, and it does not move
  * the tracker's ESTIMATE -- a small filled dot, and it DOES move
So we identify the estimate by taking several shots and finding the red cluster
whose position varies.

    py probe.py watch [n]     # n shots during the current animation
"""
import subprocess, sys, os, time
import cv2, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(HERE, 'pcsx2_shot.png')


def grab():
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", os.path.join(HERE, "shot.ps1")],
                   capture_output=True)
    img = cv2.imread(SHOT)
    if img is None:
        raise RuntimeError("no screenshot")
    return img


def red_clusters(img, min_area=4, max_area=4000):
    """Find red things. Red = strong R, weak G and B."""
    b, g, r = cv2.split(img.astype(np.int16))
    mask = ((r > 110) & (r - g > 60) & (r - b > 60)).astype(np.uint8) * 255
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if min_area <= a <= max_area:
            w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            # a ring is hollow: its area is small relative to its bounding box
            fill = a / max(1, w * h)
            out.append({"x": float(cent[i][0]), "y": float(cent[i][1]),
                        "area": int(a), "w": int(w), "h": int(h),
                        "fill": round(float(fill), 2)})
    return out


def white_blob(img):
    """Our synthetic silhouette as the game is displaying it."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    b, gg, r = cv2.split(img)
    mask = ((g > 190) & (abs(b.astype(int) - r.astype(int)) < 30)).astype(np.uint8) * 255
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    best, ba = None, 0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a > ba and a > 200:
            ba, best = a, i
    if best is None:
        return None
    return {"cx": float(cent[best][0]), "cy": float(cent[best][1]),
            "top": int(stats[best, cv2.CC_STAT_TOP]),
            "left": int(stats[best, cv2.CC_STAT_LEFT]),
            "w": int(stats[best, cv2.CC_STAT_WIDTH]),
            "h": int(stats[best, cv2.CC_STAT_HEIGHT]),
            "area": int(ba)}


def watch(n=6, delay=0.9):
    shots = []
    for i in range(n):
        img = grab()
        reds = red_clusters(img)
        wb = white_blob(img)
        shots.append((reds, wb))
        print(f"\n--- shot {i} ---")
        if wb:
            print(f"  our silhouette: centre=({wb['cx']:.0f},{wb['cy']:.0f}) "
                  f"top={wb['top']} box={wb['w']}x{wb['h']} area={wb['area']}")
        else:
            print("  our silhouette: NOT VISIBLE")
        for rc in sorted(reds, key=lambda c: -c["area"])[:6]:
            kind = "ring?" if rc["fill"] < 0.55 else "dot?"
            print(f"  red {kind:5s} at ({rc['x']:7.1f},{rc['y']:7.1f}) "
                  f"area={rc['area']:5d} box={rc['w']}x{rc['h']} fill={rc['fill']}")
        time.sleep(delay)

    # which red cluster moved? that one is the tracker's estimate.
    print("\n=== movement analysis ===")
    allred = [r for reds, _ in shots for r in reds]
    if not allred:
        print("  no red found at all")
        return
    # group by rough position across shots
    groups = []
    for r in allred:
        for gp in groups:
            if abs(gp[0]["x"] - r["x"]) < 40 and abs(gp[0]["y"] - r["y"]) < 40:
                gp.append(r)
                break
        else:
            groups.append([r])
    for gp in sorted(groups, key=lambda g: -len(g)):
        xs = [p["x"] for p in gp]
        ys = [p["y"] for p in gp]
        print(f"  cluster seen {len(gp)}x  mean=({np.mean(xs):7.1f},{np.mean(ys):7.1f})  "
              f"x-range={max(xs)-min(xs):6.1f}  y-range={max(ys)-min(ys):6.1f}  "
              f"fill={gp[0]['fill']}")
    print("\n  -> the cluster with a LARGE x-range is the tracker following our sweep.")
    print("  -> a cluster with ~0 range is the static calibration zone.")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'watch'
    if cmd == 'watch':
        watch(int(sys.argv[2]) if len(sys.argv) > 2 else 6)
