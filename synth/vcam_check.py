"""Prove the synthetic pipeline end to end, without the game:

    render.py  ->  pyvirtualcam  ->  "OBS Virtual Camera" (DirectShow)  ->  us

We push a known pattern into the virtual camera, then read that camera back
through DirectShow (exactly the way PCSX2 will) and check we get our pixels.
OBS must NOT be running -- it owns the same sink.
"""
import threading, time, sys
import cv2, numpy as np
import pyvirtualcam
from pyvirtualcam import PixelFormat
from pygrabber.dshow_graph import FilterGraph

sys.path.insert(0, __file__.rsplit('\\', 1)[0])
import render

DX, DY = -0.5, 0.25            # known blob position we will look for
stop = threading.Event()


def pump():
    frame = render.to_bgr(render.pattern_blob(DX, DY))
    with pyvirtualcam.Camera(width=render.OUT_W, height=render.OUT_H, fps=30,
                             fmt=PixelFormat.BGR, backend='obs') as cam:
        print(f"  virtual camera up: {cam.device}  {cam.width}x{cam.height}@{cam.fps}")
        while not stop.is_set():
            cam.send(frame)
            cam.sleep_until_next_frame()


t = threading.Thread(target=pump, daemon=True)
t.start()
time.sleep(2.0)                # let the sink settle

names = FilterGraph().get_input_devices()
if "OBS Virtual Camera" not in names:
    print("  ERROR: 'OBS Virtual Camera' not registered"); stop.set(); sys.exit(1)
idx = names.index("OBS Virtual Camera")

cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)      # what the game asks for
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
got = None
for _ in range(30):
    ok, f = cap.read()
    if ok and f is not None and f.mean() > 0.5:
        got = f
        break
    time.sleep(0.05)
cap.release()
stop.set()

if got is None:
    print("  FAILED: read no frame back from the virtual camera")
    sys.exit(1)

h, w = got.shape[:2]
g = cv2.cvtColor(got, cv2.COLOR_BGR2GRAY)
ys, xs = np.where(g > 128)
cv2.imwrite("vcam_readback.png", got)

print(f"\n  read back {w}x{h} from 'OBS Virtual Camera'")
if len(xs) == 0:
    print("  FAILED: frame arrived but contains no bright blob")
    sys.exit(1)

# where did the blob land, in normalised coords?
cx, cy = xs.mean() / w, ys.mean() / h
exp_x = 0.5 + 0.5 * DX * 0.8
exp_y = 0.5 + 0.5 * DY * 0.8
print(f"  blob centre : ({cx:.3f}, {cy:.3f})   expected ({exp_x:.3f}, {exp_y:.3f})")
print(f"  bright px   : {len(xs)}  ({100*len(xs)/(w*h):.1f}% of frame)")

ok = abs(cx - exp_x) < 0.04 and abs(cy - exp_y) < 0.04
print("\n  RESULT:", "PASS - the game will see exactly what we draw"
      if ok else "MISMATCH - geometry is being altered in transit")
print("  saved vcam_readback.png")
