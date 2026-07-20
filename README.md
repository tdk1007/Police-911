# Police 24/7 (PAL) — Body-Motion + Light-Gun Rig · Runbook

Everything in this folder is built and pre-tested. What's left for you is the
physical part: drop in your BIOS, plug in the camera and gun, mount the IR
emitters, and calibrate. Every fork is pre-solved — if a step fails, the
fallback is already built and one flag away.

**The bottom line from the research + disc forensics** (this changed everything):

- The PAL disc's own camera driver (`WEBCAM_N.IRX`, extracted from your rip and
  disassembled) accepts exactly USB VID `05A9` with PID `0511/A511/0518/A518`
  (OmniVision OV511 family). **PCSX2 has emulated precisely that device since
  2022** — USB device "Webcam (EyeToy)" subtype **"Konami Capture Eye"**
  presents VID `05A9` PID `A511` and speaks OV511+ protocol. Police 24/7 was
  the game it was written for. So the *authentic* in-game motion sensing
  (graduated lean/peek, camera minigame) is the primary path, fed by your
  Insta360.
- The game aims with a **USB mouse** (`USBMOUSE.IRX` on disc). The "gun
  controller" it mentions is a controller-port Justifier which PCSX2 doesn't
  emulate — irrelevant: your OpenFIRE gun in absolute-mouse mode drives
  PCSX2's emulated **HID Mouse** on the second USB port. The game has a
  built-in mouse aim-calibration screen ("Aim at the center of the target and
  shoot") and a "Target cursor speed" setting — that's how we get gun-accurate
  aim out of a relative-mouse device.
- If the authentic camera path hiccups (e.g. the PAL build's camera check is
  fussier than the tested build), the **bridge fallback** is already built:
  `bridge\police247_bridge.py` watches you through the webcam, and while you
  physically duck it holds **K = pad Square = the game's cover button**. Same
  body motion, same game response, zero camera emulation involved. It also has
  a UDP mode for your iPhone-ARKit pipeline.

---

## What's in this folder

| Path | What it is |
|---|---|
| `Play Police 24-7.bat` / `Play-Police247.ps1` | One-shot launcher (BIOS check → ini patch → optional OBS/bridge → PCSX2 fullscreen). Tested in all modes. |
| `PCSX2\` | PCSX2 **2.6.3** portable, preconfigured (`inis\PCSX2.ini`): USB1 = Konami Capture Eye, USB2 = HID Mouse, DualShock2 on keyboard with **Square = K**. |
| `PCSX2\bios\` | **← put your PS2 BIOS dump here** (see Step 1). |
| `bridge\police247_bridge.py` | Head-tracking motion bridge (fallback motion path + iPhone UDP mode). Self-tested (`--selftest` passes). |
| `bridge\iphone_sender_example.py` | UDP protocol example/tester for the iPhone path. |
| `extracted\` | The disc's IRX drivers + ELF (forensic reference). |
| `Police 24-7 (Europe)...\*.bin` | Your game rip — the launcher boots the `.bin` directly (PCSX2 doesn't parse `.cue`, and this single-track disc needs nothing from it). |

---

## Setup, start to finish

### Step 1 — BIOS (2 min) — ✅ DONE & BOOT-VERIFIED
A Europe BIOS (`ps2-0230e-20080220.bin`) is installed in `PCSX2\bios\` and
wired into the config. **Verified 2026-07-02: the game boots with it and the
PAL disc accepted the emulated Konami Capture Eye — PCSX2 reached the game's
SENSOR ADJUSTMENT (camera) screen.** The region-lock worry is dead.

### Step 2 — Camera: make the Insta360 Link 2C a dumb fixed camera (5 min)
1. Plug the Link 2C into a **USB port on the PC**, positioned per
   [Placement](#camera-placement) below.
2. Install **Insta360 Link Controller** (Windows):
   <https://www.insta360.com/download/insta360-link2c>
3. In Link Controller, with the camera selected:
   - **Auto Framing: OFF** (bottom control bar toggle).
   - **Gesture Control: OFF** — critical: the palm-up gesture toggles Auto
     Framing *in camera firmware even with no software running*, and a person
     playing an arm-waving gun game will show palms constantly.
   - Zoom at **1×**.
   - Image panel: **HDR OFF**, then set exposure manually (ISO/Shutter) so the
     picture doesn't pump when the TV flashes. Aim for a bright, low-noise
     image of your play spot at night-play lighting.
4. Close Link Controller's preview when done (only one app can hold the
   camera). The framing state lives in camera firmware; persistence across
   reboots isn't officially documented, so **verify the stream is full-frame
   at the start of a session** (any camera app, 2 seconds). If it ever comes
   back zoomed: open Link Controller, toggle Auto Framing off again.

### Step 3 — Gun: OpenFIRE firmware + profile (10 min)
1. **Flash firmware v6.2** (if not already on it): hold BOOTSEL while plugging
   the RP2040 in, drop
   [`OpenFIREfw.rpipico.uf2`](https://github.com/TeamOpenFIRE/OpenFIRE-Firmware/releases/download/v6.2/OpenFIREfw.rpipico.uf2)
   (or `OpenFIREfw.generic.uf2` for non-Pico boards) onto the `RPI-RP2` drive.
2. Get the **OpenFIRE App v3.0.3**:
   [`OpenFIREapp-win64.zip`](https://github.com/TeamOpenFIRE/OpenFIRE-App/releases/download/v3.0.3/OpenFIREapp-win64.zip).
3. In the App, on your Police 24/7 profile:
   - IR layout: **Square** (double lightbar — 2 LEDs top + 2 bottom) if that's
     your build; Diamond if you built 4 single points. Match your hardware.
   - Leave output as the default **absolute mouse + keyboard** (this is
     OpenFIRE's normal mode — the OS cursor jumps to where you point; no
     serial `M0x…` mode switching needed).
   - Button map: **Trigger → Mouse Left** (shoot). Map a comfortable
     side/pump button → **Keyboard K** (manual duck — works as a backup even
     in camera mode). Map two more buttons → **Enter** (Start) and
     **Backspace** (Select) for menus. A-button → **Mouse Right** (the game
     lets you configure mouse buttons in its own menu).
4. Windows check: the gun enumerates as **"FIRECon"** (VID F143). Point at the
   screen — the Windows cursor should snap to your aim.

### Step 4 — IR emitters on the TV (hardware)
- Emitters bracket the **full physical screen**, not the 4:3 game rectangle.
  (The pillarbox is handled downstream: gun calibration + the game's own aim
  calibration absorb it. Gun-side "4:3 correction" modes exist but are for
  legacy resolution-switching apps — leave OFF.)
- **Square layout**: LED pairs centered at **30% and 70% of screen width**,
  one bar along the top edge, one along the bottom (on the bezel or just
  above/below it). Diamond layout: midpoints of all four edges.
- At couch distance on a big 4K TV, use the recommended **OSRAM SFH 4547**
  emitters (5.6 Ω resistors); if you're >2.5 m away, 2 LEDs per point helps.
- Sanity check: OpenFIRE App → IR test/camera view — from your play position,
  all 4 points visible across your whole aiming sweep, including when you
  duck low. If the bottom bar vanishes when you crouch, angle it up slightly.
- **Displays: while playing, make the TV the ONLY active display**
  (Win+P → "Second screen only" or unplug the monitor). OpenFIRE's absolute
  mouse spans the whole *virtual desktop* — a second monitor skews aim.

### Step 5 — First launch
Double-click **`Play Police 24-7.bat`**. That runs the authentic camera path:
Insta360 → PCSX2's emulated Konami Capture Eye → the game's own motion
sensing. PCSX2 starts fullscreen and boots the PAL disc (50 Hz — normal for
this release).

- If PCSX2's camera pick is wrong, fix it once in PCSX2:
  `Settings → USB → Port 1` — Device "Webcam (EyeToy)", Subtype **"Konami
  Capture Eye"**, Device = your camera in the dropdown (its exact DirectShow
  name). Port 2 stays "HID Mouse" with Pointer bound.
- Keyboard while playing: **arrows** = d-pad, **Enter** = Start,
  **Backspace** = Select, **Space** = Cross, **K** = Square (cover),
  T/C = Triangle/Circle, WASD = left stick.

### Step 6 — In-game setup (once)
1. The game asks **"Would you like to set up the camera?"** → yes. Follow its
   flow from your play spot: it captures your **standing position**, sets
   **movement sensitivity**, and shows a red light that should **follow your
   head**. Use **VIEW POINT CHECK** to see the play area it perceives — your
   head must stay inside it standing, leaning, and fully ducked.
2. Options → **USB mouse settings**: run the calibration target — **aim the
   gun at the center of the target and pull the trigger** (reset with any
   non-shoot button if you fumble). Then set **Target cursor speed** so that
   sweeping the gun from the left edge of the *game image* to the right edge
   moves the crosshair exactly one full screen. Err slightly fast: overshoot
   self-corrects at the edges (both the game cursor and your aim clamp), too
   slow permanently lags.
3. Button config: confirm Square = duck/cover works (press K, or duck if the
   camera path is live — cover should trigger).

That's it. You're playing.

---

## Camera placement

- **Position**: centered on top of the TV (or just below it), lens facing your
  play spot, level or tilted down a few degrees.
- **Distance**: stand **2–3 m** from the TV. The Link 2C's 67° horizontal FOV
  covers ~3.3 m wide at 2.5 m — your full duck-to-stand range fits with room
  to lean both ways.
- **Framing** (check in any camera app or the bridge preview): your head near
  the top quarter of frame when standing; your head **still in frame at full
  crouch**; nothing but you moving in the visible background (no doorway with
  foot traffic, no fan, no TV reflection in glass behind you).
- **Lighting**: a constant room light source on you (floor/ceiling lamp), not
  just TV glow. The game's motion detection ultimately sees an **80×64
  grayscale** image — it needs body-vs-background contrast, not resolution.
  Wear something that contrasts with the wall behind you.

## Motion-bridge calibration (fallback path)

Run `Play Police 24-7.bat -Motion bridge` (or run the bridge alone:
`python bridge\police247_bridge.py`). In the preview window:

1. **B** → step out of frame for ~2 s (it learns the empty room; do this with
   the game already running so TV glow is part of the learned background).
2. Stand at your play spot → **S** (records standing head height; auto-places
   the duck line 22% of frame height below your head).
3. Crouch to where "in cover" should begin → **D** (sets the duck line
   exactly there). Fine-tune with **[** / **]**.
4. Duck a few times: the HUD flips standing/DUCKED and K is held while down.
   Config auto-saves (`bridge\bridge_config.json`); next time just launch and
   play — recalibrate only if you rearrange the room.
5. `--no-preview` once calibrated. The key only registers while the PCSX2
   window has focus (it always does during play).

**iPhone-LiDAR path**: `Play Police 24-7.bat -Motion bridge -BridgeSource udp`
— the bridge listens on UDP **47911** for `{"duck": true/false}` or
`{"head_y": 0.0-1.0}` JSON datagrams (≥15 Hz; 0.5 s silence fail-safes to
standing). Point your existing ARKit-over-UDP streamer at it — schema and
adaptation notes are in `bridge\iphone_sender_example.py`, which is also a
LAN tester (hold D to duck from another machine).

## OBS normalization layer — ✅ INSTALLED, CONFIGURED, AND NOW THE DEFAULT

Direct Link-2C → PCSX2 capture was tested 2026-07-02 and is **broken by
design**: the 2C has no 4:3/320×240 modes, so PCSX2's 320×240 request comes
back stretched and cropped. The fix is installed and validated end-to-end:

- OBS Studio 32.1.2 is installed with a pre-seeded **Police247** profile
  (640×480 4:3 canvas @30) and **Police247** scene collection ("EyeToy" scene
  = your Insta360, center-cut from 16:9 to 4:3).
- A 320×240 DirectShow capture from "OBS Virtual Camera" was verified clean,
  native, and undistorted — exactly what PCSX2's Capture Eye consumes.
- **The launcher now uses this path automatically** whenever OBS is installed
  (no flag needed). `-CameraName "<device>"` forces a direct device instead.

Bonus: the bridge and PCSX2 can share the camera through OBS if ever needed
(both can read the virtual camera; only one app can hold the physical one).

---

## If it breaks → the fix

| Symptom | Cause | Fix (already built) |
|---|---|---|
| Launcher: "NO PS2 BIOS FOUND" | Nothing in `PCSX2\bios` | Step 1. Any `scph*.bin`/`ps2*.bin` ≥512 KB is picked up automatically. |
| Game: **"USB camera is not connected."** | PCSX2 device dropdown empty/wrong; OBS not running; Link Controller holding the camera | Close Link Controller. PCSX2 `Settings → USB → Port 1`: Webcam (EyeToy) / **Konami Capture Eye** / device "OBS Virtual Camera" (launcher sets this). Still dead → `-Motion bridge` — full body-duck gameplay preserved. |
| Camera image stretched / zoomed-in in game | Direct Link-2C capture (no 4:3 modes) — PCSX2 mangles the 16:9 stream | Fixed & now default: launcher routes through OBS Virtual Camera (640×480 4:3 center-cut, validated). Just run the .bat without `-CameraName`. |
| Camera detected, red light doesn't follow head / erratic | Contrast/lighting too poor at 80×64 | Add a lamp on the player, kill HDR/auto-exposure in Link Controller, contrasting clothing, re-run in-game camera setup. |
| Image zooms/crops mid-session | Auto Framing re-enabled (palm gesture or persistence quirk) | Link Controller: Auto Framing OFF, **Gesture Control OFF**. Verify full-frame at session start. |
| Gun moves cursor but in-game crosshair drifts from aim | Relative-mouse scaling mismatch | In-game **USB mouse settings**: re-run the aim-at-target-center calibration; tune **Target cursor speed** (full gun sweep across the 4:3 image = full crosshair travel). Sweep into a screen corner any time to hard-resync. |
| Cursor flies off / aim skewed badly | Second monitor active (absolute mouse spans virtual desktop) | Win+P → TV as only display. |
| Gun doesn't move the Windows cursor at all | Not calibrated / IR points not visible | OpenFIRE App: recalibrate the profile at your play distance; check all 4 IR points visible in the App's IR view, incl. when ducked. |
| Game: **"Gun controller is not connected."** | Refers to the controller-port Justifier (not emulated) | Expected — ignore. Aiming runs on the USB mouse path. |
| Mouse/gun ignored by game | USB port probing order | Swap devices: PCSX2 Settings → USB → Port 1 = HID Mouse, Port 2 = Capture Eye (or edit `[USB1]`/`[USB2]` in `PCSX2\inis\PCSX2.ini`). |
| Camera works alone but dies when mouse also connected (or vice-versa) | Untested-in-the-wild combo (no public report of both at once) | Same port swap as above; if genuinely exclusive, run camera in-game + gun, and duck via camera; or `-Motion bridge` + gun — motion and gun both stay functional in every branch. |
| Bridge: no duck on duck | Background stale / duck line wrong | Preview window: **B** (relearn, step out of frame), **S** standing, **D** at crouch depth. Check the yellow head dot tracks you in the mask window. |
| Bridge duck does nothing in game | PCSX2 lost focus | Click the PCSX2 window. (The launcher starts PCSX2 last so it has focus.) |
| Game speed/audio weird | It's a 50 Hz PAL title | Normal. Don't force 60 Hz — the camera timing and game logic are 50 Hz native. |

## Fallback ladder (all pre-built)

1. **Authentic**: Insta360 → emulated Capture Eye → in-game motion sensing (graduated lean!) + OpenFIRE gun. `Play Police 24-7.bat`
2. **Authentic + normalized feed**: same, camera through OBS. `-Obs`
3. **Bridge**: webcam head-tracking → physical duck = cover button + gun. `-Motion bridge`
4. **iPhone LiDAR**: ARKit pose over UDP → same bridge → cover + gun. `-Motion bridge -BridgeSource udp`
5. **Floor**: gun only, duck on K (or a gun button mapped to K). `-Motion none`

## Sources (non-obvious config details)

- PCSX2 Capture Eye emulation: PCSX2 PR **#5382** (merged 2022-01-24, OV511+/
  VID 05A9 PID A511, written & tested against Police 24/7) and PR #11721
  (assert fix); `pcsx2/USB/usb-eyetoy/` (subtype/ini keys), `usb-hid.cpp`
  (HID Mouse = relative deltas from absolute host cursor), `USB.cpp`
  (`[USB1]/[USB2]`, `Type`, `webcam_subtype`, `webcam_device_name`,
  `hidmouse_*` — verified against source and the 2.6.3 binary).
- Disc forensics (this folder, `extracted\`): `WEBCAM_N.IRX` probe accepts
  VID 05A9 / PID 0511·A511·0518·A518; `USBMOUSE.IRX` = standard USB HID mouse;
  gun = controller-port device; ELF strings confirm in-game USB-mouse
  calibration screen, target-cursor-speed setting, and head-tracking setup
  flow.
- Gun protocol reality: PCSX2 issues #7889 (open — no Justifier emulation),
  #10863 (absolute-mouse request, closed "not planned"); nixxou's lightgun
  fork covers GunCon2 games only — hence the HID-mouse + in-game-calibration
  route (same as the documented 2023 full playthrough by shadoweez).
- OpenFIRE: firmware v6.2 / App v3.0.3 release assets; TinyUSB descriptors
  (VID F143 "FIRECon", absolute mouse 0–32767); emitter placement 30%/70%
  from the App's alignment assistant source.
- Insta360 Link 2C: official manual (Auto Framing = firmware digital crop,
  palm gesture, no gimbal on 2C); Link Controller v2.2.1 image controls.

**Steps that need your hardware to confirm** (each already has its pre-built response above):
1. PAL disc accepts the emulated Capture Eye (expected — PID matches its own
   driver; if not → fallback 3).
2. Link 2C negotiates directly with PCSX2's DirectShow capture (if not →
   fallback 2/`-Obs`).
3. Camera + HID Mouse detected simultaneously (no public precedent either
   way; if not → port swap, then fallback 3).
4. Auto-framing state persists across reboots (if not → 5-second Link
   Controller check at session start).
