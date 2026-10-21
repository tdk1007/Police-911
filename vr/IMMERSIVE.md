# Immersive VR (Stage 2): how it works and how to test it

Built 2026-10-21 without a headset. Everything below the "In the headset" line is untested.

## How to launch
```
.\Play-Police247.ps1 -Immersive
```
This starts SteamVR if it's down. It then boots the **pcsx2-vr fork** (`pcsx2-vr\bin\pcsx2-qtx64-avx2.exe`, with its own portable config) and sets its VR profile:

| Setting | Value |
|---|---|
| `[VR] Mode` | `openvr` |
| `[EmuCore/GS] Renderer` | `3` (D3D11) |
| `upscale_multiplier` | `4` |
| `FrameratePAL` | `90` |
| `VsyncEnable` | `false` |
| `[EmuCore/Speedhacks] EECycleRate` | `3` |

It also starts `frame_bridge.py -v --immersive`, which logs to `vr\bridge.log`.

**Set the headset to 90 Hz.** The emulated vsync is 90 Hz, so a 120 Hz headset would make the two clocks beat against each other.

## The pieces
1. **`camera-tracking/re/ram/vrcam.py`: head rotation and FOV in the game's render view** (code cave at `0x4F0000`, slots at `0x4F8000`). The rotation signs match OpenVR:
   - yaw + = look left
   - pitch + = look up
   - roll + = head tilted left (counter-clockwise)
   The eye offset is +x = right, in game units (about cm). The HUD stays fixed.
   - It also counts gameplay: the six call sites of the fire handler `0x185040` go through a cave at `0x4F0300` that bumps slot `+0x4C` (`play` in `--status`). That handler runs once per sim tick of actual play, in every game mode. Menus, the title and Sensor Adjustment also render through the patched view, so its own `applied` counter can't tell them apart.
2. **`vr90.py`: 90 Hz stereo on the EE.**
   - It runs the main loop twice per 90 Hz vsync: first with eye L and the sim gated to 50 Hz game time, then with eye R and no sim step.
   - It saves and restores the render's one-shot queues, so the HUD draws in every pass.
   - It forces a one-vsync wait.
   - Measured: 180 renders/s, with game speed exact. The EE overclock has to be 300%; at 180% you get 45 Hz per eye. The EE thread uses about 52% of a 9800X3D core.
3. **`vrshot.py`: shots follow the gun.** The game's hit test casts its own ray from its logic camera, with a fixed focal length of 402 in a 512 space. It ignores the head rotation and the wider FOV. Two call sites in the fire handler get the shot coordinates from the bridge instead, computed in the game camera's frame.
4. **The fork** (`vr/pcsx2-vr.patch`; apply it to PCSX2 v2.6.3 and copy `openvr.h` into `3rdparty/include/openvr/`):
   - `GSRendererHW` snapshots each eye framebuffer just before the GS draws over it.
   - It pairs the two eyes from the same EE vsync.
   - `VRSession` submits the pair to SteamVR with `WaitGetPoses` pacing and `Submit_TextureWithPose`.
   - On the EE thread at each vsync, it writes head yaw, pitch and roll, the per-eye IPD offsets and the FOV into the slots.
   - The desktop window shows L | R side by side.
   - **Flat screen outside gameplay:** while vrcam's `play` counter stalls (menus, title, briefings, results), it shows the normal picture on a world-locked SteamVR overlay (4:3, 2.4 m wide, 2.5 m ahead along the recentred forward, at head height) over black eyes. The desktop window shows the normal picture. The log says `VR: gameplay, stereo` / `VR: no gameplay, flat screen`.
5. **`frame_bridge.py --immersive`:**
   - Lean, duck, fire, voice and the grip-hold recenter work as in Stage 1. The recenter also re-zeroes the fork's head yaw.
   - The green ring is projected through the head-rotated view. The shot goes through `vrshot`.
   - It re-installs all three patches after any savestate load or reset.

## Tunables (`pcsx2-vr\bin\inis\PCSX2.ini`, section `[VR]`)
| key | default | what |
|---|---|---|
| `Mode` | off | `off`, `dryrun` (L\|R on the desktop only), `openvr` |
| `SwapEyes` | false | Flip it if the depth looks inside-out |
| `TanH` / `TanV` | 0.635 / 0.443 | The stock frame half-extents. Measured from yaw/pitch image shifts, and the hit-test constant 256/402 = 0.637 agrees |
| `FovMargin` | 1.05 | How far past the eye frusta to render |
| `UnitsPerMetre` | 100 | World scale for the IPD. A full duck is 54.5 units, so 1 unit is about 1 cm |
| `PoseDelay` | 2 | Vsyncs from writing a pose to presenting its frame. This pose goes to SteamVR for reprojection |
| `StereoAfter` / `FlatAfter` | 3 / 15 | Gameplay ticks before switching to stereo, and vsyncs without a tick before switching to the flat screen |
| `FlatDistance` / `FlatWidth` / `FlatAspect` | 2.5 / 2.4 / 1.333 | The flat screen's distance and width in metres, and its picture aspect |
| `Menus` | world | Outside gameplay: `world` (flat screen standing in the room), `head` (fixed in front of the face), `stereo` (no flat screen; menus fill the view). ROADMAP's design intent avoids floating displays, so this is for comparing in the headset |
| `DumpEyes` | false | Debug: write `logs/vr_eye{0,1}.png` every 5 s |

## In the headset: test order
1. **Mirror and stereo.** Launch, then go to the hotel lobby. The desktop window should show L | R, and the fork log (`pcsx2-vr\bin\logs\emulog.txt`) should have the line `VR: OpenVR up ...`. In the headset the game should fill your view.
2. **Comfort.** Turn your head slowly. The world should stay put. If it swims with rotation, `TanH`/`TanV` are off. If it lags or jumps, try `PoseDelay` 1 or 3.
3. **Depth.** Close each eye in turn. If the depth looks inside-out, set `SwapEyes = true`. If the scale feels wrong, change `UnitsPerMetre`.
4. **Aim.** The green ring should sit where the gun points. Shoot enemies with your head turned ±30°. If the ring is right but hits miss, check `vrshot.py --status` (the `used` count goes up per shot).
5. **Lean and duck** should still trigger the cover mechanics.
6. **Flat screen.** Boot to the title or Sensor Adjustment: you should see a flat screen in front of you that stays put when you turn your head. Try `Menus = head` and `stereo` too, and pick one (or decide on a virtual room, see ROADMAP). Start a stage, and it should switch to full stereo. If the screen sits off to one side, hold the grip to recenter, then return to a menu.

## Known gaps
- **Flat screen untested in the headset.** The switching was verified on the desktop (dryrun, 2026-10-21): Sensor Adjustment stays flat, the lobby goes stereo, a stalled play counter goes flat after 15 vsyncs and back. The OpenVR overlay itself (`IVROverlay`, D3D11 texture) has only been compiled. Mid-stage pauses and cutscenes are untested; if they stop the fire-handler ticks, they go flat too.
- **No positional parallax.** Head translation goes to the lean/duck game mechanics, not the view. The view gets rotation, eye offsets and SteamVR reprojection.
- **Eye timing:** each pair is presented about 2 vsyncs after the EE rendered it. Reprojection with the submitted pose should hide that.
- **One unexplained PCSX2 exit** happened right after a savestate load during development. It hasn't reproduced since.
