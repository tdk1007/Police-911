"""List (and optionally extract) files from the Police 24/7 disc.

The .cue says MODE2/2352: each raw sector is 2352 bytes with 2048 bytes of user
data at offset 24. ISO9660's PVD lives at LBA 16.
"""
import struct, sys, os

BIN = r"C:\Users\tdk10\Claude Code\Police 911\Police 24-7 (Europe) (En,Fr,De,Es,It)\Police 24-7 (Europe) (En,Fr,De,Es,It).bin"
RAW, DATA_OFF, DATA_LEN = 2352, 24, 2048

f = open(BIN, 'rb')


def sector(lba):
    f.seek(lba * RAW + DATA_OFF)
    return f.read(DATA_LEN)


def read(lba, nbytes):
    out = b''
    while len(out) < nbytes:
        out += sector(lba)
        lba += 1
    return out[:nbytes]


def walk(lba, size, path=""):
    data = read(lba, size)
    i = 0
    while i < len(data):
        rec_len = data[i]
        if rec_len == 0:
            i = (i // DATA_LEN + 1) * DATA_LEN     # next sector
            if i >= len(data):
                break
            continue
        ext_lba  = struct.unpack_from('<I', data, i + 2)[0]
        ext_size = struct.unpack_from('<I', data, i + 10)[0]
        flags    = data[i + 25]
        nlen     = data[i + 32]
        name     = data[i + 33:i + 33 + nlen].decode('latin1')
        if name not in ('\x00', '\x01'):
            clean = name.split(';')[0]
            full = f"{path}/{clean}"
            if flags & 2:
                print(f"  [DIR ] {full}")
                walk(ext_lba, ext_size, full)
            else:
                yield_name = full
                print(f"  {ext_size:>10,}  {yield_name}   (lba {ext_lba})")
                FILES.append((yield_name, ext_lba, ext_size))
        i += rec_len


FILES = []
pvd = sector(16)
print("volume id:", pvd[40:72].decode('latin1').strip())
root = pvd[156:190]
root_lba  = struct.unpack_from('<I', root, 2)[0]
root_size = struct.unpack_from('<I', root, 10)[0]
print(f"root dir @ lba {root_lba}, {root_size} bytes\n")
print("=== disc contents ===")
list(walk(root_lba, root_size))

print(f"\n{len(FILES)} files")

if len(sys.argv) > 2 and sys.argv[1] == 'extract':
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for name, lba, size in FILES:
        base = name.strip('/').replace('/', '_')
        p = os.path.join(outdir, base)
        with open(p, 'wb') as o:
            o.write(read(lba, size))
        print(f"extracted {base} ({size:,})")
