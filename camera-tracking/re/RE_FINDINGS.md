# Police 24/7 (SLES-50285) — camera pipeline reverse engineering

Working notes. Everything below is **verified against the binary**, not inferred
from behaviour, unless explicitly marked as a hypothesis.

Tools in this folder (`py <script>`):
- `mipslib.py` — shared: ELF load, disassembly, xrefs, function recovery
- `look.py <va> [n]` / `look.py xref <va>` — annotated disassembly / callers
- `refs.py <va>` — who references an address (incl. `$gp`-relative globals)
- `jal.py <va>` — raw-word scan for call sites (capstone-proof, see gotcha below)
- `api.py` — camera module's public API + its game-side callers
- `ptr.py <va>` — find function-pointer tables
- `iso.py` — list/extract the disc filesystem
- `irx.py <file>` — inspect an IOP module
- `mmi_scan.py` — locate R5900 SIMD (multimedia) code

## Binary layout

- EE executable: `SLES_502.85`, one loadable segment.
  **`vaddr = file_offset + 0xFFF80`** (segment: file `0x80` → vaddr `0x00100000`, size `0x19EF00`).
- `$gp = 0x002A6070` (set in crt0 at `0x0010005C`). Needed to resolve `imm($gp)` globals.

### Gotcha that cost real time
Capstone's MIPS32 mode **cannot decode the R5900's MMI (128-bit SIMD), LQ/SQ, or
COP2/VU0 opcodes, and it silently STOPS at the first one.** A naive
`list(md.disasm(...))` yields ~37 instructions out of ~338,000. Skip the
undecodable word (MIPS is fixed 4-byte) and resume. Even then ~20% of words never
decode — so **any call-graph built purely from capstone is incomplete**. Use
`jal.py`, which decodes JAL straight from raw words (opcode 3), for ground truth.

## The camera pipeline

Acquisition runs on the **IOP**, not the EE:

- `MODULES/WEBCAM_N.IRX` (49 KB) — the OmniVision (OVTI) USB camera driver.
  `WEBCAM.IRX` (179 KB) is the other camera variant; despite its size its `.text`
  is only 14 KB (the bulk is `.bss` frame buffers + 67 KB of `.mdebug`), so
  **it is a USB driver, not a vision engine**. Both carry full symbol tables.
- The EE talks to it over **SIF RPC** (`sceSifCallRpc` wrapper at `0x00228660`,
  numeric function IDs e.g. `0x56`, `0x58`).
- EE-side camera library: **`0x00226000`–`0x0022A000`**. It is almost entirely
  **table-dispatched** — the entry points have *zero* `jal` callers; an async
  command dispatcher at `0x00226D8C` does `jr $a0` through a 10-entry jump table
  at `0x002917B0`. This is why a normal xref hunt finds nothing.
- Camera state struct: **`0x0026B790`**. Confirmed field layout:
  - `+0x04` = **frame width**
  - `+0x08` = **frame height**
- Game-side camera client: **`~0x001BDB00`** (loads the `"webcam_n"` module,
  drives init/attach). Notably the SIMD-dense regions found by `mmi_scan.py`
  (`0x001BCB00`, `0x001BD100`, `0x001BD700`, `0x001BEF00`) sit in the *same*
  neighbourhood — game camera client and heavy pixel code are co-located.

## Verified constraints on the video feed  ← what matters for our synthetic feed

### 1. The game is LUMINANCE-ONLY. Colour is discarded.
The frame→preview converter at `0x002285A8` does, per pixel:

    lbu v0, (a0)    ; sb v0, (a1)   ; a1++     <- R
    lbu v0, (a0)    ; sb v0, (a1)   ; a1++     <- G
    lbu v0, (a0)    ; a0 += 2       ; sb v0, (a1); a1++   <- B
    sb  zero, (a1)  ; a1++                               <- A = 0

