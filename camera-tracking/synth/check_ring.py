"""Is the game's head marker sitting inside its calibration ring?

That is the game's own definition of "the player is standing in the right place",
so it is the pass/fail for our neutral calibration.
"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import grab, red_clusters

RING = (3481.5, 649.0)
RADIUS = 32.0

best = None
for _ in range(5):
    img = grab()
    for r in red_clusters(img, min_area=80, max_area=900):
        if 520 < r["y"] < 1180 and r["w"] >= 10 and r["h"] >= 10 and r["fill"] > 0.85:
            best = r          # the filled square = tracker dot (ring is hollow arcs)
    time.sleep(0.4)

if not best:
    print("no tracker dot found")
    sys.exit(1)

d = ((best["x"] - RING[0]) ** 2 + (best["y"] - RING[1]) ** 2) ** 0.5
print(f"tracker dot : ({best['x']:.1f}, {best['y']:.1f})")
print(f"ring centre : ({RING[0]}, {RING[1]})  radius {RADIUS:.0f}px")
print(f"distance    : {d:.1f}px")
print("\nRESULT:", "INSIDE THE RING - neutral is calibrated"
      if d <= RADIUS else f"outside by {d - RADIUS:.0f}px - neutral needs nudging")
