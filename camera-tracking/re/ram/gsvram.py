"""Pull framebuffers out of a savestate's GS.bin (GS local memory, PSMCT32 only).

With a hardware renderer the frames live on the GPU; set UserHacks = true and
UserHacks_ReadTCOnClose = true so a savestate flushes them into GS memory first.

    py gsvram.py STATE.p2s --frames OUTPREFIX     both contexts' FRAME buffers -> PNG
    py gsvram.py STATE.p2s --at FBP FBW W H OUT   any buffer (FBP in 2048-word units, FBW in 64 px)
"""
import argparse
import struct
import zipfile

import numpy as np
from PIL import Image

VM_OFF = 433                  # GSState::Freeze, STATE_VERSION 9 layout, before m_mem.m_vm8
CTXT0 = 4 + 15 * 8            # version + 15 env regs
FRAME_IDX, ZBUF_IDX = 10, 11  # within each 12-reg context block

BLOCK32 = np.array([[0, 1, 4, 5, 16, 17, 20, 21], [2, 3, 6, 7, 18, 19, 22, 23],
                    [8, 9, 12, 13, 24, 25, 28, 29], [10, 11, 14, 15, 26, 27, 30, 31]])
COLUMN32 = np.array([[0, 1, 4, 5, 8, 9, 12, 13], [2, 3, 6, 7, 10, 11, 14, 15],
                     [16, 17, 20, 21, 24, 25, 28, 29], [18, 19, 22, 23, 26, 27, 30, 31],
                     [32, 33, 36, 37, 40, 41, 44, 45], [34, 35, 38, 39, 42, 43, 46, 47],
                     [48, 49, 52, 53, 56, 57, 60, 61], [50, 51, 54, 55, 58, 59, 62, 63]])


def load(p2s):
    with zipfile.ZipFile(p2s) as z:
        gs = z.read('GS.bin')
    vm = np.frombuffer(gs, np.uint32, 1 << 20, VM_OFF)
    regs = lambda c, i: struct.unpack_from('<Q', gs, CTXT0 + (c * 12 + i) * 8)[0]
    return vm, regs


def read32(vm, fbp, fbw, w, h):
    """FBP in units of 2048 words (one page), FBW in units of 64 pixels."""
    y, x = np.mgrid[0:h, 0:w]
    page = (y // 32) * fbw + (x // 64)
    block = BLOCK32[(y % 32) // 8, (x % 64) // 8]
    word = fbp * 2048 + page * 2048 + block * 64 + COLUMN32[y % 8, x % 8]
    px = vm[word % (1 << 20)]
    rgb = np.stack([px & 0xFF, (px >> 8) & 0xFF, (px >> 16) & 0xFF], -1).astype(np.uint8)
    return Image.fromarray(rgb)


def frame_reg(v):
    return {'fbp': v & 0x1FF, 'fbw': (v >> 16) & 0x3F, 'psm': (v >> 24) & 0x3F}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('p2s')
    ap.add_argument('--frames')
    ap.add_argument('--at', nargs=5)
    ap.add_argument('--h', type=int, default=512)
    a = ap.parse_args()
    vm, regs = load(a.p2s)
    if a.frames:
        for c in (0, 1):
            f = frame_reg(regs(c, FRAME_IDX))
            print(f'ctxt{c} FRAME', f, 'ZBUF', hex(regs(c, ZBUF_IDX)))
            if f['psm'] == 0 and f['fbw']:
                read32(vm, f['fbp'], f['fbw'], f['fbw'] * 64, a.h).save(f'{a.frames}_c{c}.png')
    if a.at:
        fbp, fbw, w, h = map(lambda s: int(s, 0), a.at[:4])
        read32(vm, fbp, fbw, w, h).save(a.at[4])


if __name__ == '__main__':
    main()
