"""Get at the EE main memory inside a PCSX2 savestate.

A .p2s file is a zip; `eeMemory.bin` inside it is the emulated PS2's 32 MB of
main RAM, dumped verbatim. Because EE RAM is mirrored at 0x00000000-0x01FFFFFF,
an EE address under 32 MB is also its byte offset into that file -- so an
address found here (say 0x0026B790) is the same number you hand to PINE.

Extraction is cached: the .bin is written next to the .p2s and reused unless the
savestate is newer, because a hunt re-reads the same dumps many times.
"""
import os
import zipfile

import numpy as np

EE_MEMBER = 'eeMemory.bin'
EE_SIZE = 32 * 1024 * 1024
EE_ADDR_MASK = 0x01FFFFFF


def extract_ee(p2s_path, cache_dir=None):
    """Unpack eeMemory.bin from a savestate. Returns the path to the .bin."""
    p2s_path = os.path.abspath(p2s_path)
    if not os.path.exists(p2s_path):
        raise FileNotFoundError(p2s_path)
    base = os.path.splitext(os.path.basename(p2s_path))[0]
    out_dir = cache_dir or os.path.dirname(p2s_path)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, base + '.eeMemory.bin')

    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(p2s_path):
        return out

    with zipfile.ZipFile(p2s_path) as z:
        names = z.namelist()
        if EE_MEMBER not in names:
            raise KeyError(f"{p2s_path} has no {EE_MEMBER} (members: {names[:12]})")
        with z.open(EE_MEMBER) as src, open(out, 'wb') as dst:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                dst.write(chunk)

    size = os.path.getsize(out)
    if size != EE_SIZE:
        raise ValueError(f"{out} is {size} B, expected {EE_SIZE} B of EE RAM")
    return out


def open_ee(p2s_path, dtype=np.uint8, cache_dir=None):
    """Memory-map a savestate's EE RAM as `dtype`, read-only.

    Memory-mapped rather than loaded: a hunt walks eight or more 32 MB dumps in
    lockstep, and mapping keeps that inside a few hundred MB instead of gigabytes.
    """
    return np.memmap(extract_ee(p2s_path, cache_dir), dtype=dtype, mode='r')


def addr_to_offset(addr):
    """EE address -> byte offset into eeMemory.bin."""
    return addr & EE_ADDR_MASK


def offset_to_addr(off):
    """Byte offset into eeMemory.bin -> the EE address PINE wants."""
    return off & EE_ADDR_MASK


def describe(addr):
    """Label an address with what the RE work already knows lives there.

    Addresses come from camera-tracking/re/RE_FINDINGS.md. A candidate landing in
    one of these regions is far more interesting than one in the middle of the heap.
    """
    regions = [
        (0x00100000, 0x0029EF00, 'EE executable (SLES_502.85 image)'),
        (0x001BCB00, 0x001BF400, 'MMI/SIMD-dense block -- camera client + pixel code'),
        (0x00226000, 0x0022A000, 'EE camera library (table-dispatched)'),
        (0x0026B790, 0x0026B7C0, 'camera state struct (+4 width, +8 height)'),
        (0x002917B0, 0x00291C00, 'camera jump tables / strings'),
    ]
    hits = [name for lo, hi, name in regions if lo <= addr < hi]
    return '; '.join(hits) if hits else ''


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        out = extract_ee(p)
        print(f"{p}\n  -> {out}  ({os.path.getsize(out)} B)")
