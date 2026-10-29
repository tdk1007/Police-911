# Synthetic camera calibration

How the commanded position `(dx, dy)` becomes pixels, why the vertical axis was
wrong, and what still has to be measured with the game running.

## The mapping

`render.place_f(dx, dy)` is the whole of it:

```
cx = OUT_W * (neutral_x + dx * range_x)     # OUT_W, OUT_H = 640, 480
cy = OUT_H * (neutral_y + dy * range_y)
```

`dx`/`dy` run -1..+1. `calib.json` holds the four constants and is **hot-reloaded
every frame** — deliberately, because restarting `pump.py` while PCSX2 holds the
DirectShow filter kills its capture and the feed freezes. Tune calibration live;
never restart the pump to do it.

## The vertical axis was broken, and it was our bug

`measure.json` recorded the game's tracker dot at five commanded `dy` values:

| dy | −0.8 | −0.4 | 0.0 | +0.4 | +0.8 |
|----|------|------|-----|------|------|
| dot_y | 668.4 | 706.0 | 742.1 | **742.0** | 851.9 |

`dy = 0.0` and `dy = +0.4` read back the same number: a dead band. `ring.py`
nevertheless fitted `dot_y = 100.76*dy + 742.08` straight through it and solved a
neutral of `dy ≈ −0.92`, which is outside the range that was ever sampled.

**Cause: the target was falling off the top of the frame before the game ever
saw it.** With the calibration that shipped (`neutral_y 0.146`, `range_y 0.21`)
and `control.json`'s `head_r 0.18`, `draw_head_only` drew an ellipse of
half-height `480 * 0.18 = 86 px` centred at `cy = 480 * (0.146 + dy*0.21)`:

| dy | commanded cy | overhang off top | visible centroid y |
|----|--------------|------------------|--------------------|
| −0.8 | −10.6 | 96 px | 31.9 |
| −0.4 | 29.8 | 57 px | 50.3 |
| 0.0 | 70.1 | 16 px | 73.7 |
| +0.4 | 110.4 | none | 110.0 |
| +0.8 | 150.7 | none | 150.0 |

A clipped shape's *visible* centroid stops following its commanded centre. The
commanded 161 px of travel arrived as 118 px, and equal `dy` steps produced
visible steps of 18.5, 23.4, 36.3 and 40.0 px — the top of the range compressed
to less than half the sensitivity of the bottom. Measured with
`render_selftest.py`'s centroid routine; reproduce it any time.

So the non-linearity the fit was papering over was ours, not the game's. The
game's tracker may well have its own quirks on this axis, but they cannot be
measured until the target stops leaving the frame.

A second, independent defect made this worse: `probe.grab()` used to return the
*previous* `pcsx2_shot.png` whenever the screenshot failed, because it called
`cv2.imread` without checking that `shot.ps1` had succeeded. A stale screenshot
yields an identical reading — which is also a perfectly good explanation for two
consecutive samples agreeing to 0.1 px. `grab()` now deletes the file first,
checks the exit code, and rejects a shot older than the call. It fails loudly
instead.

## Guard rails now in place

- `render.clip_overhang(cx, cy, rx, ry)` returns how far a shape falls outside
  the frame; `render.is_clipped` is the boolean.
- `draw_gaussian` and `draw_head_only` both call `_warn_clip`, which prints once
  per distinct position rather than 30 times a second.
- `py render.py [sigma]` audits `calib.json` and exits non-zero if any command in
  -1..+1 would clip. Run it before any measurement session.

Against the shipped calibration it says:

```
  y: centre spans  -30.7.. 170.9 px, must stay within 123..357  CLIPS
     at neutral_y=0.146, max safe range_y = -0.110 (currently 0.210)
```

A *negative* maximum safe range: at that neutral, no range fits at all.

## Current calibration

`calib.json` is now a geometrically safe starting point, centred so nothing
clips at full deflection:

```json
{"neutral_x":0.5,"neutral_y":0.5,"range_x":0.30,"range_y":0.22}
```

The previous values are preserved in `calib.json.pre-recentre-2026-09-13`.

**This is not a finished calibration.** It guarantees the target stays in frame;
it does not put the game's head marker inside the game's calibration ring. That
still has to be solved against the running game:

1. Start `pump.py`, boot to SENSOR ADJUSTMENT.
2. `py render.py` — confirm "safe".
3. Re-run `measure.py` with a fine `dy` sweep across the full range, and check
   its `our_head_top` column shows no clipping at any sample.
4. Fit only over the clip-free region. If the game's own response really is
   non-linear once ours is clean, store a lookup table rather than forcing a line.
5. `py check_ring.py --learn` with the dot sitting in the ring, then
   `py check_ring.py` to verify.

## The target shape

Three generations, each fixing what the last one taught us:

- `draw_player` — head and shoulders. **Failed:** the torso carries far more
  bright area than the head, so a centroid-of-bright-mass tracker put its
  estimate on the chest.
- `draw_head_only` — head, no torso. Fixed the chest bug. Still a hard-edged
  ellipse snapped to whole pixels.
- `draw_gaussian` — a soft radial bump at a sub-pixel position. **The default.**
  No torso; positioned to 1/8 px, which matters because the game downsamples our
  640×480 before tracking and quantisation upstream of a downsample shows up as
  stepping; and it degrades gracefully under thresholding as the game's gain
  shifts, instead of vanishing all at once.

`render_selftest.py` measures this rather than asserting it: sub-pixel placement
gives a max linearity residual of **0.06 px** against **0.48 px** for the same
blob forced onto whole pixels.

## Screen coordinates are fractions now

`check_ring.py` used to hardcode `RING = (3481.5, 649.0)` and `measure.py`
`PANEL_Y = (520, 1180)` — screen-absolute coordinates on a 4K desktop, which
became silently wrong whenever the PCSX2 window moved, was resized, or landed on
another monitor.

`shot.ps1` now captures the **client area** (not the window rect, whose borders
change with theme and DPI) and writes `pcsx2_shot.json` describing it.
`probe.to_frac` / `probe.from_frac` convert, and `oracle.json` stores the ring
centre and tolerance as fractions of that client area. `py check_ring.py --learn`
records it; `py check_ring.py` checks against it.
