# Memory tooling — finding the tracker's output in EE RAM

The synthetic camera works, but it is a lossy round trip: a clean pose estimate
gets rasterised into a fake image, and a 2003 centroid tracker then re-estimates
it. Every quirk of that tracker — its motion requirement, its centroid drag, its
smoothing and latency — sits in the loop.

This directory is the way out. If we can find where the game *stores* the head
position it computed, we can write our own value there and the camera image stops
mattering. The head-finding algorithm itself is unrecoverable from capstone (it
is R5900 MMI SIMD, see `../RE_FINDINGS.md`) — but we do not need the algorithm,
only its output.

## The pieces

| File | What it does |
|---|---|
| `pine.py` | Client for PCSX2's PINE IPC server. Read/write EE memory, trigger savestates, query title and status. Batched bulk reads. |
| `snapshot.py` | Pulls `eeMemory.bin` out of a `.p2s` savestate (it is a zip) and memory-maps it. Also labels addresses with the regions `RE_FINDINGS.md` already identified. |
| `snap.py` | Drives the game through known head positions and takes a savestate at each. Writes `manifest.json`. |
| `hunt.py` | Correlates every aligned value in 32 MB of RAM against the commanded (or observed) head position. Ranks candidates. |
| `pine_selftest.py` | Validates the wire format against a fake PINE server. No PCSX2 needed. |
| `hunt_selftest.py` | Plants a known value in synthetic savestates and proves the hunt finds it — and rejects decoys. |

## The decoy problem

This is the part that makes or breaks the hunt.

A frame counter, a timer, a progress bar — all of them climb steadily as
snapshots are taken. Sweep `dx` in ascending order and every one of them
correlates with it at r = 1.000, burying the real hit under thousands of false
ones. Two defences, and both are on by default:

1. **`snap.py` shuffles the visit order** until the commanded position barely
   correlates with time, so "rises with time" and "rises with `dx`" stop being
   the same shape. It prints the correlation it achieved; `hunt.py` warns if a
   manifest was captured without it.
2. **Positions are revisited.** `hunt.py --repeat-tol` then demands a candidate
   return to its earlier value when the command returns to an earlier position.
   A counter never comes back down; the tracker's output must.

`hunt_selftest.py` proves both work: it plants a tracker value *and* a monotonic
frame counter *and* a wall clock, and asserts the first is found and the other
two are not.

## Running it

```
# once: PCSX2 needs its IPC server on
Play Police 24-7.bat -Motion synth -Pine

# with the game sitting somewhere the tracker is live, and pump.py already up
py snap.py --axis dx --out sweeps/dx
py hunt.py sweeps/dx/manifest.json --out sweeps/dx/candidates.json
```

`snap.py` records the game's own tracker dot next to each snapshot, read off the
screen by `../../synth/probe.py`. That gives `hunt.py --against dot` the option
of correlating against what the tracker actually concluded rather than what we
asked for — strictly better wherever the tracker is non-linear.

It also means `snap.py` can tell you the sweep was worthless before you spend
time hunting: if the dot never moved, it says so.

## After a hit

1. Confirm by writing: freeze the feed, `pine.write_f32(addr, v)` across a
   sweep, and watch the dot move. An address whose writes move the dot is the
   output.
2. Find the writer: PCSX2's debugger, write-breakpoint on that address, capture
   the storing instruction's PC.
3. Make it permanent: NOP that store from a pnach in
   `PCSX2/cheats/<serial>_<crc>.pnach`, so the game stops fighting our writes.
4. Record the address in `../RE_FINDINGS.md`.

## Addresses

EE RAM is mirrored at `0x00000000`, so an address under 32 MB is also its byte
offset into `eeMemory.bin` — the same number works for PINE and for the
savestate. `snapshot.describe()` annotates candidates that land in known regions
(the camera state struct at `0x0026B790`, the camera library at
`0x00226000`–`0x0022A000`, the MMI-dense pixel code near `0x001BCB00`).
