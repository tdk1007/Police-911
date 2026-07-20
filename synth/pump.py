"""Drive the virtual camera from a live control file.

The frame is ALWAYS moving. That is deliberate: if the game's tracker does any
temporal differencing (a 2003 EyeToy-era tracker very likely does), a static
image tells it nothing and its estimate drifts or decays -- so a still frame
would give us a meaningless reading. Two motions are available:

  jitter : a small oscillation around the commanded position, so the mean
           position is still what we asked for. Use this while SAMPLING.
  anim   : a large sweep, to watch whether the tracker actually follows.

control.json:
  {"mode":"player","dx":0,"dy":0,"fg":255,"bg":0,"filled":true,
   "head_r":0.11, "shoulder_w":0.34,
   "jitter":0.03, "jitter_hz":3.0,
   "anim":"none"|"sweep_x"|"sweep_y"|"circle", "amp":0.8, "period":4.0}
"""
import json, math, os, sys, time
import pyvirtualcam
from pyvirtualcam import PixelFormat

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render

CONTROL = os.path.join(HERE, 'control.json')
DEFAULT = {"mode": "player", "dx": 0.0, "dy": 0.0, "fg": 255, "bg": 0,
           "filled": True, "head_r": 0.11, "shoulder_w": 0.34,
           "jitter": 0.03, "jitter_hz": 3.0,
           "anim": "none", "amp": 0.8, "period": 4.0}


_last_err = None


def load():
    """Read control.json.

    utf-8-sig, NOT utf-8: PowerShell 5.1's `-Encoding utf8` writes a BOM, which
    makes json.load throw. This used to fall back to DEFAULT *silently*, so the
    pump rendered a static frame while we believed it was sweeping. Never
    swallow the error again -- print it once.
    """
    global _last_err
    try:
        with open(CONTROL, encoding='utf-8-sig') as f:
            c = dict(DEFAULT)
            c.update(json.load(f))
            _last_err = None
            return c
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        if msg != _last_err:
            print(f"pump: CONTROL FILE UNREADABLE ({msg}) -- using defaults", flush=True)
            _last_err = msg
        return dict(DEFAULT)


def offset(c, t):
    """Where the silhouette is at time t, given the commanded position."""
    dx, dy = float(c["dx"]), float(c["dy"])
    anim, amp = c.get("anim", "none"), float(c.get("amp", 0.8))
    per = max(0.2, float(c.get("period", 4.0)))
    ph = 2 * math.pi * t / per
    if anim == "sweep_x":
        dx = amp * math.sin(ph)
    elif anim == "sweep_y":
        dy = amp * math.sin(ph)
    elif anim == "circle":
        dx = amp * math.sin(ph)
        dy = amp * math.cos(ph)
    else:
        # no sweep: keep it alive with a small jitter about the commanded point
        j = float(c.get("jitter", 0.0))
        if j:
            dx += j * math.sin(2 * math.pi * float(c["jitter_hz"]) * t)
            dy += j * 0.5 * math.cos(2 * math.pi * float(c["jitter_hz"]) * t)
    return max(-1.0, min(1.0, dx)), max(-1.0, min(1.0, dy))


def build(c, dx, dy):
    mode, fg, bg = c.get("mode", "player"), int(c["fg"]), int(c["bg"])
    if mode == "player":
        return render.draw_player(dx, dy, fg=fg, bg=bg,
                                  filled=bool(c["filled"]),
                                  head_r=float(c["head_r"]),
                                  shoulder_w=float(c["shoulder_w"]))
    if mode == "head":                      # head only -- no torso mass at all
        return render.draw_head_only(dx, dy, fg=fg, bg=bg,
                                     head_r=float(c["head_r"]))
    if mode == "blob":
        return render.pattern_blob(dx, dy, fg=fg, bg=bg)
    if mode == "level":
        return render.pattern_level(fg)
    if mode == "split":
        return render.pattern_split(bg, fg)
    if mode == "bars":
        return render.pattern_bars(fg=fg, bg=bg)
    return render.blank(bg)


def main():
    t0 = time.time()
    with pyvirtualcam.Camera(width=render.OUT_W, height=render.OUT_H, fps=30,
                             fmt=PixelFormat.BGR, backend='obs') as cam:
        print(f"pump: {cam.device} {cam.width}x{cam.height}@{cam.fps}", flush=True)
        last_desc = None
        while True:
            c = load()
            t = time.time() - t0
            dx, dy = offset(c, t)
            cam.send(render.to_bgr(build(c, dx, dy)))
            cam.sleep_until_next_frame()
            desc = (c["mode"], c["dx"], c["dy"], c["anim"], c["head_r"],
                    c["shoulder_w"], c["fg"], c["bg"], c["filled"])
            if desc != last_desc:
                print(f"pump: {desc}", flush=True)
                last_desc = desc


if __name__ == '__main__':
    main()
