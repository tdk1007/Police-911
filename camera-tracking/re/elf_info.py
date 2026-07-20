"""Parse the Police 24/7 EE executable (SLES_502.85) so we know where code lives
and how file offsets map to the PS2's virtual addresses."""
import struct, sys

PATH = r"C:\Users\tdk10\Claude Code\Police 911\extracted\SLES_502.85"
d = open(PATH, 'rb').read()

print(f"file size  : {len(d):,} bytes")
print(f"magic      : {d[:4]}")
print(f"class      : {d[4]} (1=ELF32)   endian: {d[5]} (1=little)")

e_machine = struct.unpack_from('<H', d, 18)[0]
e_entry   = struct.unpack_from('<I', d, 24)[0]
e_phoff   = struct.unpack_from('<I', d, 28)[0]
e_shoff   = struct.unpack_from('<I', d, 32)[0]
e_phnum   = struct.unpack_from('<H', d, 44)[0]
e_shnum   = struct.unpack_from('<H', d, 48)[0]

print(f"machine    : {e_machine}  (8 = MIPS)")
print(f"entry      : 0x{e_entry:08X}")
print(f"phnum      : {e_phnum} @ 0x{e_phoff:X}    shnum: {e_shnum} @ 0x{e_shoff:X}")

print("\nprogram headers (these are what actually get loaded to RAM):")
segs = []
for i in range(e_phnum):
    off = e_phoff + i * 32
    (p_type, p_offset, p_vaddr, p_paddr,
     p_filesz, p_memsz, p_flags, p_align) = struct.unpack_from('<8I', d, off)
    flag_s = "".join(c for c, b in zip("RWX", (4, 2, 1)) if p_flags & b)
    print(f"  [{i}] type={p_type} off=0x{p_offset:06X} vaddr=0x{p_vaddr:08X} "
          f"filesz=0x{p_filesz:06X} memsz=0x{p_memsz:06X} flags={flag_s}")
    if p_type == 1:
        segs.append((p_offset, p_vaddr, p_filesz))

# The mapping we need for every later step: vaddr <-> file offset
print("\nvaddr <-> file offset mapping for loadable segments:")
for off, va, sz in segs:
    print(f"  vaddr 0x{va:08X}..0x{va+sz:08X}  <-  file 0x{off:06X}..0x{off+sz:06X}"
          f"   (delta = vaddr - off = 0x{va-off:08X})")
