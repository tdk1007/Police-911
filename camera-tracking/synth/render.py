"""Frame synthesis for the Police 24/7 synthetic camera.

Everything the game sees is generated here. Two hard constraints, both verified
against the game's own code (see ../re/RE_FINDINGS.md):

  * The game is LUMINANCE-ONLY. Its frame converter reads one byte per pixel and
    writes it to R, G and B. Colour is discarded, so we only ever draw in gray.
  * It accepts a fixed set of geometries. We output 4:3; the emulated Capture Eye
    hands the game 320x240.

We render at OUT_W x OUT_H and let the virtual-camera sink deliver it.
"""
import json
import os

import cv2
import numpy as np

OUT_W, OUT_H = 640, 480          # 4:3, matches what the rig already fed PCSX2

# Defaults for the player silhouette. These are HYPOTHESES about what the 2003
# tracker likes -- the SENSOR ADJUSTMENT oracle is what actually tunes them.
BG_LEVEL = 0                     # flat black background: zero false edges
FG_LEVEL = 255                   # maximum contrast against it

# Where dx=dy=0 puts the head, and how far +/-1 moves it, as fractions of the
# frame. NOT magic numbers: measured against the game's own calibration ring on
# the SENSOR ADJUSTMENT screen (see measure.py / ring.py). Neutral must land the
# game's head marker inside that ring, or the game thinks you're standing in the
# wrong place before we even start.
CALIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calib.json')
CALIB = {"neutral_x": 0.521, "neutral_y": 0.146, "range_x": 0.31, "range_y": 0.21}
if os.path.exists(CALIB_PATH):
    try:
        with open(CALIB_PATH, encoding='utf-8-sig') as f:
            CALIB.update(json.load(f))
    except Exception as e:
        print(f"render: calib.json unreadable ({e}); using built-in defaults")


_calib_mtime = None


def reload_calib():
    """Re-read calib.json when it changes.

    Restarting the pump while PCSX2 already holds the DirectShow filter kills its
    capture, so calibration has to be tunable WITHOUT a restart.
    """
    global _calib_mtime
    try:
        m = os.path.getmtime(CALIB_PATH)
    except OSError:
        return
    if m == _calib_mtime:
        return
    try:
        with open(CALIB_PATH, encoding='utf-8-sig') as f:
            CALIB.update(json.load(f))
        _calib_mtime = m
        print(f"render: calib reloaded {CALIB}", flush=True)
    except Exception as e:
        print(f"render: calib.json unreadable ({e}); keeping previous", flush=True)


def place_f(dx, dy):
    """Normalised command -> sub-pixel position of the head centre.

    The vertical range is ASYMMETRIC, and it has to be. Measured against the
    game's own calibration ring (2026-09-13): the ring sits high in the camera
    frame, because that is where a standing player's head belongs. So neutral_y
    is near the top, which leaves very little room above it before the target
    clips -- but a great deal of room below, which is exactly the direction a
    duck travels.

    A symmetric range would have to be the SMALLER of the two, throwing away
    most of the duck travel to reserve headroom nobody uses: dy < 0 only means
    "standing even taller than neutral", and neutral already is standing.

    `range_y_up` / `range_y_down` override `range_y` when present.
    """
    reload_calib()
    cx = OUT_W * (CALIB["neutral_x"] + dx * CALIB["range_x"])
    span = CALIB.get("range_y_up" if dy < 0 else "range_y_down", CALIB["range_y"])
    cy = OUT_H * (CALIB["neutral_y"] + dy * span)
    return cx, cy


def place(dx, dy):
    """Normalised command -> whole-pixel position of the head centre."""
    cx, cy = place_f(dx, dy)
    return int(cx), int(cy)


