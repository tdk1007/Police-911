# Police 911 arcade (Konami Viper) — body-sensor reverse engineering

Working notes. Verified against the running game in MAME 0.289 (`p911ud`,
"Police 911 (ver UAD)") unless marked as a hypothesis.

## Setup

- MAME 0.289 at `MAME/mame0289/`, ROMs at `MAME/mame0289/roms/p911ud/`
  (boot ROMs `941a01/941b01.u25`, `a00uad_nvram.u39`, `ds2430.u3`, CHDs
  `a00eaa02.chd` + `a00uad02.chd`). MAME's `p911ud` entry loads the
  **`a00eaa02`** disk.
- MAME driver status: `MACHINE_NOT_WORKING`; `p911` machine config has **no
  sensor inputs at all** (only gun X/Y, trigger, start, coins, DIPs).
- REA cannot open these targets (its ELF/PE/Mach-O arch list is x86/x64/ARM/ARM64
  only). All static work uses Ghidra 12.1.4 headless directly.

## Getting at the code

- The CF card is a FAT16 volume (partition at image offset `0x4000`) holding one
  30 MB file, `A00AAD02.BIN`: a 0x100-byte header (224-byte signature-like block)
  followed by compressed data. Not unpacked statically.
- Instead, main RAM (16 MB at `0x00000000`) is dumped from MAME after boot via a
  Lua autoboot script → `extracted/arcade/p911ud_ram_sensorbad.bin`. Strings and
  code are plaintext there. Load into Ghidra as `PowerPC:BE:32:default`, base 0,
  first 2 MB; seed functions at `stwu r1,-N(r1)` (`0x9421xxxx`) prologues.
- Code uses `r2` as a TOC base (`r2 = 0x0001323C` at the sensor screen); string
  addresses are mostly not reachable via `lis/addi`, so trace from I/O instead.

## Instrumentation gotchas (MAME Lua on Viper)

- `install_read_tap`/`install_write_tap` **crash MAME** on this 64-bit bus:
  upper-lane masks (`0xFFFFFFFF00000000`) can't be represented as Lua integers
  ("integer value will be misrepresented in lua"). Use debugger watchpoints
  set from Lua instead: run with `-debug -debugger none -log`, call
  `manager.machine.debugger:command('wpset ...,{logerror "...";g}')`; output
  lands in `error.log`. (`-debugscript` does not run under `-debugger none`.)
- Run headless (`-video none`); windowed runs stall when the window lacks focus.
  Snapshots still work headless.
- Writing to RAM before the game has initialised it corrupts boot — gate
  injection on the driver's init signature (below).

## Summary (current state)

- **Channel A = Konami factory programming jig** (`D`/`T` ASCII protocol below).
  Not needed for play; used once to program the NVRAM (region, RTC, DS2430 SID).
- **Channel B = the body sensor** (two overhead rangefinders, 4-byte binary
  packets). Emulated by `arcade-re/mame/p911_sensor.lua`.
- `Play Police 911 Arcade.bat` boots the game in MAME with the sensor emulated.
  Boot now passes SENSOR CHECKING and reaches the first-run operator prompt
  "PLEASE SET THE TIME FOR THE BOOKKEEPING" (set once in the test menu).

## Body sensor (DUART channel B) — verified

Channel B (`0xFFE00008`–`F`) is set up with divisor 26 and IER=`0x0D`
(interrupt-driven). Its ISR fills a 1 KB ring at `*(r2+0x5C)+0x400`
(= `0x33EBE8` with game-module `r2 = 0x000DCDF4`); u16 read/write indices at
`0x868`/`0x86A`. `FUN_00042c38` pops bytes (`0xE5` is an escape prefix) and
raises RTS via MCR (`0xFFE0000C`) when there is room.

Packet parser `FUN_00042980` (state in sensor struct `S = *(r2+0x60)` =
`0x33EFE8`, byte `S+0x54`):

| Byte | Constraint | Meaning |
|---|---|---|
| b0 | top two bits clear | sensor-bar bitmap A (6 bits) → `S+0x40` |
| b1 | top two bits clear | sensor-bar bitmap B (6 bits) → `S+0x41` |
| b2 | ≥ `0x20`, < `0xFD` | left range; `0x20` (space) = no echo |
| b3 | ≥ `0x20` | right range; `0x20` = no echo |

`FUN_00042714` turns (b2, b3) into the head position: X from `b2 - b3`,
height/depth from `b2 + b3 + 0x60` (smoothed, clamped, calibration constants at
`*(r2+0x64)`); `FUN_00042e44` is the game's position getter (2 floats).
Latest b2/b3 land at `S+0x38`/`S+0x3C` (shown as "SENSOR DATA" on I/O CHECK);
`S+0x44` counts consecutive bad packets.

