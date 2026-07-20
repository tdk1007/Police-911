# camera-tracking

Webcam-based duck/lean/dodge detection for **Police 911 / Police 24/7**
under PCSX2 — reconstructing the arcade cabinet's overhead body-position
sensor, which the PS2 port replaced with a special Konami USB camera.

**Status: not started.** This is a placeholder so the two efforts (light
gun vs. this) have separate, non-conflicting directories from day one. Fill
in this README as the design solidifies; keep it as the entry point for
anyone picking this up.

## What this needs to do

PCSX2 exposes a generic camera-input device slot for this game (labeled
"EyeToy" in its USB device list, regardless of what's actually plugged in).
Something has to feed that slot a video stream that the game's own motion
detection reads as duck/lean/cover, the same way it would read the original
Konami "Capture Eye" (model RU035) camera on real hardware.

**Read `../police-247-research-dossier.md` before designing this** — it
already documents several dead ends:
- The **Sony EyeToy itself is reported incompatible** with this game on
  real hardware, despite PCSX2 naming the device slot "EyeToy." What
  matters is the video signal PCSX2 forwards into that slot, not the
  camera's brand.
- No one has publicly demonstrated the camera dodge mechanic working under
  PCSX2 emulation (webcam or OBS Virtual Camera) — this is open territory,
  not a known-working recipe.
- The game is fully playable **without** a camera at all, falling back to
  a button-press duck (Square) — useful as a fallback/comparison mode
  while this is in development.

## Suggested shape (adjust freely)

Mirroring `PoliceGun/`'s layout for consistency, not a hard requirement:

```
camera-tracking/
  README.md          <- this file
  SPIKE.md            <- first-milestone runbook, once there's a plan
  capture/            <- webcam capture + pose/lean detection
  pcsx2-bridge/        <- feeds the detected state into PCSX2's camera device
```

## Integration point with the light gun

The two inputs are independent (different USB devices into PCSX2 — mouse
for aim/fire, camera for dodge) and don't need to share code. See the root
[`PLAY_SESSION.md`](../PLAY_SESSION.md) for how a session using both will
be started together once this exists.
