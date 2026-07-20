"""Frame synthesis for the Police 24/7 synthetic camera.

Everything the game sees is generated here. Two hard constraints, both verified
against the game's own code (see re/RE_FINDINGS.md):

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


def place(dx, dy):
    """Normalised command -> pixel position of the head centre."""
    reload_calib()
    cx = int(OUT_W * (CALIB["neutral_x"] + dx * CALIB["range_x"]))
    cy = int(OUT_H * (CALIB["neutral_y"] + dy * CALIB["range_y"]))
    return cx, cy


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
    cv2.ellipse(img, (cx, cy), (int(OUT_W * head_r * 0.62), int(OUT_H * head_r)),
                0, 0, 360, fg, -1)
    return img


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
