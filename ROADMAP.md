# Police 24/7 Rig — Roadmap & Next Steps

*Status snapshot: 2026-07-02. Resume point for the next session.*

## Where things stand (all verified working)

- ✅ Game boots in PCSX2 2.6.3 (BIOS `ps2-0230e-20080220.bin` installed, PAL disc
  boots from the `.bin`; two launch bugs fixed: `SettingsVersion=1`, no-cue).
- ✅ PAL disc **accepts the emulated Konami Capture Eye** — reached the game's
  SENSOR ADJUSTMENT camera screen (screenshot-confirmed). Biggest risk: dead.
- ✅ Camera distortion solved: Link 2C has no 4:3 modes → OBS 32.1.2 installed,
  pre-seeded 640×480 "Police247" profile + "EyeToy" scene (16:9 → 4:3
  center-cut). 320×240 DirectShow capture from OBS Virtual Camera verified
  clean — this is now the launcher's default camera path.
- ✅ Motion bridge (fallback path) self-tested; UDP/iPhone mode tested.
- ✅ Launcher `Play Police 24-7.bat` handles all modes.
- ⏳ USER: camera currently **unplugged** (being moved to the TV).
- ⏳ USER: no light gun yet — aim testing will use the desk mouse first
  (mouse = crosshair, left click = shoot; identical input path to the gun).

## Roadmap

### 1. Standing play (next session, mostly physical)
- Plug the Insta360 in at the TV — **use the USB port it will keep** (the
  OBS device id encodes the port; changing ports needs step 2).
- Run `police247-rig\obs\Setup-Camera.ps1` once (regenerates the OBS scene
  for the camera's new device id). Close OBS first if it's open.
- Placement: camera centered on/under the TV (~1.0–1.2 m high), level,
  facing the play spot. **Stand 2.0–2.5 m back** (computed, not guessed):
  Link 2C is 67° H / ~41° V raw, but the OBS 4:3 center-cut keeps the
  vertical and drops horizontal to ~53°, so **vertical ~41° is the binding
  constraint**. At 2 m the frame is ~1.5 m tall × ~2 m wide → standing head
  near the top, full crouch still in frame, ample lean width. Game tracks
  head/upper-body silhouette (EyeToy-style), NOT head-to-toe, so ~2 m is
  enough. Any normal living room has this (TV-to-couch is usually 2.5–3.5 m;
  just clear ~2 m in front of the TV). Constant room lighting on the player.
- Cramped-room fallback: iPhone 0.5x ultrawide (~120°) via Camo/EpocCam →
  existing OBS scene → PCSX2. The 4:3 crop keeps the ultrawide's huge
  vertical, giving full body at ~1 m back. Caveats: USB webcam-app latency
  (bad for this fast game), edge barrel distortion, Camo lens-select is paid.
  Prefer the already-built ARKit UDP bridge (port 47911) if the goal is just
  iPhone-assisted motion without touching the camera path.
- Launch, re-run the in-game camera setup (standing position → movement
  sensitivity → red light follows head → VIEW POINT CHECK).
- Tune with README's calibration section; troubleshooting table covers the
  likely misses.

### 2. Any-webcam support (mostly built — finish next session)
- ✅ `police247-rig\obs\Setup-Camera.ps1`: enumerates physical USB cameras,
  builds the DirectShow device id, generates OBS profile + 4:3 scene for ANY
  camera (bounds-based center-cut = resolution/aspect independent).
- ⏳ TODO: test the wizard end-to-end once a camera is plugged in
  (`-List`, then pick; then verify OBS virtual cam output at 320×240 —
  one-liner capture test exists in session scratch, redo with
  `python -c` snippet or bridge `--list-cameras`).
- ⏳ TODO: consider auto-detect fallback in the launcher when the OBS scene's
  device id goes stale (detect black frames → prompt to re-run wizard).

### 3. GitHub package `police247-rig\` (half-built — finish next session)
Goal: share the fixes with friends — **no game files, no BIOS** in the repo.
- ✅ Skeleton created: `bridge\` (bridge + iPhone example + requirements),
  `obs\` (Setup-Camera.ps1, profile template), `pcsx2\cheats\` (empty, for
  pnach), `launcher\` (empty yet).
- ⏳ TODO:
  - Generalized launcher copy into `launcher\` (auto-locate PCSX2 dir + game
    `.bin` relative to repo root, keep -Motion/-CameraName/-DryRun).
  - `pcsx2\PCSX2.ini.template` (current ini minus BIOS filename, minus
    absolute GameList path).
  - Share-README: from-scratch setup for friends (PCSX2 portable download,
    dump-your-own BIOS/game note, pip install, Setup-Camera, launcher, gun
    section, bridge/iPhone fallback, troubleshooting table — adapt README.md).
  - `.gitignore` (bios, *.bin/*.cue/*.iso/*.chd, PCSX2/, bridge_config.json,
    __pycache__), MIT LICENSE, `git init` + first commit.
  - Publish: no `gh` CLI installed. Either install GitHub CLI and
    `gh auth login` (user types `! gh auth login` in the session), then
    `gh repo create police247-rig --private --source . --push`; or create the
    repo on github.com and `git remote add origin … && git push`.

### 4. Stretch: extra time/lives (cheat research was IN FLIGHT)
- A research agent was hunting RAW/AR/CodeBreaker codes for SLES-50285 (and
  US/JP variants) — infinite time, lives, continues — when the session
  paused. **Next session: check the agent's findings first** (ask Claude to
  re-run the search if lost).
- Once codes exist: write `.pnach` → `PCSX2\cheats\<serial>_<crc>.pnach`.
  Get the CRC by booting the game once (window title / emulog with
  `EnableFileLogging=true`, already on). Enable via PCSX2 Settings →
  Game Properties → Cheats, or leave the file and toggle "Enable Cheats".
- If the web has no PAL codes: fallback plan is live memory hunting over
  PINE (`EnablePINE=true`, port 28011) while playing — scan for the timer
  value, narrow on change, patch. More work; only if needed.

### 5. Later / ideas (unprioritized)
- OpenFIRE gun build once mouse test proves the loop (README Step 3/4 has
  the full config + emitter plan ready).
- Gun recoil/solenoid via QMamehook when the gun exists.
- PINE sidecar for pixel-perfect absolute aim (kills relative-mouse drift
  entirely) — needs the crosshair memory address, find via PINE scan.
- Second gun + second player (game strings mention two gun controllers).
- Save-state quick-resume / memcard backup script.
- CRT shader in PCSX2 for arcade look (Settings → Graphics → Shaders).

## Fast resume checklist (for the human)
1. Plug camera in at the TV (final USB port).
2. `police247-rig\obs\Setup-Camera.ps1` → pick the camera.
3. `Play Police 24-7.bat` → in-game camera setup from the play spot.
4. Duck. If the game ducks: buy/build the OpenFIRE parts.
5. Tell Claude "resume the roadmap" — items 2/3/4 above continue from here.
