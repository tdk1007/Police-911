# PoliceGun

An iPhone-as-light-gun for **Police 911 / Police 24/7 (PS2)** running under
**PCSX2 on Windows 11**.

## Why this design

Police 24/7 is the one PS2 game that does **not** support GunCon / GunCon 2, so
there is no absolute-pointer path into it. Under PCSX2 it reads a **relative HID
mouse** — the same input that a desktop mouse uses to move the crosshair and
fire (confirmed working by hand). So v1.0 turns the iPhone's **gyro** into that
relative mouse: angular velocity → mouse deltas. No LiDAR, no AR, no
calibration — those only pay off for GunCon2 games and are deferred to v2.0.

The body-dodge (duck/lean) mechanic is handled separately by a fixed webcam fed
into PCSX2's EyeToy device — it is **not** part of this phone gun.

## Pieces

| Part | Path | Runs on |
|------|------|---------|
| iPhone app (gyro → UDP) | `ios/PoliceGunApp.swift` | iPhone 17 Pro |
| Input helper (UDP → SendInput) | `windows/gun_helper.py` | Windows 11 PC |

`ios/PoliceGunApp.swift` is the source of truth — drop it into a fresh
Xcode project per `SPIKE.md`. The full buildable Xcode project scaffold
(xcodeproj, tests, assets) is versioned separately at
[github.com/tdk1007/policegun-ios](https://github.com/tdk1007/policegun-ios)
as a convenience backup; it's not embedded in this repo.

```
iPhone gyro ──UDP/WiFi/100Hz──▶ gun_helper.py ──SendInput(relative)──▶ PCSX2 ──▶ Police 911
```

## Spike 1 — prove the plumbing (do this first, no game yet)

1. **Windows PC:** install Python 3, then:
   ```
   py -3 gun_helper.py
   ```
   It listens on `0.0.0.0:52777` and prints packet stats.
2. **Find the PC's IP:** `ipconfig` → IPv4 address (e.g. `192.168.0.50`).
3. **iPhone:** build `PoliceGunApp.swift` in Xcode onto the physical phone
   (gyro isn't in the simulator). Enter the PC IP, tap **Start**.
4. Wave the phone → the **Windows mouse cursor** should move. Hold **FIRE** →
   left-click. That's the whole pipeline validated.

Both devices must be on the **same subnet** (your Trusted VLAN, 192.168.0.x).
If packets don't arrive, check Windows Firewall (allow inbound UDP 52777) and
that the PC isn't stranded on a different VLAN.

## Spike 2 — tune against the game

Launch PCSX2 with Police 911, USB port = **HID Mouse**, fullscreen. Disable
Windows "Enhance pointer precision" first. Aim the phone and adjust in-app:
**Sensitivity**, **Y scale**, **Invert X/Y** until the crosshair tracks your
muzzle. Expect "playable-but-drifty, bump-the-edge to
recenter" — same as any mouse playthrough of this title.

## Roadmap

- **v1.0** — gyro-relative, on-screen trigger. *(this)*
- **v1.x** — 3D-printed grip; $5 Bluetooth shutter as a hardware trigger
  (pairs as a keyboard; app maps the keypress to FIRE). Phone fully enclosed —
  the gyro gun needs no camera view.
- **v2.0** — dual-mode: add ARKit/LiDAR **absolute** aiming for the GunCon2
  light-gun library (Time Crisis, House of the Dead…), toggle between modes.
  Same grip, trigger, and helper.

## Protocol

UDP datagram, JSON, ~100 Hz:
```json
{"dx": 1.23, "dy": -0.45, "fire": 0}
```
`dx`/`dy` = relative mouse counts since the last packet (fractional; the helper
carries the remainder). `fire` = current trigger state; helper emits button
down/up on transitions.
