"""ptr.py <vaddr> [...]  -- find 32-bit little-endian words in the image whose
value equals vaddr. That finds function-pointer tables / vtables, which is how
this game reaches its camera API (the entry points have no direct `jal`)."""
import struct, sys
import mipslib as M

raw = open(M.ELF, 'rb').read()
DELTA = 0x000FFF80          # vaddr = file_off + DELTA

for a in sys.argv[1:]:
    va = int(a, 0)
    needle = struct.pack('<I', va)
    print(f"\n=== dwords equal to 0x{va:08X} ===")
    start = 0
    n = 0
    while True:
        i = raw.find(needle, start)
        if i < 0:
            break
        start = i + 1
        if i % 4:                       # only aligned words are real pointers
            continue
        print(f"  at file 0x{i:06X}  ->  vaddr 0x{i + DELTA:08X}")
        n += 1
    if not n:
        print("  none")
