# Setting up a play session

Checklist for going from "cold start" to playing Police 911 under PCSX2 with
the iPhone light gun (and, once it exists, the camera dodge/lean tracker).

## What you need

**Hardware**
- Windows 11 PC running PCSX2, on the Trusted VLAN (`192.168.0.x`)
- iPhone with the PoliceGun app installed (see `PoliceGun/SPIKE.md` for the
  one-time Xcode build/install)
- Both devices on the same Wi-Fi / subnet — packets get dropped silently if
  the PC is stranded on a different VLAN
- 3D-printed grip (`PoliceGun/cad/tap-trigger-911.stl`) + AB Shutter 3
  Bluetooth remote as the trigger, once printed — see
  `PoliceGun/cad/README.md`. Until then, use in-app **Tap to fire** or the
  on-screen FIRE pad; no printed part is required to play.
- A Police 911 / Police 24/7 disc image (not provided in this repo)
- *(once camera-tracking exists)* a webcam positioned per
  `camera-tracking/README.md`

**Software**
- PCSX2, with the Police 911 ISO configured
- `PoliceGun/windows/gun_helper.py` (Python 3 on the Windows PC)

## Every session, in order

1. **Windows PC:** start the gun helper.
   ```
   py -3 gun_helper.py
   ```
   Leave this terminal open for the whole session — it's the UDP → mouse
   injector. It listens on `0.0.0.0:52777`.

2. **Windows PC:** disable pointer acceleration once per machine (persists
   across reboots, so usually a one-time step):
   **Settings ▸ Bluetooth & devices ▸ Mouse ▸ Additional mouse settings ▸
   Pointer Options →** uncheck **"Enhance pointer precision."**

3. **iPhone:** open the PoliceGun app, set **PC IP** to the Windows PC's LAN
   IP (`ipconfig` on the PC if it's changed), tap **Start**.

4. **Launch PCSX2** with the Police 911 disc. Confirm the USB port is set to
   **HID Mouse**, go fullscreen.

5. **Aim check:** wave the phone — the in-game crosshair should track it.
   If not, see the troubleshooting table below or `PoliceGun/SPIKE.md`.

6. *(once camera-tracking exists)* start the camera tracker per
   `camera-tracking/README.md` before launching PCSX2, and set PCSX2's
   camera/EyeToy device to it.

7. Play. Expect a **"playable but drifty, bump a screen edge to recenter"**
   feel — normal for a relative-mouse light gun on this title, not a bug.

## End of session

- Ctrl-C the `gun_helper.py` terminal.
- Tap **Stop** in the iPhone app (or just background it).
- No PCSX2 save-state requirement — the game's own save/checkpoint system
  handles progress.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Crosshair doesn't move | Helper not running, or phone/PC on different VLANs/Wi-Fi |
| Crosshair moves but backwards/sideways | Flip **Invert X/Y** in the app |
| Aim feels laggy or nonlinear | Windows "Enhance pointer precision" still on (step 2) |
| Can't reach part of the screen | Raise **Sensitivity** in the app |
| Vertical aim weak | Raise **Y scale** in the app |

Full first-time setup and deeper diagnostics live in `PoliceGun/SPIKE.md`.
