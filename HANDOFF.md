# Handoff — Police 911 VR effort (updated 2026-10-21)

Start here in a fresh session. The approved plan is in
`C:\Users\tdk10\.claude\plans\ok-i-want-to-sequential-avalanche.md`
(Stage 1 flatscreen VR → Stage 2 6DOF, on **PS2/PCSX2**).

## ▶ STAGE 2 BUILT, WAITING FOR THE HEADSET (2026-10-21)
Built and verified without a headset: 90 Hz true stereo (two renders per vsync, 180 renders/s, game speed exact). The runbook and
test order are in **`vr/IMMERSIVE.md`**. **ACTION NEEDED (user, in the headset):** set the Frame to 90 Hz, run
`.\Play-Police247.ps1 -Immersive`, then follow the test order in IMMERSIVE.md.
- **Game-side patches**, in `camera-tracking/re/ram`:
  - `vrcam.py`: head rotation and FOV. Live-verified, with signs = OpenVR.
  - `vr90.py`: 50 Hz sim gate, one-shot render state save/restore, two loop passes per vsync.
  - `vrshot.py`: shots along the gun, because the hit test uses the logic camera with a fixed focal length.
  - All three selftests PASS. `frame_bridge --immersive` keeps them installed.
- **Fork** (`pcsx2-vr`, diff saved in `vr/pcsx2-vr.patch`):
  - eye snapshots and same-tick pairing
  - `[VR] Mode = dryrun|openvr`
  - OpenVR submit (D3D11) and pose → EE slots
  - It only attaches to an already-running SteamVR (VR_Init would otherwise start SteamVR itself).
  - The OpenVR path is compiled but untested.
- Measured: the frame spans tan ±0.635 × ±0.443; EE 300% is required (180% gives 45 Hz/eye); 4× upscale holds 90 Hz.
  Details are in RE_FINDINGS.md (2026-10-21).
- The fork's `PCSX2.ini` was edited for the tests (90 Hz, EE 300%, D3D11, 4×, [VR]). The launcher re-asserts these settings on each launch. The
  pre-test copy is `PCSX2.ini.pre-vr90`.
- New helpers: `pshot.py` (frame grab via savestate, no focus needed) and `gsvram.py` (GS VRAM framebuffer decode from a .p2s).
- Open: no menu/theater fallback in immersive mode, and no positional parallax (head translation drives lean/duck). See IMMERSIVE.md.

### ▶ NEXT TASKS (in order)
1. **Headset test (needs the user):** run `vr/IMMERSIVE.md` steps 1–5.
   - Fix whatever breaks in `pcsx2/GS/VR/VRSession.cpp`: the D3D11 submit, the texture bounds, the pose delay.
   - Tune `TanH/TanV`, `PoseDelay`, `SwapEyes` and `UnitsPerMetre`.
   - After any fork edit, re-export the patch:
     `cd pcsx2-vr; git diff -- . ':!3rdparty/include/openvr/openvr.h' > ..\vr\pcsx2-vr.patch`
2. **Aim check in VR:** in training (savestate 8: infinite time and ammo), turn your head ±30° and shoot.
   - The `vrshot.py --status` count `used` must rise with each shot.
   - If the ring and the hits disagree, check `AIM_DIST_M` (6 m) and the logic-frame math in `frame_bridge.aim_target`.
3. **Menu/theater fallback:** while vrcam's `applied` counter (`0x4F8038`) stops advancing (title, menus, captions), present a
   world-locked flat quad instead of full-FOV eyes (IVROverlay, or a quad in the submitted eye textures).
