# Spike 1 — Runbook

Goal: prove the whole chain **iPhone gyro → WiFi → Windows cursor moves & clicks**,
before any game tuning or 3D printing. Do the stages in order; each one isolates
a different half so a failure tells you exactly where the problem is.

```
Stage 1: (no phone)  synthetic sender ──▶ Windows helper ──▶ cursor moves   [proves injection]
Stage 2: (no PC)     phone ──▶ Mac monitor prints packets                   [proves phone TX]
Stage 3: (full)      phone ──▶ Windows helper ──▶ cursor moves & clicks     [proves the chain]
```

Files live in `PoliceGun/`:
- `windows/gun_helper.py` — the real injector (Windows only)
- `tools/udp_monitor.py` — prints incoming packets, no injection (Mac or Windows)
- `tools/send_test.py` — fake phone: streams a circle + clicks (Mac or Windows)
- `ios/PoliceGunApp.swift` — the phone app

---

## Prerequisites

**On the Mac (to build the phone app):**
1. Install **Xcode** from the Mac App Store (free, large download). You currently
   have only Command Line Tools, which can't build an iOS app.
2. After it installs, run once:
   ```
   sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
   sudo xcodebuild -license accept
   ```

**On the Windows 11 PC:**
1. Install **Python 3** (python.org or `winget install Python.Python.3.12`).
2. Both the phone and the PC must be on the **same subnet** — your Trusted VLAN
   (`192.168.0.x`). Confirm the PC isn't on Servers/IoT, or the VLAN block rules
   eat the packets.

You don't need the phone or Xcode to do **Stage 1** — start there for an
immediate win while Xcode downloads.

---

## Stage 1 — prove Windows injection (no phone)

On the **Windows PC**, two terminals:

Terminal A (the injector):
```
py -3 gun_helper.py
```
It prints `listening on 0.0.0.0:52777`. The **first time**, Windows Firewall will
pop up — click **Allow access** (Private networks). If you miss it, add a rule:
```
netsh advfirewall firewall add rule name="PoliceGun UDP" dir=in action=allow protocol=UDP localport=52777
```

Terminal B (the fake phone — send to the PC's own address):
```
py -3 tools\send_test.py --host 127.0.0.1
```

**Expected:** the Windows mouse cursor sweeps in a slow circle and left-clicks
about once a second. If it does, injection works — the entire Windows half is
proven. Ctrl-C both.

> Prefer to drive it from the Mac? Run `send_test.py --host <WINDOWS_PC_IP>` on
> the Mac instead — that also proves WiFi + firewall in one shot.

---

## Stage 2 — prove the phone transmits (no PC needed)

1. **Build the app:** open Xcode → **File ▸ New ▸ Project ▸ iOS ▸ App**. Name it
   `PoliceGun`, Interface **SwiftUI**, Language **Swift**. In the Project Navigator,
   open the generated `PoliceGunApp.swift` and **replace its entire contents** with
   `ios/PoliceGunApp.swift` from this folder.
2. Select **Signing & Capabilities ▸ Team** → your personal Apple ID. Set the
   deployment target to iOS 16+.
3. Plug in the iPhone, select it as the run destination, press **▶ Run**. First
   run: on the phone, **Settings ▸ General ▸ VPN & Device Management** → trust your
   developer certificate.
4. On the **Mac**, run the monitor:
   ```
   python3 tools/udp_monitor.py
   ```
   It prints the Mac's LAN IP(s). In the phone app, put one of those in **PC IP**,
   leave port `52777`, tap **Start**, and wave the phone.

**Expected:** the monitor prints a live stream of `dx / dy` values that change as
you move the phone, at ~100/s, and `fire 1` when you trigger. That proves the
phone is sensing and transmitting correctly.

### Firing — all zero-cost, no hardware, hold the phone bare-handed

You do **not** need the 3D-printed grip or any purchase to validate the spike.
Turn on whichever trigger feels best in the app's **Trigger** section:

- **Tap to fire** *(default, best rapid fire)* — tap the phone body with a
  finger; an accelerometer spike fires. Mash-tap = rapid fire. Aim is briefly
  muted around each tap so it doesn't jerk the crosshair. Tune **Tap sensitivity**.
- **Volume button to fire** — press a volume button as a physical trigger.
  Works because the app is sideloaded (App Store would disallow it).
- **On-screen FIRE** — the pad at the bottom; hold it for autofire. Always works.

---

## Stage 3 — full chain

1. On the **Windows PC**: `py -3 gun_helper.py`.
2. In the phone app: set **PC IP** to the **Windows PC's** IP, tap **Start**.
3. Move the phone → the **Windows cursor** moves. Hold **FIRE** → it clicks.

That's Spike 1 complete: the iPhone is a working wireless mouse you aim with.

---

## Stage 4 — into the game (Spike 2, tuning)

First, on Windows: **Settings ▸ Bluetooth & devices ▸ Mouse ▸ Additional mouse
settings ▸ Pointer Options → uncheck "Enhance pointer precision"** — Windows
applies pointer acceleration to injected motion and it wrecks aim linearity.

Launch PCSX2 with Police 911, set the USB port to **HID Mouse**, go fullscreen.
Aim the phone and tune in the app until the crosshair follows your muzzle:

- **Sensitivity** — counts per radian. Start ~3200; raise if you can't sweep
  edge-to-edge, lower if aim is twitchy.
- **Y scale** — vertical multiplier on top of Sensitivity, for games that
  scale X and Y differently.
- **Invert X / Invert Y** — flip if the crosshair goes the wrong way.

Aim mapping is orientation-agnostic (since v1.1): yaw is measured about the
world vertical and pitch from the barrel's absolute elevation (barrel = the
phone's long axis, camera end forward). Hold it flat, on-edge, or in the grip —
same behavior, and vertical aim cannot drift.

Expect "playable-but-drifty, bump a screen edge to recenter" — normal for any
relative-mouse playthrough of this title. That feel is the target for v1.0.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Stage 1 cursor doesn't move | Helper not running as the same user as the foreground app; or firewall blocked it. Re-run, click **Allow**. |
| Stage 2 monitor shows nothing | Phone on a different VLAN/WiFi than the Mac; wrong IP typed; app not **Start**ed. |
| Packets arrive but no cursor motion (Stage 3) | You're pointing the phone at the **monitor** IP, not the **helper** (Windows) IP. |
| Cursor moves but backwards / sideways | Invert X/Y in the app. One-time. |
| Up/down aim weak or dead | Fixed in v1.1 (orientation-agnostic mapping). If still weak in-game, raise **Y scale**. |
| Aim feels nonlinear / laggy on desktop | Disable Windows "Enhance pointer precision" (see Stage 4). |
| Cursor jitters at rest | Raise **deadzone** slightly (in code, `deadzone` default 0.01 rad/s). |
| Crosshair "sticks" then jumps | Normal relative-mouse drift; bump a screen edge to resync, or lower sensitivity. |
| No Firewall prompt appeared | `netsh` rule above; also ensure network profile is **Private**, not Public. |
