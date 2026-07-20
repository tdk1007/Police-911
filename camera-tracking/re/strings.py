"""Dump ASCII strings from the EE ELF with their PS2 virtual addresses, and
highlight anything camera / sensor / tracking related."""
import re, sys

PATH  = r"C:\Users\tdk10\Claude Code\Police 911\extracted\SLES_502.85"
DELTA = 0x000FFF80          # vaddr = file_offset + DELTA (from elf_info.py)

d = open(PATH, 'rb').read()

strings = []
for m in re.finditer(rb'[\x20-\x7e]{4,}', d):
    strings.append((m.start() + DELTA, m.group().decode('ascii', 'replace')))

print(f"{len(strings):,} ASCII strings\n")

KEYWORDS = ('camera', 'cam', 'sensor', 'eye', 'webcam', 'noise', 'track',
            'head', 'motion', 'capture', 'image', 'video', 'usb', 'vision',
            'detect', 'thresh', 'edge', 'filter', 'light', 'bright')

want = sys.argv[1] if len(sys.argv) > 1 else None
if want:
    print(f"--- strings matching {want!r} ---")
    for va, s in strings:
        if want.lower() in s.lower():
            print(f"0x{va:08X}  {s}")
else:
    hits = {}
    for va, s in strings:
        low = s.lower()
        for k in KEYWORDS:
            if k in low:
                hits.setdefault(k, []).append((va, s))
                break
    for k in KEYWORDS:
        if k in hits:
            print(f"--- {k!r} ({len(hits[k])}) ---")
            for va, s in hits[k][:20]:
                print(f"  0x{va:08X}  {s}")
            print()