4. **Positional comfort:** decide whether small head translation (beyond what lean/duck uses) should also go into the view
   (eye-space translate in the vrcam S_TX slots, with y and z added to vr90's per-eye x).
5. **Busier scenes:** confirm 180 renders/s holds in heavy firefights and in interval-1 (50 Hz sim) scenes. If not, the fallback
   is stereo at the achieved rate plus SteamVR reprojection, which already works through `Submit_TextureWithPose`.
6. Tidy-up: delete the stray `pcsx2-vr/deps/deps`. Debug leftovers: `vr_eye{0,1}.png` dumps every 5 s in `GSRenderer::VRCompose`
   (remove them, or put them behind a setting).

## ▶ OPEN BUG (2026-10-20, end of session): VR launch lands on the DESKTOP, not Theater
The launch chain works end to end. Clicking "Police 24-7 (VR)" in Steam with SteamVR down:
`-Vr` starts SteamVR (+4 s) → exits → a WMI-spawned helper relaunches the shortcut via
`steam://rungameid/17657713875153321984` → PCSX2 (+24 s) → frame_bridge starts and connects. But PCSX2
showed up as a desktop window, and the Frame was streaming the whole desktop instead of the Theater screen.
The 2026-10-12 Theater success was a launch from the Steam library while SteamVR was already running.
Hypotheses, in order:
(a) Steam uses Theater only for launches it starts while VR is active *from the VR library/dashboard*;
    a `steam://rungameid` URL (or a desktop-Steam click) goes to the desktop. Test: start SteamVR first,
    then launch the shortcut from the in-headset library.
(b) SteamVR had just restarted (Steam restart + forced SteamVR kill) and the Frame session was in
    "desktop streaming" mode.
(c) The relaunch path itself. Compare against a manual library launch.
If Theater can't be triggered reliably, the Stage 2 immersive renderer (our own OpenVR scene app)
replaces Theater anyway, so don't sink much time into it.

## ▶ STAGE 2 STARTED 2026-10-20: immersive full-FOV stereo
Plan: `C:\Users\tdk10\.claude\plans\pickup-the-workstream-to-gentle-deer.md`. The user chose
**stereo now** and approved upscaling for VR. On the PS2, VU1 transforms vertices before the GS sees them,
so there's no per-eye geometry. Approach: a PCSX2 v2.6.3 fork (OpenVR scene app, D3D11) does depth
reprojection from GS colour+Z, with an alternate-frame-eye toggle to compare.
- **Done (static, untested live):** the render camera, projection and culling are decoded
  (`camera-tracking/re/RE_FINDINGS.md`, last section). `camera-tracking/re/ram/vrcam.py` adds the cave
  (head yaw/pitch/roll + eye offset into the render view) and live FOV/culling slots. `--selftest` PASS.
- **90 Hz/eye target (user, 2026-10-20 late): AFR at 30 Hz/eye is rejected.** The sim is frame-locked to 50 Hz
  PAL (no dt; "[Hz CHANGE]" is the camera's flicker setting). The design is now: the fork runs vsync at 90 Hz,
  an EE patch runs the sim step (0x1335D0) only on a 50 Hz accumulator, and the render (0x133690) runs
  twice per vsync, once per eye. That is 180 renders/s and needs EE overclock; the fallback is reprojection.
  See the plan's Phase 1b and the last section of RE_FINDINGS.md.
- **(Superseded 2026-10-21: the user said continue, Phase 1b measured and passed — see the top.) ON HOLD (user, end of 2026-10-20).** I explained the 90 Hz options. Comfort needs the head view at 90 Hz;
  reprojection covers that. Real stereo at 90 Hz is uncertain, 45–50 Hz real stereo + reprojection is likely.
  A recompile is not viable via REA (it can't open MIPS R5900) and would still need a GS/VU renderer, so the
  recommendation is to stay on the emulator. Waiting on the user's go for the Phase 1b measurement.
  Tidy-up for later: delete the stray `pcsx2-vr/deps/deps` (a duplicate extraction), and add `pcsx2-vr/`
  and `pcsx2-vr-deps/` to `.gitignore` (several GB, not decided yet).
- **Phase 0 DONE:** stock `pcsx2-vr/bin/pcsx2-qtx64-avx2.exe` (v2.6.3) builds and boots slot 9 (build notes are in the plan).
- **Next:** (0) Phase 1b gate: measure 90 Hz vsync + 2 render passes. (1) live-test vrcam in the hotel lobby (`py vrcam.py --on`, `--sweep yaw 20`,
  `--fov 1.5`, `--cull 0 0`, `--status`), then the aim hit-test question. (2) Phase 0 toolchain:
  VS 2022 Build Tools + CMake, the PCSX2 v2.6.3 source + deps, the OpenVR SDK (needs the user's OK).
- GhidraMCP: `tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py ps2 <tool> k=v`.

## ▶ STATUS (end of 2026-10-12): Stage 1 flatscreen VR is PLAYABLE on the Steam Frame
User played full rounds: firing good, aim "much better" after the fixes below, voice works.

### How to play (verified)
0. **One click (2026-10-20):** `Play Police 24-7 VR.bat` starts SteamVR if needed, then launches
   the Steam shortcut, which runs `Play-Police247.ps1 -Vr`. That starts PCSX2 windowed with PINE, and starts
   `frame_bridge.py -v` minimised (it waits for the game to boot; log `vr/bridge.log`; killed when
   PCSX2 exits). So step 3 below is now automatic. The shortcut's options were changed to `-Vr`;
   re-run `py vr/add_steam_shortcut.py --restart` if Steam still has the old ones.
   If SteamVR is down when the shortcut runs, `-Vr` starts SteamVR, waits for it, and exits;
   a hidden helper then waits for that process to end (+5 s) and relaunches the shortcut, so the
   game opens on the Theater screen. Gotcha (2026-10-20): a relaunch that reaches Steam while it still
   counts the game as running gets stuck as a pending "DownloadingDepots" action, and blocks
   later launches until it is cancelled in Steam or Steam restarts.
1. Start SteamVR with the Frame. Launch **"Police 24-7 (VR)"** from the Steam library
   (non-Steam shortcut added by `vr/add_steam_shortcut.py`; runs `Play-Police247.ps1
   -Vr` via powershell; Steam's overlay injects into PCSX2).
2. The game appears on SteamVR's **Theater screen**. **Close the dashboard** (system
   button): only then does SteamVR deliver buttons to the bridge (`trig=?` in `-v` output
   = dashboard open).
3. `cd vr` → `py frame_bridge.py -v` (Claude runs it in the background). `vr/calib.json` is
   current (aim-pose + plane model, 2026-10-12 22:34); recalibrate with `--calibrate` if
   the play spot or screen moves.
4. Controls: right trigger = fire (bridge SendInput click), point = aim (RAM write), lean/
   crouch with the body, hold right grip 1.5 s = recenter, **voice = hold the left
   controller at your mouth ("radio mic")** or hold left d-pad down / right A (buttons only
   with the dashboard closed). High beep = recording, low beep = sent, focus returns to PCSX2.

### ▶ NEXT
- **Verify the last tuning in play** (not yet played): neck-pivot lean/duck (`NECK` =
  [0,-0.10,+0.08] in the HMD frame, so head tilt/nod no longer leans), `LEAN_M` 0.40,
  `DUCK_M` 0.22. User said: lean too floaty, crouch didn't reach fully down (before this fix).
- Aim plane is assumed perpendicular to the calibrated head yaw at `SCREEN_M`=3.0 m. The
  last calibration showed the picture well to the right of the head yaw, so the plane is
  oblique → aim may drift while leaning. Fix if reported: take the plane normal from the
  mean corner ray instead of the head yaw (store the corner rays in calib.json).
- Possibly auto-start the bridge from the Steam launcher; then Stage 2 (6DOF), see below.

## Found in the first headset session (2026-10-12, evening)
- **SteamVR dashboard/desktop view = no buttons for any other app.** Legacy
  `getControllerState` returns false for Background/Overlay apps; IVRInput actions stay
  `bActive=0` while `isDashboardVisible()=1` even with global-overlay priority
  (`k_nActionSetOverlayGlobalPriorityMin`) and the SteamVR setting
  `steamvr/globalActionSetPriority=true` (now ON in `steamvr.vrsettings`; tested after a
  restart). The desktop view only sends Windows the laser left click. Poses always flow.
- **Theater screen (game launched from Steam) + dashboard closed → IVRInput works.**
  `frame_bridge.VR` now: `VRApplication_Overlay`, manifest `vr/input/actions.json`
  (fire vector1, recenter, talk, aim pose, haptic) + `bindings_frame_controller.json`
  (controller_type `frame_controller`; right trigger/grip/A, left dpad_down, right pose/tip).
- **Aim used the raw pose, whose forward axis is 40° off the Frame controller's aim.** Now
  uses the `/user/hand/right/pose/tip` pose action, and maps the ray-plane hit (plane
  `SCREEN_M` ahead) through the 4-corner homography; exact under lean when the distance is
  right (self-tested). `run()` refuses old angle-model calib files.
- Frame controller inputs (driver `frame_controller`): left has `dpad_*` + view, right has
  A/B/X/Y + menu; both trigger, grip, bumper, thumbstick, thumbrest.
- pyopenvr quirk: `updateActionState` must get a ctypes array (`(VRActiveActionSet_t*1)()`);
  a bare struct is silently replaced by an empty array.
- Only one python OpenVR client with a manifest at a time (shared app key
  `system.generated.python.exe` → `InputError_InvalidHandle`). Stop the bridge before probes.
- Desktop+ doesn't work on the Frame yet; the user docks the Claude terminal to the left
  controller (SteamVR). PTT focuses the terminal whose title doesn't end in `.exe`.
- Probes: `vr/probe_buttons.py` (action states), `vr/probe_hooks.py` (Windows mouse/key log
  with the focused exe). Shortcut backup: `Steam/userdata/42342116/config/shortcuts.vdf.bak-*`.

## Voice in VR (added 2026-10-12)
- SteamVR's audio setting is on "Headset" (auto), so it already switches the Windows defaults to
  Steam Streaming Speakers/Microphone while the Frame streams. `vr/mic_default.ps1 [-Speakers] [-Set X]`
  lists or forces the default device.
- `~/.claude/settings.json`: `voice` = hold mode + `autoSubmit` (sends on release if ≥3 words).
- `vr/voice_ptt.py`: on talk → focus the Claude terminal, hold Space (repeat keydowns @30 Hz,
  hold mode needs key-repeat) → on release key-up, then focus back (logged). Triggered from
  `frame_bridge.VR.talk()` (radio-mic gesture or talk button). `--voice-only` runs just that.

## Goal (user)
1. **Flatscreen VR** on a Steam Frame streaming from this PC: the game shows on a
   virtual screen, **headset pose drives lean/duck**, and **the controller is
   the gun**.
2. Then **full 6DOF VR**.

The user wants to be told explicitly when they must click or do something
(prefix: **ACTION NEEDED:**).

## Decision made: PS2 (PCSX2) is the platform
- The arcade build (MAME) now boots, but MAME's Voodoo3 emulation corrupts
  textures and flickers, which the user confirmed. That is emulator-core work, so
  it is parked.
- The PS2 build's camera tracking is bypassed: `camera-tracking/re/ram/hook.py`
  NOPs guards `0x001BC808/0x001BC810`, and we write **head_x `0x0029F0F8`** /
  **head_y `0x0029F0F4`** (int32, neutral `248,71`) over PINE (`pine.py`).
  Lean is verified graduated (`camera-tracking/GAMEPLAY_VERIFY.md`). Tracking
  quality depends on our pose source, not on which game version we run.

## Found 2026-10-12 (live, hotel lobby + training level)
- **Aim (absolute crosshair) = `0x002C240C` X / `0x002C2410` Y**, int32, offset from
  frame centre. On the 640×480 frame: `screen_x = 320 + X`, `screen_y = 240 + 0.9375·Y`.
  Hunt r = 0.996 / 0.998 (`aim_hunt.py states`). **Writes verified**: writing
  (−200,−120) / (200,120) / (0,0) put the green reticle at (119,127) / (519,352) /
  (319,240), and the values stuck. A screen-space copy is at `0x00420688/0x0042068A` (int16).
- **Trigger held = `0x002C4740`** (int32, 1 held / 0 released), mirrored at `0x002C49D0`;
  IOP `0x00171A40` probably holds the raw USB report. Found with `aim_hunt.py buttons` +
  `button-hunt` (beep-cued hold/release, `sweeps/fire1`; phase 0 was a late press).
  **Writing it does NOT fire** (it is a status copy; a written value persists but the game
  ignores it). Not chased further, because:
- **Fire = a real left-click.** A `SendInput` LEFTDOWN/LEFTUP with PCSX2 in the foreground
  fires (user-confirmed, 5/5). `SendInput` *movement* never reaches the game (PCSX2 likely
  takes pointer deltas from raw input and drops injected ones), but buttons work. PCSX2 is not
  elevated. So the bridge = RAM writes for head + aim, SendInput click for the trigger.
- The **green ring** is the player's crosshair. The small red circles are enemy markers.
- **head_x sign**: `head_x=500` clears "MOVE LEFT" and `0` peeks right. `hook.from_normalised`
  had the sign backwards; fixed 2026-10-12 (dx=-1 now leans left).
- **head_y** sweep 71→240 lowers the camera gradually, all the way to fully behind cover.
- **PINE serves one client at a time.** A second connection times out, so stop
  `lean_keys.py` before running other PINE scripts (`aim_hunt.py live/states` include
  the J/L/M keys themselves).
- The gun is PCSX2's USB HID mouse (`Pointer-0`). SendInput moves from a script do NOT reach it,
  so a person has to aim during hunts. Savestates (`.p2s`) contain `eeMemory.bin` +
  `Screenshot.png` from the same frame: use them for RAM↔screen correlation.
- Savestate slot 9 = hotel lobby start.

## Next steps (Stage 1)
1. **ACTION NEEDED (user):** launch PCSX2 with PINE on
   (`Play Police 24-7.bat -Motion synth -Pine`, see
   `camera-tracking/re/ram/README.md`) and get to the first stage (hotel lobby).
   The last session was interrupted right before checking for this.
2. With the game live: `py hook.py --status/--on/--set X Y` in
   `camera-tracking/re/ram/`. Sweep **head_y** to confirm duck/cover, and map the
   X thresholds for peek/exposed.
3. ~~Find the absolute crosshair X/Y and fire state~~ **DONE 2026-10-12** (see "Found" above).
   Original plan: find them in EE RAM (`snap.py` +
   `hunt.py` diff hunts; cross-check in Ghidra on `extracted/SLES_502.85`;
   the ghidra-emotionengine-reloaded extension is installed).
4. **BUILT 2026-10-12, untested on a headset:** `camera-tracking/pose/head_writer.py`
   (normalised lean/duck → head hook, with smoothing and a deadzone) and `aim_writer.py`
   (0..1 picture coordinates → AIM RAM, trigger → SendInput click only while PCSX2 is
   focused) were both verified live against the game without VR. `vr/frame_bridge.py`: `--calibrate`
   (neutral stance + point at the 4 corners of the game picture → `vr/calib.json`), `--dry`,
   `-v`; hold the right grip for 1.5 s to recenter. The math is self-tested. `pyopenvr` is installed.
   Stop `lean_keys.py` first (PINE allows one client). Still open: the launcher flag in
   `Play-Police247.ps1`; whether the legacy `getControllerState` trigger reaches a
   background app (if not, add an action manifest).
   Original plan: build head/aim writers, then `vr/frame_bridge.py` (pyopenvr/OpenXR: HMD → head writer; controller ray ∩
   calibrated virtual-screen plane → aim writer; trigger → fire).
5. Stage 2: trace the consumers of head_x/head_y forward to the camera/view-matrix
   build, prototype HMD → camera writes over PINE, then decide on stereo
   (depth reprojection first, alternate-eye PCSX2 fork second).

## Arcade work completed this session (reference / fallback)
Full write-up: **`arcade-re/ARCADE_FINDINGS.md`**. Highlights:
- MAME 0.289 is installed at `MAME/mame0289/`, set `p911ud` (ROMs in
  `roms/p911ud/`; MAME's p911ud loads disk `a00eaa02`).
- **Body sensor = DUART channel B**: 4-byte packets (b0/b1 = 6-bit bar
  bitmaps, b2/b3 = left/right rangefinders ≥ `0x20`). Emulated by injecting
  into the game's RX ring (`0x33EBE8`, indices `0x868/0x86A`):
  `arcade-re/mame/p911_sensor.lua` (globals `p911.left/right/barsA/barsB`).
- **DUART channel A = Konami factory jig** (`@0L…CC` ASCII; `T` = seconds since
  2000-01-01, `D` = region index, 1 = UAD). It was used once to program the
  NVRAM (PRODUCTION MODE). The programmed NVRAM is saved in
  `MAME/mame0289/nvram/p911ud/`; the old copy is in `nvram/p911ud.backup-before-production`.
- `Play Police 911 Arcade.bat` boots to gameplay (the user saw the intro video
  after setting the bookkeeping time).
- REA cannot open PowerPC/MIPS, so all static work used **Ghidra 12.1.4 headless**
  (`tools/ghidra_12.1.4_PUBLIC`). Reusable scripts are in `arcade-re/tools/`
  (`ghidra/*.java`, `mame-lua/*.lua`, `fat16.py`, `rom2elf.py`). The Ghidra
  project for the arcade RAM dump is in `extracted/arcade/ghidra_proj`.

## Gotchas that cost time
- MAME Lua memory taps crash on Viper (64-bit bus masks overflow Lua ints).
  Use debugger watchpoints/breakpoints set from Lua instead, with
  `-debug -debugger none -log`; output goes to `error.log`.
- Run scripted MAME headless (`-video none`). Windowed runs stall without focus.
- Don't pipe MAME output into `Select-Object -First N`: it kills MAME.
- Ghidra headless on Windows: call it through a `.cmd` wrapper (PowerShell
  quoting breaks it).

## Housekeeping
- `MAME/` (ROMs, about 300 MB of emulator files) is **not** in `.gitignore`;
  the user hasn't decided yet.
- The `Police 911` repo has uncommitted changes from earlier work; nothing was
  committed this session.

## Tool: GhidraMCP (added 2026-10-20)
Ghidra as MCP tools (decompile, disasm, xrefs, strings, read memory, rename/comment/retype)
for the PS2 EE ELF (`ghidra-ps2`, MMI decodes) and the arcade PPC RAM dump (`ghidra-arcade`).
`ghidra-mcp\start.cmd` / `stop.cmd`; shared servers, edits persist. See `ghidra-mcp/README.md`.
