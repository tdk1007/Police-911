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
import json, subprocess, sys, os, time
import cv2, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(HERE, 'pcsx2_shot.png')
SHOT_META = os.path.join(HERE, 'pcsx2_shot.json')
ORACLE = os.path.join(HERE, 'oracle.json')


def grab(with_meta=False):
    """Screenshot PCSX2's client area. Optionally also where on screen it was.

    shot.ps1 captures the CLIENT rect, so pixel (0,0) is the top-left of the
    rendered frame regardless of where the window sits or how thick its border
    is. Everything downstream stores positions as fractions of this image, which
    is why moving or resizing the window no longer invalidates a calibration.
    """
    # Delete first, and check the capture actually succeeded. Without this, a
    # failed shot.ps1 left the PREVIOUS pcsx2_shot.png in place and cv2.imread
    # happily returned it -- so a sweep could record the same stale dot position
    # for every sample and look like a tracker with a dead band. Never read a
    # screenshot we did not just take.
    try:
        os.remove(SHOT)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    started = time.time()
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", os.path.join(HERE, "shot.ps1")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        msg = (r.stdout or r.stderr or '').strip() or f"exit {r.returncode}"
        raise RuntimeError(f"screenshot failed: {msg}")
    img = cv2.imread(SHOT)
    if img is None:
        raise RuntimeError("no screenshot -- is PCSX2 running and not minimised?")
    if os.path.getmtime(SHOT) < started - 1.0:
        raise RuntimeError("screenshot is stale -- shot.ps1 did not rewrite it")
    if not with_meta:
        return img
    meta = {}
    try:
        with open(SHOT_META, encoding='utf-8-sig') as f:
            meta = json.load(f)
    except Exception:
        pass
    meta.setdefault('width', img.shape[1])
    meta.setdefault('height', img.shape[0])
    return img, meta


def to_frac(x, y, img=None, meta=None):
    """Absolute pixel in the shot -> fraction of the client area."""
    w = (meta or {}).get('width') or (img.shape[1] if img is not None else 1)
    h = (meta or {}).get('height') or (img.shape[0] if img is not None else 1)
    return x / float(w), y / float(h)


def from_frac(fx, fy, img=None, meta=None):
    """Fraction of the client area -> absolute pixel in the shot."""
    w = (meta or {}).get('width') or (img.shape[1] if img is not None else 1)
    h = (meta or {}).get('height') or (img.shape[0] if img is not None else 1)
    return fx * float(w), fy * float(h)


def load_oracle():
    """Where the calibration ring and the preview panel are, as fractions.

    Replaces the screen-absolute 4K pixel constants that used to be baked into
    check_ring.py and measure.py, which silently became wrong the moment the
    PCSX2 window moved.
    """
    try:
        with open(ORACLE, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return {}


def save_oracle(d):
    cur = load_oracle()
    cur.update(d)
    with open(ORACLE, 'w', encoding='utf-8') as f:
        json.dump(cur, f, indent=1)
    return cur


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


def tracker_dot(img, panel=None, min_area=8, max_area=400):
    """The tracker's estimate: the small filled red square in the preview.

    `panel` is (x0, x1, y0, y1) in image pixels, to exclude red UI elsewhere
    (the title banner, the NOISE REMOVAL button).

    Rejecting the calibration ring is the whole difficulty. The ring is a thin
    hollow circle, and the obvious test -- "fill = area / bounding-box area is
    high, so it is solid" -- FAILS on it: the threshold breaks the ring into
    short arcs, and a 12x1 horizontal arc has fill = 1.00, higher than the
    dot's own 0.90. That misidentification produced a dot_y of 299.0 (the ring's
    own y) in the middle of a sweep and destroyed the fit, turning r = 0.997
    into r = -0.16.

    So also require the shape to be THICK in both axes and roughly square. An
    arc is 1-2 px in one dimension; the dot is ~8x9.
    """
    best = None
    for c in red_clusters(img, min_area=min_area, max_area=max_area):
        if panel:
            x0, x1, y0, y1 = panel
            if not (x0 < c['x'] < x1 and y0 < c['y'] < y1):
                continue
        if c['w'] < 4 or c['h'] < 4:          # thin arc of the ring
            continue
        aspect = c['w'] / float(c['h'])
        if not (0.4 <= aspect <= 2.5):        # elongated -> not the dot
            continue
        if c['fill'] < 0.6:                   # hollow -> the ring itself
            continue
        if best is None or c['area'] > best['area']:
            best = c
    return best


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
