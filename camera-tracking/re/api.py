"""Find the camera module's public API: every jal target inside the camera code
range that is called from OUTSIDE it. Those callers are game code -- and the one
that consumes the image is the tracker."""
import struct, collections
import mipslib as M

raw  = open(M.ELF, 'rb').read()
code = raw[M.FOFF:M.FOFF + M.SIZE]
BASE = M.BASE

CAM_LO, CAM_HI = 0x00226000, 0x0022A000

# Decode every jal in the image straight from raw words (capstone-proof).
calls = collections.defaultdict(list)          # target -> [call sites]
for off in range(0, len(code) - 3, 4):
    w = struct.unpack_from('<I', code, off)[0]
    if (w >> 26) == 3:                          # JAL
        tgt = (w & 0x03FFFFFF) << 2
        tgt |= (BASE + off) & 0xF0000000
        calls[tgt].append(BASE + off)

print("=== camera-module functions called from OUTSIDE the camera module ===")
found = False
for tgt in sorted(calls):
    if not (CAM_LO <= tgt < CAM_HI):
        continue
    outside = [c for c in calls[tgt] if not (CAM_LO <= c < CAM_HI)]
    if outside:
        found = True
        print(f"\n  API 0x{tgt:08X}   called from {len(outside)} outside site(s):")
        for c in outside[:12]:
            print(f"      0x{c:08X}")
if not found:
    print("  (none -- the camera module is entirely table-dispatched)")

# Which game functions call the most camera APIs? Those are the camera clients.
print("\n=== callers ranked by how many distinct camera APIs they hit ===")
by_caller = collections.Counter()
for tgt, sites in calls.items():
    if CAM_LO <= tgt < CAM_HI:
        for c in sites:
            if not (CAM_LO <= c < CAM_HI):
                by_caller[c] += 1
for c, n in by_caller.most_common(20):
    print(f"  0x{c:08X}  hits {n} camera API(s)")
