"""Locate the calibration ring precisely.

The ring is the red target the game wants the head marker to sit inside. It never
moves, so: park the silhouette far to one side (dragging the tracker dot away
with it), then whatever red remains near the middle of the panel is the ring.
"""
import os, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from probe import grab, red_clusters

PANEL_Y = (520, 1180)

# park the player hard left so the dot is far from the ring
subprocess.run(["py", "setctl.py", "anim=none", "jitter=0.03", "dx=0.95", "dy=0.9"],
               cwd=HERE, capture_output=True)
time.sleep(2.0)

pts = []
for _ in range(4):
    img = grab()
    for r in red_clusters(img, min_area=3, max_area=3000):
        if PANEL_Y[0] < r["y"] < PANEL_Y[1]:
            pts.append(r)
    time.sleep(0.4)

print("red clusters in the preview panel (player parked far away):")
for r in sorted(pts, key=lambda r: r["x"]):
    print(f"  ({r['x']:7.1f},{r['y']:7.1f})  area={r['area']:4d}  "
          f"box={r['w']}x{r['h']}  fill={r['fill']}")

# the ring sits well away from the parked dot; group what's left
if pts:
    xs = np.array([r["x"] for r in pts])
    ys = np.array([r["y"] for r in pts])
    # the dot went to roughly dot_x = -255.8*0.95 + 3498.8 = 3255
    keep = [r for r in pts if abs(r["x"] - 3255) > 90]
    if keep:
        cx = np.mean([r["x"] for r in keep])
        cy = np.mean([r["y"] for r in keep])
        print(f"\n  RING CENTRE ~= ({cx:.1f}, {cy:.1f})   from {len(keep)} fragments")
        # invert the fits measured by measure.py
        dx = (3498.79 - cx) / 255.78
        dy = (cy - 742.08) / 100.76
        print(f"  -> to put the head in the ring, command dx={dx:+.3f}, dy={dy:+.3f}")
    else:
        print("\n  couldn't separate ring from dot")
