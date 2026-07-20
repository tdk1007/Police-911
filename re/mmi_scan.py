"""Find the SIMD image-processing code.

Capstone's MIPS32 mode can't decode the R5900's extensions, so the game's vision
loops are invisible to a plain disassembly. Invert that: the PS2's multimedia
opcodes ARE the fingerprint of pixel work. Scan raw words for them.

  opcode 0x1C (28) = MMI   -- 128-bit SIMD (padd/psub/pmax/pcmp/ppac...)
  opcode 0x1E (30) = LQ    -- load  quadword (128-bit)
  opcode 0x1F (31) = SQ    -- store quadword
  opcode 0x12 (18) = COP2  -- VU0 macro mode
"""
import struct, collections
import mipslib as M

raw  = open(M.ELF, 'rb').read()
code = raw[M.FOFF:M.FOFF + M.SIZE]
BASE = M.BASE

MMI, LQ, SQ, COP2 = 0x1C, 0x1E, 0x1F, 0x12

words = len(code) // 4
kinds = bytearray(words)
for i in range(words):
    w = struct.unpack_from('<I', code, i * 4)[0]
    op = w >> 26
    if op == MMI:
        kinds[i] = 1
    elif op in (LQ, SQ):
        kinds[i] = 2
    elif op == COP2:
        kinds[i] = 3

tot = collections.Counter(kinds)
print(f"{words:,} words   MMI={tot[1]:,}  LQ/SQ={tot[2]:,}  COP2/VU0={tot[3]:,}\n")

# sliding window: where is multimedia code densest?
WIN = 64
best = []
for i in range(0, words - WIN, 16):
    seg = kinds[i:i + WIN]
    n_mmi  = sum(1 for k in seg if k == 1)
    n_lqsq = sum(1 for k in seg if k == 2)
    n_cop2 = sum(1 for k in seg if k == 3)
    s = n_mmi * 3 + n_lqsq * 2 + n_cop2
    if s:
        best.append((s, BASE + i * 4, n_mmi, n_lqsq, n_cop2))

best.sort(reverse=True)
print("densest multimedia regions (these are the pixel loops):")
seen = []
for s, va, a, b, c in best:
    if any(abs(va - v) < 0x300 for v in seen):     # collapse neighbours
        continue
    seen.append(va)
    print(f"  0x{va:08X}  score={s:3d}   MMI={a:2d} LQ/SQ={b:2d} COP2={c:2d}")
    if len(seen) >= 20:
        break