def clip_overhang(cx, cy, rx, ry):
    """How far a shape of half-size (rx, ry) at (cx, cy) falls outside the frame.

    Returns pixels overhanging (left, top, right, bottom); all zero means the
    shape is wholly visible.

    This exists because of a real bug. With the calibration that was in
    calib.json (neutral_y 0.146, range_y 0.21) and head_r 0.18, the head centre
    sits at y=70 while its half-height is 86 px -- so the top of the head was
    cut off by the frame edge across most of the dy sweep. A clipped shape's
    VISIBLE centroid stops tracking its commanded centre, which is why
    measure.json shows dy=0.0 and dy=+0.4 producing an identical dot_y of 742.
    The transfer function was then fitted straight through that dead band.

    Anything that positions a shape should check this and complain loudly.
    """
    return (max(0, rx - cx),
            max(0, ry - cy),
            max(0, cx + rx - OUT_W),
            max(0, cy + ry - OUT_H))


def is_clipped(cx, cy, rx, ry):
    return any(clip_overhang(cx, cy, rx, ry))


def blank(level=BG_LEVEL):
    return np.full((OUT_H, OUT_W), level, np.uint8)


def to_bgr(gray):
    """Game is luma-only, but the vcam sink wants 3 channels. R=G=B."""
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def draw_player(dx, dy, *, head_r=0.11, shoulder_w=0.34, shoulder_drop=0.30,
                fg=FG_LEVEL, bg=BG_LEVEL, filled=True, thickness=3):
    """Draw an idealised head-and-shoulders silhouette.

    dx, dy are normalised in [-1, 1]:
        dx = -1 fully leaned left ... +1 fully leaned right
        dy = -1 standing tall      ... +1 fully ducked
    Sizes are fractions of frame width/height, so the shape scales with OUT_*.

    `filled=False` draws only the outline -- we use that to test whether the
    game's tracker responds to AREA or to EDGES.
    """
    img = blank(bg)

    # Because we synthesise the head, the player can never fall out of view.
    cx, cy = place(dx, dy)

    rx = int(OUT_W * head_r * 0.62)      # head is taller than wide
    ry = int(OUT_H * head_r)

    sw = int(OUT_W * shoulder_w / 2)
    sy = cy + int(ry * 1.35)              # shoulders start just below the head
    by = sy + int(OUT_H * shoulder_drop)  # body runs to here

    body = np.array([
        [cx - sw, by], [cx - int(sw * 0.78), sy],
        [cx - int(rx * 0.72), sy - int(ry * 0.25)],
        [cx + int(rx * 0.72), sy - int(ry * 0.25)],
        [cx + int(sw * 0.78), sy], [cx + sw, by],
    ], np.int32)

    if filled:
        cv2.fillPoly(img, [body], fg)
        cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, fg, -1)
    else:
        cv2.polylines(img, [body], True, fg, thickness)
        cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, fg, thickness)

    return img


def draw_head_only(dx, dy, *, head_r=0.11, fg=FG_LEVEL, bg=BG_LEVEL):
    """Just the head, no torso.

    The first live test showed the tracker's dot land on the CHEST of a full
    head-and-shoulders silhouette: the shoulders carry far more bright area than
    the head, so if the tracker takes a centroid of the bright region, the torso
    drags its estimate down. Removing the torso makes the head the entire mass,
    so centroid and head coincide.
    """
    img = blank(bg)
    cx, cy = place(dx, dy)
    rx, ry = int(OUT_W * head_r * 0.62), int(OUT_H * head_r)
    over = clip_overhang(cx, cy, rx, ry)
    if any(over):
        _warn_clip(dx, dy, cx, cy, rx, ry, over)
    cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, fg, -1)
    return img


_gauss_cache = {}
SUBPIXEL_STEPS = 8       # positions per pixel; 8 keeps the cache small and the
                         # residual well under the 320x240 the game actually sees