It reads **the same byte three times** (R=G=B) and advances the source by **2
bytes per pixel**. That is packed **YUV 4:2:2 (YUYV)**, taking only the **Y**
byte and throwing the chroma away. Loop bounds come from camera-struct `+4`/`+8`.

**Implication: chroma is wasted bandwidth. Only the luma channel reaches the game.**

### 2. Exactly five frame geometries are accepted.
`ovtVideo_init` (`0x00228240`) switches on a size index through a jump table at
`0x00291A30`; anything else logs `"ovtVideo_init(), unsupported video size"`:

| index | width         | height        |
|-------|---------------|---------------|
| 0     | `0x140` = 320 | `0xF0`  = 240 |
| 1     | `0xA0` = 160  | `0x78`  = 120 |
| 2     | `0x50` = 80   | `0x3C`  = 60  |
| 3     | `0x30` = 48   | `0x1E`  = 30  |
| 4     | `0x280` = 640 | `0x1E0` = 480 |

It separately validates format (6 accepted) and frame rate.

## Not yet recovered: the tracking algorithm itself

The head-finding code has **not** been located precisely. The blocker is
structural, not incidental: the pixel loops are written in **R5900 MMI SIMD**,
which capstone does not decode — the vision inner loop is literally inside the
20% of words that never disassemble. Reading it properly needs an
EE-aware disassembler (Ghidra + `ghidra-emotionengine-reloaded`).

**Hypothesis (from the in-game debug panel, NOT from code):** the tracker
thresholds/edge-detects the luma image into a binary contour and locates the head
on it. The SENSOR ADJUSTMENT screen renders that binary image directly, plus a red
dot at the tracked head position.

### The shortcut that makes this tractable
We *fully control the camera feed*, and the SENSOR ADJUSTMENT screen **renders the
tracker's own internal binary image plus its head estimate**. That is a black-box
oracle: feed calibrated test patterns, screenshot the panel, and read the
tracker's transfer function straight off the screen — threshold behaviour,
edge-vs-fill response, and the image→screen coordinate mapping. That measures the
real algorithm end-to-end, including anything a static decode would miss.

---

# SOLVED 2026-09-13: the tracker's output, and how to drive it

The algorithm is still un-decoded — and it no longer matters. What the project
actually needed was the algorithm's **output**, and that is now located,
verified, and writable.

## The variables

| address | meaning |
|---|---|
| `0x0029F0F8` | head **X**, `int32`, camera-image pixels, larger = further right |
| `0x0029F0F4` | head **Y**, `int32`, larger = further down |
| `0x0029F118` / `0x0029F114` | copies, written from the same registers |

Both are `$gp`-relative (`$gp = 0x002A6070`), which is why `refs.py` finds them:
`-0x6f78` and `-0x6f7c`.

## The code, and where to cut it

`refs.py 0x0029F0F8` gives two hits, both inside function `0x001BBAD0` — in the
same neighbourhood as the camera client (`~0x001BDB00`) and the MMI-dense pixel
blocks (`0x001BCB00`). Disassembled:

```
0x001BC7F4  mflo  $s0                  ; fresh reading falls out of a divide
0x001BC808  bnez  $s0, 0x1bc824        ; found something -> go store it
0x001BC80C  nop                        ; (delay slot, already a nop)
0x001BC810  bnez  $s1, 0x1bc824
0x001BC814  nop                        ; (delay slot, already a nop)
0x001BC818  lw    $s1, -0x6f7c($gp)    ; NOTHING FOUND -> reload previous Y
0x001BC81C  b     0x1bc82c             ;   ... and skip the stores
0x001BC820  lw    $s0, -0x6f78($gp)    ;   (delay slot) reload previous X
0x001BC824  sw    $s0, -0x6f78($gp)    ; store fresh X
0x001BC828  sw    $s1, -0x6f7c($gp)    ; store fresh Y
0x001BC82C  jal   0x1042e0
0x001BC838  sw    $s0, -0x6f58($gp)    ; copies, fed from the REGISTERS
0x001BC840  sw    $s1, -0x6f5c($gp)
```