Boot check (`FUN_00074ad0`): error 3 if `S+0x44 > 30`, error 1 if
`S+0x38 < 0x20`, error 2 if `S+0x3C < 0x20`, else OK. Boot state machine
`FUN_0009a800` (state byte `[0x545908+8]`): `0x26` starts the check, `0x27`
"SENSOR CHECKING", `0x28` OK, `0x29` "SENSOR BAD (-n)".

## Factory jig link (DUART channel A)

The jig talks to the game over **PC16552 DUART channel A**
(`0xFFE00000`–`0xFFE00007`). MAME's own comment: "likely connects to sensor
motion based games". Channel B (`0xFFE00008`–`F`) is a different link.

Init (`FUN_000128c4`, at boot ~frame 600): DLAB on, divisor `0x0037` (55),
8N1, FIFO on, MCR=0, IER=0 (polled, no interrupts). With MAME's unverified
19.6608 MHz clock that is ~22.3 kbaud; the true clock is unconfirmed and does
not matter for byte-level emulation. The game never transmits during the
I/O CHECK screen — the sensor streams unprompted.

Low-level driver (low RAM, called via stubs at `0x9FA0/0x9FD0/0xA000`):

| Address | Role |
|---|---|
| `0x128C4` | init UART + ring, schedule poll timer |
| `0x12988` | poll: while LSR.DR, read RBR; if no error bits, enqueue to ring |
| `0x12A58` | putc (TX), credit-limited by `0x1106`/`0x1107` |
| `0x12AB4` | getc from ring (0 if empty) |
| `0x12B2C` | disable (`0x1105 = 0`) |

Driver state: `0x1105` enabled flag, `0x1106` TX-empty, `0x1107` TX credit
(`0x10`); after init `0x1105 == 1 && 0x1107 == 0x10`.
**RX ring at `0x1108`:** `[0]` read index, `[1]` write index, 126 data bytes at
`+2` (indices wrap at `0x7E`).

## Packet protocol (ASCII, both directions)

```
'@'  '0'  <L: one hex digit>  <L payload bytes>  <checksum: two hex digits>
```

Checksum = sum of payload bytes; while > 0xFF subtract 0xFF. Hex digits are
`0-9A-F` (uppercase). Receive parser: `FUN_0009becc`; send: `FUN_0009c16c`
(with up to 3 retries); checksum builder `FUN_0009c394`.

Payload messages from the sensor (handler `FUN_0009bba4`):

| Message | Format | Stored |
|---|---|---|
| `D` | `D` + 2 hex digits (L=3) | session `+0x34` (byte) |
| `T` | `T` + 8 hex digits (L=9) | session `+0x30` (u32) |

Example frames: `@03D00A4`, `@09T00000000D5`.

Session state machine `FUN_0009bcf4`: drains the ring through the parser each
call. State 0 waits until both `+0x30` and `+0x34` are ≥ 0 (they start at -1);
otherwise after 25,000,000 timebase ticks (~1.5 s) it latches state `0xFF` and
returns **-1** → the "SENSOR ERROR(-1)" on I/O CHECK. The boot-time check shows
"SENSOR BAD (-3)" for the same missing device.

Hypothesis: the 32-bit `T` value is the sensor-bar bitmap (MAME notes describe
24 sensors in 8 bars of 3), and `D` is a status/distance byte. Not yet mapped.

## Injecting jig frames

`D`/`T` frames pushed into the ring at `0x1108` (gated on the init signature,
~frame 360) put the boot into the jig path (state `0x10` → `0x11`). With
constant or invalid `T` this ends in "PRODUCTION ERROR"; with a ticking real
time it reaches PRODUCTION MODE (next section). This was first mistaken for
the body sensor — the sensor check is separate (channel B, above).

## Jig messages = factory programming (PRODUCTION MODE)

Boot state `0x10` checks for the jig; if it answers, states `0x11`/`0x12` run
`FUN_0009c604(T, D)`:

- **`T`** = seconds since 2000-01-01 00:00:00 (`FUN_00021c50` converts to
  civil time). When `T` ticks, the game writes it to the M48T58 RTC
  (`FUN_00021dac`, BCD at `0xFFE31FF8`) and reads it back (`FUN_000219d0`);
  any mismatch → state `0x12` **"PRODUCTION ERROR"**. A non-ticking or invalid
  `T` causes this.
- **`D`** = distribution index 0–4 into the table at RAM `0xAE5EA`:
  0 `GQA00-JAD`, **1 `GKA00-UAD`**, 2 `GKA00-EAD`, 3 `GQA00-AAD`, 4 `GKA00-KAD`.

With a valid ticking `T` and `D01` the boot shows **PRODUCTION MODE**
(DISTRIBUTION GKA00-UAD, RTC TIME SETTING, SID = DS2430 serial `000000EEAA5C`)
and writes the NVRAM. MAME saves it on exit (`nvram/p911ud/m48t58`, 35 bytes
changed; pre-programming copy kept in `nvram/p911ud.backup-before-production`).
Later boots without the jig skip production mode — no PRODUCTION ERROR, no
security patching needed.
