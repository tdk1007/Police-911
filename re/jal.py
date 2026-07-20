"""jal.py <vaddr> [...]  -- find every `jal <vaddr>` by decoding raw words.

Capstone silently skips R5900 opcodes it doesn't know, so call sites can be lost.
JAL is opcode 0b000011 with a 26-bit word-target, so we can just scan for it:
    word = 0x0C000000 | ((target & 0x0FFFFFFF) >> 2)
"""
import struct, sys
import mipslib as M

raw = open(M.ELF, 'rb').read()
code = raw[M.FOFF:M.FOFF + M.SIZE]
BASE = M.BASE

for a in sys.argv[1:]:
    va = int(a, 0)
    want = 0x0C000000 | ((va & 0x0FFFFFFF) >> 2)
    hits = []
    for off in range(0, len(code) - 3, 4):
        w = struct.unpack_from('<I', code, off)[0]
        if w == want:
            hits.append(BASE + off)
    print(f"\n=== jal 0x{va:08X}  ({len(hits)} call sites) ===")
    for h in hits:
        print(f"  called from 0x{h:08X}")
