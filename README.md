# Police 911

Reviving the arcade light-gun game **Police 911 / Police 24/7 / The Keisatsukan**
(PS2 port) on modern hardware, via **PCSX2** on Windows 11.

The original arcade cabinet had two inputs the PS2 port had to replace:

1. **A light gun** — the PS2 port has no light-gun protocol support at all
   (confirmed: it's the one PS2 game GunCon/GunCon 2 don't work with).
2. **A body-position sensor** — overhead IR sensors (arcade) / a special
   Konami "Capture Eye" USB camera (PS2), for the duck/lean/dodge mechanic.

This repo is split into two independent efforts reconstructing those two
inputs for PCSX2, developed on two different machines:

| Directory | Effort | Machine | Status |
|---|---|---|---|
| [`PoliceGun/`](PoliceGun/) | iPhone-as-light-gun (gyro → relative mouse) | This machine (MacBook Pro, builds the iOS app + Windows helper) | v1.1 working end-to-end, hand-test pending |
| [`camera-tracking/`](camera-tracking/) | Webcam-based body dodge/lean detection → PCSX2 | Second machine | Not yet started |

See **[PLAY_SESSION.md](PLAY_SESSION.md)** for how to set up and run a full
session with whichever of the two pieces are ready.

## Background reading

- [`police-247-research-dossier.md`](police-247-research-dossier.md) —
  compiled research on the arcade/PS2 game's real hardware, camera
  compatibility (Konami Capture Eye vs. EyeToy), and light-gun protocol
  history. Read this before touching camera-tracking — it documents which
  approaches are already known dead ends.
- [`police-247-research-fanout-prompt.md.docx`](police-247-research-fanout-prompt.md.docx) —
  the prompt set used to generate that dossier.

## Working across two machines

Both efforts share this one repo but touch disjoint directories
(`PoliceGun/` vs. `camera-tracking/`), so conflicts should be rare. A few
ground rules to keep it that way:

- `git pull` before starting a session; `git push` at the end of one —
  don't let work sit uncommitted locally across sessions.
- Stay inside your own directory. If a change genuinely needs to touch the
  other effort's files (e.g. wiring both inputs into PCSX2 together), call
  that out in the commit message.
- Root-level docs (this file, `PLAY_SESSION.md`) describe how the two
  pieces fit together — update them when either side's setup steps change,
  not just your own subdirectory's README.

## Not in this repo

Game ROM/ISO images and the PCSX2 emulator itself are not — and will never
be — checked in here (see `.gitignore`). Source them yourself.
