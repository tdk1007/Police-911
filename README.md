# Police 911

Reviving the arcade light-gun game **Police 911 / Police 24/7 / The Keisatsukan**
(PS2 port) on modern hardware, via **PCSX2** on Windows 11.

The original arcade cabinet had two inputs the PS2 port had to replace, and this
repo reconstructs both for PCSX2 as two independent efforts:

1. **A light gun** — the PS2 port has no light-gun protocol support at all
   (it's the one PS2 game GunCon/GunCon 2 don't work with).
2. **A body-position sensor** — overhead IR sensors (arcade) / a special
   Konami "Capture Eye" USB camera (PS2), for the duck/lean/dodge mechanic.

| Directory | Effort | Approach | Status |
|---|---|---|---|
| [`iPhone Gun/`](iPhone%20Gun/) | Light gun | iPhone gyro → relative HID mouse (UDP → Windows helper → PCSX2) | **v1.1** working end-to-end; hand-test/tuning pending |
| [`camera-tracking/`](camera-tracking/) | Body dodge/lean | Webcam head-track **or** synthetic camera → PCSX2's emulated Capture Eye | **In progress** — game camera pipeline reverse-engineered; synthetic-camera + head-track bridge built; hardware validation pending |

New here? Start with **[camera-tracking/README.md](camera-tracking/README.md)**
or **[iPhone Gun/README.md](iPhone%20Gun/README.md)** for the effort you're
picking up, and **[CONTRIBUTING.md](CONTRIBUTING.md)** for how the repo is laid
out and how to add work. **[RUNBOOK.md](RUNBOOK.md)** is the full end-to-end
setup for actually playing on the built rig; **[PLAY_SESSION.md](PLAY_SESSION.md)**
covers running a session with whichever pieces are ready.

## Background reading

- [`police-247-research-dossier.md`](police-247-research-dossier.md) —
  compiled research on the arcade/PS2 game's real hardware, camera
  compatibility (Konami Capture Eye vs. EyeToy), and light-gun protocol
  history. Read this before touching `camera-tracking/` — it documents which
  approaches are already known dead ends.
- [`police-247-research-fanout-prompt.md.docx`](police-247-research-fanout-prompt.md.docx) —
  the prompt set used to generate that dossier.

## Repo layout

```
iPhone Gun/          light-gun effort (iOS app + Windows helper + CAD grip)
camera-tracking/     body-tracking effort
  re/                reverse engineering of the game's camera pipeline
  synth/             synthetic-camera frame generation (the authentic path)
  bridge/            webcam head-track → keypress duck bridge (fallback path)
  obs/               OBS Virtual Camera setup for routing any webcam to PCSX2
Play-Police247.ps1   one-shot launcher (wires camera/gun into PCSX2, boots game)
RUNBOOK.md           full setup + play guide for the built rig
```

## Not in this repo

Game ROM/ISO images, extracted game binaries, and the PCSX2 emulator itself are
not — and will never be — checked in here (see `.gitignore`). Source them
yourself.
</content>