So the game already has a "hold the last known position when detection fails"
path. **NOP the two guards and it takes that path every frame**, loading our
values and propagating them to the copies by itself:

```
0x001BC808  0x16000006 (bnez $s0,+6)  ->  0x00000000
0x001BC810  0x16200004 (bnez $s1,+4)  ->  0x00000000
```

This is deliberately *not* "NOP the two stores". The copies at `0x001BC838` /
`0x001BC840` are written from `$s0`/`$s1`, not re-read from memory, so killing
only the stores would leave the copies carrying camera-derived values.

Both guard words were read back from the running game and matched the expected
encodings exactly before patching; `hook.py` refuses to patch if they do not.

## Verified behaviour

Measured on the SENSOR ADJUSTMENT screen, which draws the tracker's own marker:

| written | effect on the game's marker |
|---|---|
| `head_x` 119 → 403 | marker moved 140.4 px, **r = −0.99922** (mirrored, as expected) |
| `head_y` 60 → 220 | marker moved 77.5 px, **r = +0.99799** |

Both ~0.49 screen px per unit, so the units are the same on both axes. `head_x`
stays linear over at least 0–500; past ~600 the marker leaves the preview.

`head_x = 248, head_y = 71` puts the marker inside the game's calibration ring,
**which then turns green** — the game's own "correctly positioned" indicator —
while the synthetic camera blob sat in an unrelated part of the frame.

And in an actual stage it drives the cover/lean mechanic: see
`../GAMEPLAY_VERIFY.md`.

## Why this beats the synthetic-camera path

The video route renders a fake head, the game's 2003 tracker re-finds it, and
every quirk of that tracker stays in the loop — it needs motion, its centroid
gets dragged by torso mass, its vertical response depends on blob *size* and is
non-monotonic across the frame, and the whole thing has to be re-calibrated
whenever the geometry changes. Writing the output directly has none of that: the
mapping is linear, exact, repeatable, and needs no calibration at all.

Tooling: `ram/hook.py` (apply/remove, set position), `ram/pine.py` (PINE client),
`ram/snap.py` + `ram/hunt.py` (how the address was found),
`PCSX2/cheats/SLES-50285_08A1C938.pnach` (the patch, commented out by default).

---

# 2026-10-20: the render camera, projection and culling (for immersive VR)

Static only so far (Ghidra `ghidra-ps2` + a MIPS64 decoder); not yet exercised live.
Tool: `re/ram/vrcam.py` (`--selftest` passes against the ELF).

## Camera and view
- Camera pose: `0x002C60E0`, floats X, Y, Z, pitch (+0x0C), yaw (+0x10), roll (+0x14), in degrees.
  The slots are 0xE8 bytes each; the active index is at `0x002C60C8`.
  - `setCamPose 0x1B90B0`: 30 callers. `getCamPose(idx,dst) 0x1B9010`: 54 callers.
- The render view is rebuilt every frame in `0x1B9180`. `jal glLoadIdentity` @`0x1B92A4` (its delay
  slot sets `s0 = 0x2C60E0`), then `glRotatef(-roll,0,0,1)`, `(-pitch,1,0,0)`,
  `(-yaw,0,1,0)`, then `glTranslatef(-x,-y,-z)`. Lights are set after that, in eye space.
- GL-style matrix library: `glRotatef 0x1CE280` (returns early when the angle is 0), `glTranslatef 0x1CEBD0`,
  `glLoadIdentity 0x1CF170`, `glFrustum 0x1CEED0`, `glOrtho 0x1CECF0`, `glMatrixMode 0x1CF1E0`,
  push/pop `0x1CE1D0`/`0x1CE190`.

## Projection
- `glFrustum` (soft-double arithmetic) computes `m00 = 0.3 * 2/(r-l)` (immediate built at `0x1CEF84`; this is the word PCSX2's
  widescreen patch edits) and `m11 = 8/7 * 0.282 * 2/(t-b)` (0.282 built at `0x1CEFC8`).
