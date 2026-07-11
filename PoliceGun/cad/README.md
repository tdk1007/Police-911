# PoliceGun v1.x — grip (CAD)

Parametric pistol grip + iPhone 17 Pro cradle. One printed part; the Bluetooth
shutter fob *is* the trigger (seated button-out at the finger).

## Generate / edit

Open `policegun_grip.py` in Blender's **Scripting** workspace and press **Run
Script**. It builds into a fresh `PoliceGun` collection (leaves your scene
alone). Every dimension is a variable in the `PARAMS` block — change and re-run.
Export the `PoliceGun_Body` object as **STL** (unitless → slicer reads mm).

## Design at a glance

```
        ┌─ phone in landscape, screen up, camera over the open window ─┐
        │  cradle walls (X) + back stop hold it; strap over the top    │
   ┌────┴──────────────────────────────────────────────────────────┐  +Y →
   │  base plate  [ open camera window ]                            │  downrange
   └──┬───────────────┬────────────────────────────────────────────┘
      │ trigger block │  ← AB Shutter fob in pocket, button faces you
      │  ( ) guard    │
      │  pistol grip  │  (leaned back 18°)
      ╰───────────────╯
```

- **Cradle** fits the phone **with a slim case** (`CASE_SIDE=1.5`); set to `0`
  for a bare phone. The open center clears the rear-camera plateau — which also
  keeps the camera unobstructed for the **v2.0 ARKit** mode.
- **Trigger** = the fob's own button, reacted by a solid back wall so presses
  feel firm. No mechanism to break.

## Print settings (starting point)

| Setting | Value |
|---|---|
| Material | PETG or PLA+ (PETG if it'll sit in a warm room / car) |
| Orientation | Lay on its **side** (one flat X face down) so grip + spine lie flat |
| Supports | Yes — under the trigger guard loop and cradle overhangs |
| Layer height | 0.2 mm |
| Walls / infill | 4 perimeters, 25–30% gyroid (it's a hand-load part) |

## Bill of materials

- 1× printed `PoliceGun_Body`
- 1× **AB Shutter 3** BT remote (~$5) — pairs as a Bluetooth **keyboard**;
  the app maps its keypress to FIRE (wire-up in a later app build)
- 1× strip of **TPU or adhesive foam** as a cradle liner (grip on the phone/case)
- 1× **velcro strap** (~200 mm) over the phone — thread through the four base
  slots (drill Ø or add in the script later; left out of v1 to keep the print
  clean)
- Optional: rubber band as a shutter-retention backup

## Assembly

1. Line the cradle floor/walls with the TPU or foam strip.
2. Drop the phone in (screen up), snug it back against the back stop, strap over.
3. Slide the AB Shutter fob into the trigger pocket from the finger side until
   the back wall stops it; the button should sit proud, facing your trigger
   finger. Friction-fit; add a dab of tape or the rubber band if loose.
4. Pair the fob to the iPhone (Bluetooth settings), launch the app, aim.

## Known first-print tuning

- **Fob too loose/tight?** adjust `SHUTTER_CLR`.
- **Button too deep to reach?** lower `POCKET_BACKWALL` or move `TRIG_BLOCK_Y`
  toward you (smaller).
- **Guard cramped?** raise `GUARD_MAJOR`.
- **Phone rattles?** thicker liner, or reduce `CLR`.
