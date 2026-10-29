# Roadmap — arcade-style full-body play

Goal: stand ~2 m back, lean wide, squat for cover, and have the in-game cop do
the same. The PS2 port's tracker was tuned for a seated player making small
movements; the arcade cabinet read body position off overhead sensors.

Last updated 2026-09-13. Supersedes the 2026-07-02 roadmap, which predated all
of `camera-tracking/re/` and `camera-tracking/synth/` and still referenced the
`police247-rig/` directory that was folded into `camera-tracking/` in `72ddd2b`.

## VR immersion (Stage 2): open items

Design intent (user, 2026-10-21): you are **in the world**, not looking at a floating display. The current
state and test order are in `vr/IMMERSIVE.md` and `HANDOFF.md`.

- **Gun model on the motion controller** (added 2026-10-21), like other VR shooters: you see a pistol in
  your hand that tracks the controller, instead of only the game's flat green aim ring.
  - **Asset:** a free pistol model, low-poly is fine. Before use, check its licence:
    - On Fab (Epic), some free listings are restricted to Unreal Engine; we need one licensed for use in
      any engine.
    - CC0 sources avoid the question: Kenney, Quaternius, Poly Haven, and CC0/CC-BY models on Sketchfab.
    - Keep the licence file next to the asset.
  - **Rendering:** draw it in the pcsx2-vr fork (D3D11), into each eye's texture before the SteamVR submit.
    - Use the right controller's aim pose and each eye's view/projection. The game has no idea the gun
      exists.
    - Draw it on top of the scene. An optional depth test against the game's Z buffer (FBP 256) would let
      walls hide the gun.
    - Load glTF/OBJ with a small loader (cgltf/tinyobjloader). Simple lighting is enough.
  - **Controller pose:** the fork reads it straight from OpenVR (it already calls `WaitGetPoses`), so there
    is no bridge round trip.
  - **Alignment:** add a grip offset/rotation in `[VR]`, tuned in the headset so the model sits in the hand
    and its barrel lines up with the shot ray (`frame_bridge.aim_target`, `AIM_DIST_M`).
  - **Part of this feature, not optional** (user, 2026-10-21):
    - **Muzzle flash** at the barrel tip on each shot: a short additive sprite or light burst, in both eyes.
      - The fork needs to know when the trigger fires: the bridge sets a "fired" slot in EE RAM, or the
        fork reads the trigger action from OpenVR itself.
    - **Haptic pulse on fire** on the right controller.
      - The bridge already has `VR.buzz()`; call it on each trigger edge, with a stronger and sharper
        pulse than the UI buzzes.
    - **Sights instead of the flat ring:** a short laser from the barrel, or glowing tritium sights on the
      model.
      - Pick one in the headset, and keep the other as a `[VR]` option.
      - Either way, it must agree with the shot ray.
    - **Hide the game's own green crosshair ring** in VR, once the gun's sights replace it. Keep it as a
      `[VR]` option for debugging aim.
- **HUD placement:** the timer, ammo and ring are drawn flat on each eye with no depth, so they follow your
  head. Pin the HUD at a comfortable distance, or keep only the essentials.
  - Headset report (2026-10-29): the reload magazine graphic (lean in to cover) comes up huge and at the
    edge of view. Likely cause: the 2D HUD still spans the full 512-wide screen, but in VR that screen now
    covers the widened FOV (tan 1.76 vs stock 0.64), so HUD sprites are about 2.8x too big. Fix idea:
    scale and centre the HUD draws to the stock-frame part of the view.
- **Menus and title screen:** these have no 3D world behind them. Pick between a head-locked panel, a
  simple virtual room, or a flat world-locked screen (the last one is the "floating display" the design
  avoids).
- **Head-movement parallax:** small head translation goes into the view, separate from the game's
  lean/duck cover moves.
- **Comfort for the scripted camera moves** (rails and lean): vignetting during big moves.

## Two ways in

**Video injection** (`camera-tracking/synth/`) — draw an idealised target into a
virtual camera and let the game's own tracker find it. Proven: the game locks
onto a fully synthetic head. But it is a lossy round trip, and the tracker's
latency, smoothing and motion requirement all stay in the loop.

**Memory hook** (`camera-tracking/re/ram/`) — write the head position straight
into the game's own variables, so the camera image stops mattering. **This now
works**, and it is the primary path: the mapping is linear, exact, repeatable
and needs no calibration.

Video injection remains as the fallback for running an unpatched game.

## Done

- Game boots under PCSX2 2.6.3; the PAL disc accepts the emulated Konami
  Capture Eye and reaches SENSOR ADJUSTMENT.
- OBS 4:3 centre-cut path for a real camera; letterbox root-caused and fixed.
- Camera pipeline reverse-engineered: luminance-only conversion, the five
  accepted geometries, the IOP/SIF RPC path (`camera-tracking/re/RE_FINDINGS.md`).