def _gauss_tile(sigma_px, aspect, fg, bg, fx=0.0, fy=0.0):
    """A Gaussian bump offset by a sub-pixel (fx, fy), cached.

    Cut off at 3 sigma, where the bump is already ~1% of peak. The fractional
    offset is baked into the sample positions rather than applied afterwards, so
    there is no resampling blur.
    """
    key = (round(sigma_px, 3), round(aspect, 3), int(fg), int(bg),
           round(fx, 3), round(fy, 3))
    tile = _gauss_cache.get(key)
    if tile is not None:
        return tile
    sy = max(1.0, sigma_px)
    sx = max(1.0, sigma_px * aspect)
    ry, rx = int(3 * sy) + 1, int(3 * sx) + 1
    yy = (np.arange(-ry, ry + 1, dtype=np.float32) - fy)[:, None]
    xx = (np.arange(-rx, rx + 1, dtype=np.float32) - fx)[None, :]
    g = np.exp(-0.5 * ((xx / sx) ** 2 + (yy / sy) ** 2))
    tile = ((bg + (fg - bg) * g).clip(0, 255).astype(np.uint8), rx, ry)
    if len(_gauss_cache) > 256:           # calib tweaks churn keys; do not grow forever
        _gauss_cache.clear()
    _gauss_cache[key] = tile
    return tile