- The game FOV float is at `0x002C6128` (`setFOV 0x1B8E00` clamps it to 0.01..179). The frustum doubles l,r,b,t,n,f are at `0x002C60F8`.

## Culling
- `0x149680` builds 4 planes. Their angles are `(90 - k*FOV)` degrees, with `k_h = 0.375` (@`0x1496C0`) and `k_v = 0.28`
  (@`0x1498B4`). The planes are written to `0x2C9AA0..0x2C9B30`.

## Free RAM
- crt0 (`0x100008`) zero-fills `0x29EF00..0x500000` and calls `SetupHeap(0x500000, ...)`.
  A raw `lui` scan finds no code addressing `0x4A8000..0x4FFFFF` (BSS ends at `0x4A2B80`), and every
  savestate reads zero there. vrcam puts its cave at `0x4F0000` and its slots at `0x4F8000`.

## The vrcam patch
- `0x1B92A4` jal → cave. The cave runs glLoadIdentity, then glTranslatef(eye), then roll/pitch/yaw from the slots, then
  bumps `applied` (+0x38) and copies `pose_seq` (+0x40) into `pose_used` (+0x44).
- glFrustum's two scales and culling's two k values are `ld` from slot doubles (+0x00..+0x18),
  with stock defaults. Smaller scale = wider FOV; smaller k = wider culling.
- **Live checks still to do:** yaw sign, the HUD staying fixed, FOV widening, popping at the edges,
  and whether hit-testing follows the render view or the logic camera (plan Phase 1.7).


# 2026-10-20: frame timing & 90 Hz feasibility

Static only (Ghidra `ghidra-ps2` plus `look.py`, `refs.py` and raw-word scans), cross-checked against the existing RAM sweeps in
`re/ram/sweeps/*/ram*.bin`. Nothing was patched. Functions confirmed here are renamed `vr90_*` in Ghidra.
**Verified** means read in the disassembly or decompile. Anything else is marked *inferred*.

## "[Hz CHANGE]" is the camera's mains frequency, not the display
- The string (`0x2819C0`, table `0x258C04`) is camera-adjustment help: "If the red light is not still following the player's head
  correctly, please shoot [Hz CHANGE]". It is the USB camera's anti-flicker setting.
- Verified chain:
  - The panel handler toggles a short at obj+0x3C (`xori v0,v0,1` @`0x1C3428`).
  - It then calls `vr90_camSetMainsHz 0x1BE6C0`, which posts camera-thread command 3 to the mailbox `0x42FDA4`.
  - The mailbox dispatcher is `0x1BD870`. It calls driver vtable +0x2C, `vr90_camDrv_setFps25or30 0x225D00`.
  - Flag 0 gives 25 fps capture (50 Hz mains). Flag 1 gives 30 fps (60 Hz mains).
  - The rate is held at `0x49F638` (default 30, set in `0x2260C0`). The saved setting is the short `0x2C33C0`
    (written @`0x1C33A4`, read @`0x1C3124`/`0x1C6984`).
- **The display is hard-wired PAL.** The `SetGsCrt` stub `0x103EA0` (syscall 2) has one caller, `sceGsResetGraph 0x1001A0`.
  - The only live call to that is in `vr90_gfxInit_ResetGraphPAL 0x1CD2C0`, with immediates `(0, interlace=1, mode=3 PAL, field 0)`
    @`0x1CD2D8..E4`. Boot `0x132D30` calls it.
  - The NTSC call (mode 2) in `0x227DE8` is camera-library sample code. Its parent `0x227CC8` has no callers and no pointers to it.
  - No game code writes SMODE/SYNCH directly.
  - So the game has no 60 Hz video mode. A 60 Hz display would have to come from PCSX2.

