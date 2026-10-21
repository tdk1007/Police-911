"""Check the rendered target actually behaves the way the tracker needs.

Runs entirely on rendered frames -- no game, no camera, no virtual camera. It
measures the intensity-weighted centroid of what we draw, which is the quantity
a centroid-of-bright-mass tracker is trying to recover, and asserts:

  1. the Gaussian's centroid lands where place_f() said it would
  2. it moves LINEARLY with the commanded position, with sub-pixel residual
  3. clipping at the frame edge breaks that, and clip_overhang() catches it
  4. the Gaussian tracks more smoothly than a whole-pixel hard disc

Check 3 is the regression test for the dead vertical band: with the calibration
that shipped in calib.json, the head ran off the top of the frame and its
visible centroid stopped following the command, which is what made dy=0.0 and
dy=+0.4 read back the same dot_y.

    py render_selftest.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render


def centroid(img):
    """Intensity-weighted centroid -- what a bright-mass tracker computes."""
    a = img.astype(np.float64)
    total = a.sum()
    if total <= 0:
        return None
    ys, xs = np.indices(a.shape)
    return float((xs * a).sum() / total), float((ys * a).sum() / total)


def fit_line(x, y):
    """slope, intercept, max abs residual."""
    m, b = np.polyfit(x, y, 1)
    resid = np.abs(np.asarray(y) - (m * np.asarray(x) + b))
    return float(m), float(b), float(resid.max())


def main():
    checks, failures = 0, []

    def check(label, ok, detail=''):
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f'{label}{(" -- " + detail) if detail else ""}')
        return ok

    # A calibration that keeps the blob fully inside the frame at every command.
    # 3*sigma = 3*0.085*480 = ~123 px, so the centre must stay >=123 px from any
    # edge: y in [123, 357] -> neutral_y 0.5, range_y 0.2 gives y in [144, 336].
    render.CALIB.update(neutral_x=0.5, neutral_y=0.5, range_x=0.24, range_y=0.2)
    render.reload_calib = lambda: None       # stop calib.json fighting the test
    render._gauss_cache.clear()

    cmds = np.linspace(-1.0, 1.0, 21)

    # --- 1 & 2: centroid lands where asked, and moves linearly -----------------
    want_x, got_x, want_y, got_y = [], [], [], []
    for c in cmds:
        wx, _ = render.place_f(c, 0.0)
        gx = centroid(render.draw_gaussian(c, 0.0))
        want_x.append(wx)
        got_x.append(gx[0])
        _, wy = render.place_f(0.0, c)
        gy = centroid(render.draw_gaussian(0.0, c))
        want_y.append(wy)
        got_y.append(gy[1])

    err_x = np.abs(np.array(got_x) - np.array(want_x)).max()
    err_y = np.abs(np.array(got_y) - np.array(want_y)).max()
    check('x centroid matches place_f', err_x < 0.35, f'max error {err_x:.3f} px')
    check('y centroid matches place_f', err_y < 0.35, f'max error {err_y:.3f} px')

    mx, _, rx = fit_line(cmds, got_x)
    my, _, ry = fit_line(cmds, got_y)
    check('x response linear', rx < 0.25, f'max residual {rx:.3f} px')
    check('y response linear', ry < 0.25, f'max residual {ry:.3f} px')
    check('x slope correct', abs(mx - render.OUT_W * 0.24) < 1.0, f'slope {mx:.2f}')
    check('y slope correct', abs(my - render.OUT_H * 0.20) < 1.0, f'slope {my:.2f}')

    # no dead band: every step must actually move the centroid
    steps_x = np.diff(got_x)
    steps_y = np.diff(got_y)
    check('x has no dead band', steps_x.min() > 0.5,
          f'smallest step {steps_x.min():.3f} px')
    check('y has no dead band', steps_y.min() > 0.5,
          f'smallest step {steps_y.min():.3f} px')

    # --- 4: sub-pixel beats whole-pixel ---------------------------------------
    # Compare against the same blob forced onto whole-pixel positions, which is
    # what a hard-edged shape drawn with cv2 integer coords effectively does.
    saved = render.SUBPIXEL_STEPS
    render.SUBPIXEL_STEPS = 1                # 1 step per pixel == whole-pixel only
    render._gauss_cache.clear()
    coarse = [centroid(render.draw_gaussian(c, 0.0))[0] for c in cmds]
    render.SUBPIXEL_STEPS = saved
    render._gauss_cache.clear()

    _, _, r_coarse = fit_line(cmds, coarse)
    check('sub-pixel is smoother than whole-pixel', rx < r_coarse,
          f'sub-pixel residual {rx:.3f} px vs whole-pixel {r_coarse:.3f} px')

    # --- 3: clipping breaks tracking, and we detect it ------------------------
    # Reinstate the calibration that actually shipped, which puts the blob's top
    # off the frame, and confirm both that the centroid stops following and that
    # clip_overhang() reports it.
    render.CALIB.update(neutral_x=0.521, neutral_y=0.146, range_x=0.31, range_y=0.21)
    render._gauss_cache.clear()

    clipped_any = False
    clip_got = []
    for c in cmds:
        cxf, cyf = render.place_f(0.0, c)
        _, rxp, ryp = render._gauss_tile(render.OUT_H * 0.085, 1.0, 255, 0)
        if render.is_clipped(int(cxf), int(cyf), rxp, ryp):
            clipped_any = True
        clip_got.append(centroid(render.draw_gaussian(0.0, c, warn=False))[1])

    check('shipped calibration is detected as clipping', clipped_any,
          'clip_overhang saw nothing wrong with neutral_y=0.146')

    _, _, r_clip = fit_line(cmds, clip_got)
    check('clipping visibly breaks linearity', r_clip > 2.0,
          f'residual only {r_clip:.3f} px -- expected clipping to distort it')

    worst_step = np.diff(clip_got).min()
    print(f"\n  unclipped: x residual {rx:.3f} px, y residual {ry:.3f} px, "
          f"smallest y step {steps_y.min():.3f} px")
    print(f"  clipped  : y residual {r_clip:.3f} px, smallest y step {worst_step:.3f} px")
    print(f"  whole-pixel x residual {r_coarse:.3f} px (sub-pixel: {rx:.3f} px)")

    for f in failures:
        print(f'  FAIL  {f}')
    print(f"render_selftest: {checks - len(failures)}/{checks} checks passed")
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