def draw_gaussian(dx, dy, *, sigma=0.085, aspect=1.0, fg=FG_LEVEL, bg=BG_LEVEL,
                  warn=True):
    """A soft radial blob at the commanded position. The preferred live target.

    Better than draw_head_only for the same reason draw_head_only beat
    draw_player: give the tracker as little excuse as possible to put its
    estimate anywhere but where we asked.

      * No torso, so nothing drags the centroid down -- the chest bug that
        killed draw_player.
      * Positioned to a fraction of a pixel. A hard-edged disc snapped to whole
        pixels has an intensity-weighted centroid that wobbles as it translates,
        because whole rows and columns of rim pixels switch on and off at once.
        A smooth bump sampled at a fractional offset moves its centroid smoothly
        and proportionally. That matters here because the game downsamples our
        640x480 to its own grid before tracking, and quantisation upstream of a
        downsample turns into visible stepping.
      * Degrades gracefully under thresholding: as the game's gain shifts, the
        retained region shrinks symmetrically about the same centre instead of
        the blob vanishing all at once.

    `sigma` is a fraction of frame height. The default puts 3 sigma at ~123 px,
    comfortably inside a 480-line frame as long as the neutral point is sane --
    and clip_overhang() shouts if it is not.
    """
    img = blank(bg)
    cxf, cyf = place_f(dx, dy)
    cx, cy = int(np.floor(cxf)), int(np.floor(cyf))
    q = float(SUBPIXEL_STEPS)
    fx = round((cxf - cx) * q) / q
    fy = round((cyf - cy) * q) / q
    tile, rx, ry = _gauss_tile(OUT_H * sigma, aspect, fg, bg, fx, fy)

    if warn:
        over = clip_overhang(cx, cy, rx, ry)
        if any(over):
            _warn_clip(dx, dy, cx, cy, rx, ry, over)

    x0, y0 = cx - rx, cy - ry
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(OUT_W, cx + rx + 1), min(OUT_H, cy + ry + 1)
    if x1 > x0 and y1 > y0:
        sub = tile[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        np.maximum(img[y0:y1, x0:x1], sub, out=img[y0:y1, x0:x1])
    return img


_warned_clip = None


def _warn_clip(dx, dy, cx, cy, rx, ry, over):
    """Complain once per distinct clipping situation, not 30 times a second."""
    global _warned_clip
    key = (round(dx, 2), round(dy, 2))
    if key == _warned_clip:
        return
    _warned_clip = key
    l, t, r, b = over
    print(f"render: CLIPPED at dx={dx:+.2f} dy={dy:+.2f} -- centre=({cx},{cy}) "
          f"half=({rx},{ry}) overhangs L{l} T{t} R{r} B{b}. The visible centroid "
          f"no longer matches the commanded position, so any measurement taken "
          f"here is wrong. Fix neutral_y/range_y in calib.json or shrink sigma.",
          flush=True)


# ---------------------------------------------------------------- test patterns
# Used to measure the tracker's transfer function against the SENSOR ADJUSTMENT
# screen, which renders the tracker's own binary image and its head estimate.

def pattern_blob(dx, dy, r=0.10, fg=FG_LEVEL, bg=BG_LEVEL):
    """A single bright disc at a known position: maps our image coords -> the
    game's red dot, and tells us whether it tracks a blob at all."""
    img = blank(bg)
    cx = int(OUT_W * (0.5 + 0.5 * dx * 0.8))
    cy = int(OUT_H * (0.5 + 0.5 * dy * 0.8))
    cv2.circle(img, (cx, cy), int(OUT_W * r * 0.5), fg, -1)
    return img


def pattern_level(level):
    """A flat field. Sweeping `level` finds any global threshold."""
    return blank(level)


def pattern_split(level_a, level_b):
    """Left half at one luma, right half at another: isolates a pure edge with
    no shape at all -- does the tracker chase edges by themselves?"""
    img = blank(level_a)
    img[:, OUT_W // 2:] = level_b
    return img


def pattern_bars(n=8, fg=FG_LEVEL, bg=BG_LEVEL):
    """Vertical bars: lots of equally-strong edges. If the tracker locks onto
    these it is edge-driven and background clutter really does hurt it."""
    img = blank(bg)
    w = OUT_W // (n * 2)
    for i in range(n):
        x = i * 2 * w
        img[:, x:x + w] = fg
    return img


# ------------------------------------------------------------ calibration check

def check_calib(sigma=0.085, aspect=1.0, calib=None):
    """Is the current calibration safe, i.e. never clips at full deflection?

    Returns (ok, report). A calibration that clips is worse than useless: the
    visible centroid stops following the command near the limits, so every
    measurement taken there is silently wrong and any fit through it is a fit
    through an artefact. This is exactly what happened to the dy axis.
    """
    c = dict(CALIB if calib is None else calib)
    _, rx, ry = _gauss_tile(OUT_H * sigma, aspect, FG_LEVEL, BG_LEVEL)

    up = c.get('range_y_up', c['range_y'])
    down = c.get('range_y_down', c['range_y'])
    lines, ok = [], True
    for axis, size, half, neutral, rng in (
            ('x', OUT_W, rx, c['neutral_x'], (c['range_x'], c['range_x'])),
            ('y', OUT_H, ry, c['neutral_y'], (up, down))):
        lo = size * (neutral - rng[0])
        hi = size * (neutral + rng[1])
        safe_lo, safe_hi = float(half), float(size - half)
        bad = lo < safe_lo or hi > safe_hi
        ok = ok and not bad
        max_up = neutral - safe_lo / size
        max_down = safe_hi / size - neutral
        lines.append(
            f"  {axis}: centre spans {lo:6.1f}..{hi:6.1f} px, must stay within "
            f"{safe_lo:.0f}..{safe_hi:.0f}  {'CLIPS' if bad else 'ok'}\n"
            f"     at neutral_{axis}={neutral:.3f}, max up {max_up:.3f} "
            f"(using {rng[0]:.3f}), max down {max_down:.3f} (using {rng[1]:.3f})")
    lines.append(f"  blob half-size {rx} x {ry} px at sigma={sigma}")
    return ok, '\n'.join(lines)


if __name__ == '__main__':
    import sys
    sigma = float(sys.argv[1]) if len(sys.argv) > 1 else 0.085
    good, report = check_calib(sigma)
    print(f"calib.json: {CALIB}")
    print(report)
    print("VERDICT:", "safe -- nothing clips at full deflection" if good else
          "UNSAFE -- the target leaves the frame; re-centre before measuring")
    raise SystemExit(0 if good else 1)