## Frame timing: frame-locked to a vsync interval (verified)
- The vsync block lives at `0x2C6050` (pointer `$gp-0x6E28` = `0x29F248`), initialised by `vr90_vsyncInit 0x1D4D40`.
  | offset | contents |
  |---|---|
  | +0x00 | vsyncs since last flip |
  | +0x04 | total vsyncs |
  | +0x08 | **frame interval** (vsyncs per game frame) |
  | +0x10 | wait hook, `0x1D3E90` (semaphore wait) |
  | +0x14 | per-vsync hook, `0x1D3E80` (signals that semaphore) |
- The ISR `vr90_vblankIsr 0x1D4BB0` sits on INTC 2 (VBLANK_START, registered via `0x1016F8`). It does +0++, +4++, then calls +0x14.
- `vr90_waitVsyncInterval 0x1D4C80` waits one vsync, then `(interval - sinceFlip)` more, then zeroes +0.
  An overrun frame just slips. There is no catch-up.
- The block's accessors:
  - `vr90_getVsyncTotal 0x1D4C50`: 39 callers.
  - `vr90_setFrameInterval 0x1D4C60`: 29 callers, always with 1 or 2.
  - `vr90_getFrameInterval 0x1D4C70`: 47 callers.
- **Game time runs in 50 Hz vsync units, hard-coded.** Most interval callers compute `fps = interval==1 ? 50 : 25`, then compare
  per-tick counters against k*fps. Sites:
  `0x143F1C 0x144FC4 0x1471E8 0x148200 0x1489E0`, 14 sites in `0x18A180..0x18A850`, `0x194CDC..0x194ED4`,
  `0x1BA110 0x1BA164 0x1BA574 0x1BAA68 0x1D5104`.
- Six sites use `60/interval` instead: `0x1F5218 0x1F817C 0x1F8248 0x21A4E8 0x21ADCC 0x21D5B0`.
  *Inferred:* these are NTSC leftovers and run 20% long on PAL.
- Some per-tick steps are multiplied by the interval. Example: the fade `0x2251D0` steps by `interval*0.05` or `1/(32/interval)`.
- **No elapsed-time measurement anywhere:**
  - There is no `mfc0 $9` (Count) in the whole image.
  - The only EE timer access is boot `0x130B60` setting `T0_MODE=0x83`. No game code reads a timer or the RTC.
- **No global dt and no 50/60 speed scalar.** The ~100 sites that load `1.2f`/`50.0f` are ordinary scales.
  Per-tick deltas are baked into each call site.
- **Vsync-count timers that ignore the sim rate:**
  - The caption fader `0x13C670`: start stamped by `0x13C9A0` into `0x2C6F00`, elapsed = vsyncs>>1, source times ×25/30.
  - Blink phases `getVsyncTotal()&7` / `&0x1F` (`0x149148 0x13AA00 0x170B50 0x1862A0 0x18A884 0x1F8300`).
  - The fade `0x1B8040`.
  - The camera thread. It is registered on INTC 3 (VBLANK_END) by `0x1BDA50`, through `0x1BE2B0` → iSignalSema, so it gets one step per vsync.
- **Live cross-check (RAM sweeps):**
  - `aim1`, `aim2`, `aim_live*` and `aim_st1` have interval=2. Over 53.06 s: Δvsync 2653, Δframe 1327, i.e. 50.0 vsync/s and **25 fps**.
  - `fire1` has interval=1 (Δvsync = Δframe = 1175), i.e. **50 fps**.
  - Both sets were in top-level scene state 3. So the game runs some screens at 25 fps and some at 50.
- **Audio and FMV:**
  - Sound is a per-frame command pump to the IOP (`0x1C8A40`). Streaming (`SDSTR.IRX`) runs in IOP real time.
  - There is no FMV path: no IPU register or DMA ch3/4 references in the EE image.

