"""irx.py <file>  -- inspect an IOP module (IRX): sections, module name, and
identifier-like strings (filtering out the binary noise that plain `strings` hits).
IOP code is MIPS R3000A little-endian -- capstone decodes it fully (no MMI)."""
import re, struct, sys

path = sys.argv[1]
d = open(path, 'rb').read()
print(f"{path}\n  size {len(d):,}  magic {d[:4]}")

e_shoff = struct.unpack_from('<I', d, 32)[0]
e_shentsize = struct.unpack_from('<H', d, 46)[0]
e_shnum = struct.unpack_from('<H', d, 48)[0]
e_shstrndx = struct.unpack_from('<H', d, 50)[0]
print(f"  sections: {e_shnum} @ 0x{e_shoff:X}")

# section header string table
sh = lambda i: struct.unpack_from('<10I', d, e_shoff + i * e_shentsize)
if e_shnum:
    _, _, _, _, str_off, str_size, *_ = sh(e_shstrndx)
    shstr = d[str_off:str_off + str_size]
    print("\n  idx name                 type      addr       off      size")
    for i in range(e_shnum):
        name_i, s_type, flags, addr, off, size, *_ = sh(i)
        nm = shstr[name_i:shstr.index(b'\0', name_i)].decode('latin1')
        print(f"  {i:3d} {nm:20s} {s_type:<9d} 0x{addr:06X}  0x{off:06X} {size:8,}")

# identifier-ish strings only: mostly letters, low symbol noise
print("\n  === identifier-like strings ===")
seen = set()
for m in re.finditer(rb'[\x20-\x7e]{5,}', d):
    s = m.group().decode('ascii', 'replace')
    letters = sum(c.isalpha() for c in s)
    if letters >= max(5, len(s) * 0.7) and s not in seen:
        seen.add(s)
        print(f"    0x{m.start():06X}  {s}")
