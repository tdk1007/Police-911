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