## Main loop (verified)
`vr90_mainLoop 0x132F90` is called from crt0 @`0x1000A4`. Normal path (`0x2C241C==0`), once per iteration:
1. `vr90_frameBegin_kickDma_swap 0x1CFFC0`. It kicks the **previous** frame's packet (`0x101BA8`) from the double buffers in `0x499810`:
   - VIF packets: `0x580000` / `0x778000`, 0x1F8000 each.
   - Second pair: `0x970000` / `0x9B8000`.

   It also flips the draw and display envs (`0x101798`, `0x100E10`), resets the cursors (`0x1D01B0`), and increments the frame counter `0x499830`.
2. Read pads (`0x1D4820`) and check the reset combo (`0x1D4AF0`).
3. Run the sound/IOP pump `0x1C8A40`.
4. `0x133390` runs two steps:
   - `vr90_sceneStep 0x1335D0(0x2C6080)`: the scene table `0x22CF10`, **the simulation**.
   - `vr90_renderScene 0x133690`: `0x1B93E0` (fog/clear) plus `0x1B9180` (**the whole 3D + HUD render**).
5. Run the optional post hook `0x133360`, then `0x100F08` (sceGsSyncPath), then the vsync wait `0x1D4C80`.

One sim step per iteration. The render is a separate call after it, so it can be called twice.

What `0x1B9180` mutates (verified, but the per-object draw callbacks are not exhaustively audited):
- `0x149FB0` zeroes the active camera index `0x2C60C8` and reloads the projection.
- `0x149680` rewrites the culling planes.
- `0x14EF00` clears the per-object drawn bit on list `0x2E02B4`, picks LOD from the camera pose, and recounts `0x2FBEC0`.
- **One-shot queues the render consumes** (a second pass would see them empty):
  - draw hook `0x3A2EF8`: cleared in `0x179F40`; set by `0x17AA50`, `0x1F5670`, `0x1FB840`, `0x21B460`
  - 2D queue `0x2C9B74..[0x2C9B70]` and flags `0x2C9B60/61`: reset in `0x14A4B0`/`0x14A470`
  - callback queue `0x49F400`, count `0x49F440`: reset in `0x220890`
- All of it appends to the current ~2 MB packet buffer.
- *Not checked:*
  - whether two passes fit in that buffer
  - whether `0x14EC30` or the `0x1504C0`/`0x150400` object drawers advance animation state

## Feasibility verdicts
- **(a) 90 Hz sim at normal speed by patching dt: not feasible.** There is no dt to patch.
  - Game speed always equals vsync rate / 50, so a 90 Hz PCSX2 vsync runs everything 1.8× fast.
  - A correct 90 Hz sim would mean rescaling every baked per-tick literal plus the fps sites.
  - Even then these would break: captions and blinks (vsync-keyed), the 60/interval timers, cues against IOP-streamed audio,
    and the camera thread, which steps faster (*inferred* harmless).
- **(b) Two renders per tick: feasible, with work.**
  - Call `0x1B9180` twice from `0x133690`, using the vrcam eye offset.
  - Between passes, save and restore the three one-shot queues and `0x2C9B60/61`, or draw the HUD only once.
  - Retarget the draw between passes: either a half-width viewport or a second frame-buffer region.
  - Cost is about 2× EE/VU1 per tick. The 25 fps screens already have a spare vsync.
- **(c) Both (180 renders/s): not feasible**, because (a) isn't.
- **Better route (*inferred*, untested):** keep the 50 Hz sim and add render-only frames.
  - Run PCSX2's vsync at 90 Hz.
  - Patch `0x133390` so the sim step runs only when a 50 Hz accumulator, driven by the vsync total +0x04, says it is due.
  - Keep re-rendering `0x1B9180` every vsync with the latest head pose.
  - Sound stays in step because it is tick-driven. Vsync-keyed cosmetics run 1.8× fast.
  - Per-eye stereo on top of that means 180 renders/s and needs EE/VU overclocking.
  - The cheap alternative is 50 Hz stereo plus headset reprojection to 90 Hz.
