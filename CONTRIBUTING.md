# Contributing

Thanks for jumping in. This repo reconstructs two arcade inputs for **Police
911 / Police 24/7** under PCSX2. Read this once, then work mostly from the
per-effort READMEs.

## The two efforts

| You want to work on… | Go to | Runs on |
|---|---|---|
| Aiming / firing (the light gun) | [`iPhone Gun/`](iPhone%20Gun/) | iOS app built on a Mac + `gun_helper.py` on Windows |
| Ducking / leaning (the camera) | [`camera-tracking/`](camera-tracking/) | Python on Windows (webcam / synthetic camera + OBS) |

They use **disjoint** USB devices into PCSX2 (mouse for aim/fire, camera for
dodge) and share no code. Stay inside your effort's directory and merges stay
clean. If a change genuinely has to touch the other effort or a root doc, call
it out in the commit message.

## Before you start

You must supply these yourself — they are **not** in the repo (see
[`.gitignore`](.gitignore)) and never will be:

- A **Police 24/7 (PAL) disc image** you legally own.
- **PCSX2** (nightly) + a PS2 BIOS.
- For camera work: a webcam (developed against an Insta360 Link 2C) or the
  synthetic-camera path in `camera-tracking/synth/`.
- For gun work: an iPhone (gyro) and, on a Mac, Xcode to build the app.

## Getting oriented

- **Camera effort:** [`camera-tracking/README.md`](camera-tracking/README.md),
  and read [`police-247-research-dossier.md`](police-247-research-dossier.md) +
  [`camera-tracking/re/RE_FINDINGS.md`](camera-tracking/re/RE_FINDINGS.md)
  before designing anything — the constraints there are verified against the
  game binary, and several obvious approaches are already known dead ends.
- **Gun effort:** [`iPhone Gun/README.md`](iPhone%20Gun/README.md) and its
  [`SPIKE.md`](iPhone%20Gun/SPIKE.md) runbook.
- **Running the whole rig:** [`RUNBOOK.md`](RUNBOOK.md) and
  [`PLAY_SESSION.md`](PLAY_SESSION.md). The [`Play-Police247.ps1`](Play-Police247.ps1)
  launcher wires a chosen motion source + the gun into PCSX2 and boots the game.

## Workflow

- **Pull before, push after.** `git pull` at the start of a session, `git push`
  at the end — don't let work sit uncommitted across sessions.
- **Small, described commits.** Say what changed and why; note any cross-effort
  or root-doc edits.
- **Match the surrounding style.** Python here is plain-stdlib-leaning with
  docstrings that explain *why* (see `camera-tracking/synth/render.py`); mirror
  the neighbors rather than introducing new frameworks.
- **Keep big/copyrighted files out.** No ISOs, ROMs, extracted game binaries,
  or the PCSX2 tree. The `.gitignore` already blocks the known ones; if you add
  a new large artifact, ignore it too.

## Where help is most useful right now

- **camera-tracking (authentic path):** tune the synthetic-camera head so the
  game reads *graduated* lean/peek, not just a binary duck; confirm the PAL
  build's camera check passes on real hardware.
- **iPhone Gun:** hand-test and tune v1.1 aim against the game; the v1.x
  hardware trigger (Bluetooth shutter) and 3D-printed grip.
</content>
