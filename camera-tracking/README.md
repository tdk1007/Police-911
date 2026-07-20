# camera-tracking

Reconstructing the arcade cabinet's overhead body-position sensor — the
duck/lean/dodge mechanic — for **Police 911 / Police 24/7** under PCSX2. The PS2
port drove this from a special Konami "Capture Eye" USB camera; PCSX2 emulates
that camera, so the job is to feed it the right video (authentic path) or bypass
it with a button press (fallback path).

> **Read [`../police-247-research-dossier.md`](../police-247-research-dossier.md)
> first.** It documents the known dead ends (e.g. the Sony EyeToy is reported
> incompatible on real hardware; no one had publicly demonstrated the camera
> dodge under emulation). What matters is the *video signal* forwarded into
> PCSX2's camera slot, not the brand of camera plugged in.

## Two paths

**1. Authentic camera path (primary)** — make the game's own motion detection
see you, giving graduated lean/peek and the in-game camera minigame.

- **[`re/`](re/)** — reverse engineering of the game's camera pipeline,
  **verified against the binary** (`SLES-50285` + its IOP modules). The findings
  that drive everything else live in [`re/RE_FINDINGS.md`](re/RE_FINDINGS.md):
  the frame path is **luminance-only** (one byte/pixel, color discarded), it
  expects a **320×240 4:3** stream, and the on-disc driver (`WEBCAM_N.IRX`)
  binds **USB VID 05A9 / OV511 family** — exactly what PCSX2's emulated "Konami
  Capture Eye" presents. Run the tools with `py <script>` (start with
  `look.py`, `refs.py`, `api.py`; `mipslib.py` is the shared disassembly core).
- **[`synth/`](synth/)** — synthetic-camera frame generation. Everything the
  game sees is drawn here (`render.py`) to satisfy those constraints, then
  delivered through a virtual-camera sink. Includes the calibration-ring locator
  (`ring.py`), pose capture/measurement (`capture_pose.py`, `measure.py`), and
  the control/calibration state (`control.json`, `calib.json`). This is the
  harness that lets you feed the game a generated head for standing arcade-style
  play.
- **[`obs/`](obs/)** — routes **any** physical webcam into PCSX2 at the required
  4:3 via OBS Virtual Camera (`Setup-Camera.ps1` generates the profile + a
  center-cut 640×480 scene). Use this when driving the game with a real camera
  feed instead of the synthetic one.

**2. Bridge fallback (simple, always works)** — skip the camera entirely.

- **[`bridge/`](bridge/)** — `police247_bridge.py` watches you through a fixed
  webcam (Insta360 Link 2C), finds the top of your silhouette, and **holds the
  duck key** (bound in PCSX2 to pad Square, the game's no-camera cover button)
  while your head drops below a calibrated line. `iphone_sender_example.py`
  shows the UDP path for driving the same duck state from an iPhone (ARKit)
  instead of the webcam. This gives binary duck/cover without the camera
  minigame — the reliable comparison mode while the authentic path is tuned.

## Status

Game camera pipeline reverse-engineered and documented; synthetic-camera
harness and webcam/iPhone duck bridge built and self-tested. **Pending: hardware
validation** on the full rig (real camera + emulated Capture Eye end-to-end).
See the root [`RUNBOOK.md`](../RUNBOOK.md) for wiring this into a play session
alongside the light gun.

## Contributing

The two efforts (`../iPhone Gun/` vs. this) use **disjoint** USB devices into
PCSX2 (mouse for aim/fire, camera for dodge) and don't share code — stay in your
own directory and they won't collide. See [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
Good next steps: tune the synthetic-camera head so the game reads graduated lean
(not just binary duck), and confirm the authentic path survives the PAL build's
camera check on real hardware.
</content>
