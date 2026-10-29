"""Minimal minidump reader: exception, faulting thread's stack scan, symbolized via llvm-symbolizer.

    py -I vr/crashdump.py <dump> <exe> <llvm-symbolizer>

llvm-symbolizer: VS Build Tools VC/Tools/Llvm/x64/bin. The PDB must sit next to the exe.
"""
import struct
import subprocess
import sys

dump, exe, symbolizer = sys.argv[1:4]
d = open(dump, 'rb').read()
sig, ver, nstreams, dir_rva = struct.unpack_from('<IIII', d, 0)
assert sig == 0x504D444D, 'not a minidump'
streams = {}
for i in range(nstreams):
    t, size, rva = struct.unpack_from('<III', d, dir_rva + 12 * i)
    streams.setdefault(t, (size, rva))


def utf16(rva):
    n = struct.unpack_from('<I', d, rva)[0]
    return d[rva + 4:rva + 4 + n].decode('utf-16-le')


# modules (stream 4)
mods = []
size, rva = streams[4]
n = struct.unpack_from('<I', d, rva)[0]
for i in range(n):
    off = rva + 4 + 108 * i
    base, msize = struct.unpack_from('<QI', d, off)
    name_rva = struct.unpack_from('<I', d, off + 20)[0]
    mods.append((base, msize, utf16(name_rva)))


def where(addr):
    for base, msize, name in mods:
        if base <= addr < base + msize:
            return base, name
    return None, None


# exception (stream 6)
size, rva = streams[6]
tid = struct.unpack_from('<I', d, rva)[0]
code, flags = struct.unpack_from('<II', d, rva + 8)
addr = struct.unpack_from('<Q', d, rva + 8 + 16)[0]
nparams = struct.unpack_from('<I', d, rva + 8 + 24)[0]
params = struct.unpack_from('<15Q', d, rva + 8 + 32)[:nparams]
print(f'thread {tid} exception {code:08x} at {addr:016x} params {[hex(p) for p in params]}')

# thread list (stream 3): find the faulting thread's stack
size, rva = streams[3]
n = struct.unpack_from('<I', d, rva)[0]
stack = None
for i in range(n):
    off = rva + 4 + 48 * i
    t = struct.unpack_from('<I', d, off)[0]
    if t == tid:
        start, ssize, srva = struct.unpack_from('<QII', d, off + 24)
        stack = (start, d[srva:srva + ssize])

base_exe = next(b for b, s, nm in mods if nm.lower().endswith(exe.lower().split('\\')[-1].split('/')[-1]))
cands = [addr]
if stack:
    _, mem = stack
    for o in range(0, min(len(mem), 0x4000), 8):
        v = struct.unpack_from('<Q', mem, o)[0]
        b, nm = where(v)
        if b == base_exe:
            cands.append(v)
seen = []
for a in cands:
    if a not in seen:
        seen.append(a)
for a in seen[:40]:
    b, nm = where(a)
    if b != base_exe:
        print(f'{a:016x} {nm}')
        continue
    out = subprocess.run([symbolizer, f'--obj={exe}', f'0x{0x140000000 + a - b:x}'],
                         capture_output=True, text=True).stdout.split('\n')
    print(f'{a:016x} {out[0]}  {out[1].split("Police 911")[-1] if len(out) > 1 else ""}')
