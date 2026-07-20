"""Measure the game tracker's transfer function on the SENSOR ADJUSTMENT screen.

We command the synthetic silhouette to a position, screenshot, and read back:
  * where the game DISPLAYS our silhouette   (white blob in the preview)
  * where the game THINKS the head is        (red tracker dot)
  * where the game WANTS the head to be      (red calibration ring, static)

The ring is hollow and never moves; the dot is filled and follows us. We tell
them apart by movement across the sweep, then fit dx,dy -> dot position and
solve for the command that lands the dot in the ring.

A small jitter is left running the whole time -- a still image makes this
tracker's estimate meaningless.
"""
import json, os, subprocess, sys, time
import cv2, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from probe import grab, red_clusters, white_blob

PANEL_Y = (520, 1180)          # the preview panel band, in window pixels


def setctl(**kw):
    subprocess.run([sys.executable if False else "py", "setctl.py"]
                   + [f"{k}={json.dumps(v) if isinstance(v,bool) else v}" for k, v in kw.items()],
                   cwd=HERE, capture_output=True)


def sample(settle=1.1, n=3):
    """Take a few shots; return (white blob, [red clusters]) from the last good one."""
    time.sleep(settle)
    best = None
    for _ in range(n):
        img = grab()
        wb = white_blob(img)
        reds = [r for r in red_clusters(img) if PANEL_Y[0] < r["y"] < PANEL_Y[1]]
        if wb and reds:
            best = (wb, reds)
        time.sleep(0.25)
    return best


def find_ring_and_dot(reds, wb, ring_hint=None):
    """dot = the red cluster nearest our head; ring = the other one."""
    hx, hy = wb["cx"], wb["top"]            # top-centre of our silhouette = head
    ranked = sorted(reds, key=lambda r: (r["x"] - hx) ** 2 + (r["y"] - hy) ** 2)
    dot = ranked[0]
    ring = None
    if ring_hint is not None:
        cands = [r for r in reds if r is not dot]
        if cands:
            ring = min(cands, key=lambda r: (r["x"] - ring_hint[0]) ** 2 + (r["y"] - ring_hint[1]) ** 2)
    return dot, ring


def main():
    print("Leaving a jitter running so the tracker stays alive.\n")

    # --- pass 1: sweep dx, watch the dot's x
    xs = []
    for dx in (-0.8, -0.4, 0.0, 0.4, 0.8):
        setctl(anim="none", jitter=0.03, jitter_hz=3.0, dx=dx, dy=0.0)
        s = sample()
        if not s:
            print(f"  dx={dx:+.2f}  NO READING")
            continue
        wb, reds = s
        dot, _ = find_ring_and_dot(reds, wb)
        xs.append((dx, wb["cx"], wb["top"], dot["x"], dot["y"]))
        print(f"  dx={dx:+.2f}  our head=({wb['cx']:7.1f},{wb['top']:6.1f})  "
              f"tracker dot=({dot['x']:7.1f},{dot['y']:7.1f})")

    # --- pass 2: sweep dy, watch the dot's y
    ys = []
    for dy in (-0.8, -0.4, 0.0, 0.4, 0.8):
        setctl(anim="none", jitter=0.03, jitter_hz=3.0, dx=0.0, dy=dy)
        s = sample()
        if not s:
            print(f"  dy={dy:+.2f}  NO READING")
            continue
        wb, reds = s
        dot, _ = find_ring_and_dot(reds, wb)
        ys.append((dy, wb["cx"], wb["top"], dot["x"], dot["y"]))
        print(f"  dy={dy:+.2f}  our head=({wb['cx']:7.1f},{wb['top']:6.1f})  "
              f"tracker dot=({dot['x']:7.1f},{dot['y']:7.1f})")

    print("\n=== fit ===")
    if len(xs) >= 2:
        a, b = np.polyfit([r[0] for r in xs], [r[3] for r in xs], 1)
        res = np.std([r[3] - (a * r[0] + b) for r in xs])
        print(f"  dot_x = {a:8.2f} * dx + {b:8.2f}     (residual {res:.1f}px)")
    if len(ys) >= 2:
        c, d = np.polyfit([r[0] for r in ys], [r[4] for r in ys], 1)
        res = np.std([r[4] - (c * r[0] + d) for r in ys])
        print(f"  dot_y = {c:8.2f} * dy + {d:8.2f}     (residual {res:.1f}px)")

    # how well does the dot track our head?
    off = [(r[3] - r[1], r[4] - r[2]) for r in xs + ys]
    if off:
        ox = np.mean([o[0] for o in off]); oy = np.mean([o[1] for o in off])
        print(f"\n  dot - our head: mean offset ({ox:+.1f}, {oy:+.1f}) px, "
              f"spread ({np.std([o[0] for o in off]):.1f}, {np.std([o[1] for o in off]):.1f})")

    json.dump({"xs": xs, "ys": ys}, open(os.path.join(HERE, "measure.json"), "w"), indent=1)
    print("\n  saved measure.json")


if __name__ == '__main__':
    main()