- Synthetic feed proven end-to-end, and the game's tracker follows a fake head.
- Duck/cover fallback that needs no camera at all (`camera-tracking/bridge/`).
- **The tracker's output is located and drivable.** `0x0029F0F8` (head X) and
  `0x0029F0F4` (head Y), unlocked by NOPing two branch guards at `0x001BC808` /
  `0x001BC810`. Linear and exact: r = -0.99922 and +0.99799. Tooling in
  `camera-tracking/re/ram/` (`hook.py`, `pine.py`, `snap.py`, `hunt.py`).
- **Gameplay confirmed.** Driving head position from memory changes the in-game
  cover/lean view during a stage, graduated rather than binary. This was the
  project's blocking unknown. See `camera-tracking/GAMEPLAY_VERIFY.md`.
- Vertical-axis dead band root-caused (frame clipping, not a tracker quirk) and
  fixed; guard rails added. `camera-tracking/synth/CALIBRATION.md`.
- Launcher gained `-Motion synth` and `-Pine`.

## Next, in order

1. **Map the lean response finely.** Three sampled positions confirmed the
   mechanic exists; the in-between behaviour is unmapped. How far must a lean
   travel to count as peeking versus fully out of cover?
2. **Confirm the vertical axis in a stage.** Only `head_x` was exercised during
   gameplay. Does `head_y` engage a distinct duck/cover state?
3. **Confirm it is defensively meaningful** — that enemy fire actually misses
   while leaned, rather than the view merely shifting.
4. **Build the live pipeline.** `pose_source.py` (mediapipe on the Link 2C) ->
   `transfer.py` (built and self-tested) -> `hook.set_head` over PINE.
   Continuous by default, arcade zone-snap as a toggle.
5. Fold it into the launcher as a finished motion mode and update the RUNBOOK.

Note what is no longer on this list: the synthetic-camera calibration. The
memory hook made it unnecessary — the mapping is linear and exact with no
geometry to solve. The video path stays as a fallback for anyone who wants to
run unpatched.

## Needs the user

The Link 2C is currently unplugged — no camera devices enumerate. None of steps
1–3 need it, because the synthetic feed stands in for a body. Step 4 does:

- Plug the camera in, aimed at the play area, and re-run
  `camera-tracking/obs/Setup-Camera.ps1` — the stored OBS device ID encodes the
  USB port and will not match after a replug.
- Run `capture_pose.py` and hold four poses (neutral, lean left, lean right,
  squat). This produces `capture_pose.json`, the movement envelope the transfer
  function is fitted from. It has never been captured, and cannot be synthesised.
- The end-to-end play test.

## Parked

- **Arcade / MAME. Closed.** Verified by reading `src/mame/konami/viper.cpp`
  (3253 lines) directly, not a summary:
  - All eight p911 variants are `MACHINE_NOT_WORKING` (lines 3228-3234),
    including `p911ed` "Police 24/7 (ver EAD)", the matching regional title.
  - The driver's TODO, verbatim (lines 81-83): *"needs a proper way to dump
    security dongles, anything but p9112 has placeholder ROM for ds2430"* and
    *"Voodoo 3 has issues with LOD minimums"*.
  - **No motion input is wired to p911.** Its port block (2074-2105) has DIPs,
    Gun Trigger and GUN0-GUN3; the base `viper` block it includes has only
    IN0-IN7, GUN0-GUN3, AN0-AN3.

  Two corrections to an earlier, sloppier version of this entry. (1) The driver
  is NOT free of sensor support — it has `SENSOR1`-`SENSOR4`, 24 sensors over 8
  "sensor bars", read via `ppp_sensor_r()` at `0xff400200`; that is wired to
  Para Para Paradise, not to p911. The machine config p911 uses is called
  `viper_fullbody`, but that only swaps speaker/DMADAC audio routing and adds no
  tracking. The accurate statement is that the motion path for these games is
  *unemulated and unverified* (cf. the UART TODO "likely connects to sensor
  motion based games"), not that it is absent. (2) The Voodoo LOD comment cites
  `mocapglf`'s card check, so it should NOT be asserted as the cause of any
  particular missing-texture symptom.

  Either way the conclusion stands: no body tracking is obtainable from MAME's
  p911, and asset transplanting between the PS2 and arcade builds is impossible
  (different CPU, renderer and asset containers). The user has no romset and
  does not own the PCB; do not source one.
- **Visual upgrades: DECLINED by the user 2026-09-13.** PCSX2 texture
  replacement (`DumpReplaceableTextures` / `LoadTextureReplacements`, keys
  confirmed present in the 2.6.3 build) would work and needs only the user's own
  disc, but they do not want the PS2 game's textures changed. Do not re-propose
  it. Internal-resolution upscaling was not ruled on either way.
- Extra time / lives via pnach — codes never retrieved.
- OpenFIRE gun build, QMamehook recoil, 2P, CRT shader.
