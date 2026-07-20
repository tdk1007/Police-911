"""Shared MIPS/R5900 analysis helpers for the Police 24/7 EE executable.

The PS2 loads one segment: vaddr = file_offset + 0xFFF80. Everything here works
in PS2 virtual addresses, which is what PCSX2's debugger shows.
"""
import struct
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN

ELF   = r"C:\Users\tdk10\Claude Code\Police 911\extracted\SLES_502.85"
BASE  = 0x00100000      # vaddr of the loadable segment
FOFF  = 0x80            # its file offset
SIZE  = 0x19EF00        # its size

_md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
_md.detail = True

# $gp is loaded once in crt0 (0x0010005C: move $gp, $a0 after a0 = 0x002A6070).
# Small globals are addressed as imm($gp), so we need this to resolve them.
GP = 0x002A6070


def load():
    """Return (code_bytes, base_vaddr)."""
    d = open(ELF, 'rb').read()
    return d[FOFF:FOFF + SIZE], BASE


def word(code, va):
    off = va - BASE
    return struct.unpack_from('<I', code, off)[0]


def disasm(code, base=BASE):
    """Disassemble the whole segment.

    Capstone's MIPS32 mode doesn't know the R5900's MMI/COP2 extensions, and it
    STOPS at the first word it can't decode. MIPS instructions are a fixed 4
    bytes, so on a failure we skip that one word and resume -- otherwise we'd
    only ever see the first few dozen instructions.
    """
    out = []
    off = 0
    n = len(code)
    while off < n:
        got = False
        for ins in _md.disasm(code[off:], base + off):
            out.append(ins)
            off += ins.size
            got = True
        if not got:
            off += 4        # undecodable (R5900-specific) word -- skip it
    return out


def build_index(insns):
    """va -> instruction"""
    return {i.address: i for i in insns}


def find_addr_refs(insns):
    """Reconstruct addresses built by lui/addiu (and lui/ori, lui/lw) pairs.

    MIPS has no 32-bit immediates: code does `lui rX, hi` then `addiu rX, rX, lo`.
    We track the last lui per register and pair it with a following
    addiu/ori/lw/sw that uses the same register.

    Returns dict: target_address -> list of (code_va, mnemonic)
    """
    refs = {}
    lui = {}          # reg -> (hi_value, va)
    for ins in insns:
        m, ops = ins.mnemonic, ins.op_str.replace(' ', '').split(',')
        if m == 'lui' and len(ops) == 2:
            try:
                lui[ops[0]] = (int(ops[1], 0) << 16, ins.address)
            except ValueError:
                pass
            continue
        # addiu rD, rS, imm  -> full address if rS had a lui
        if m in ('addiu', 'ori') and len(ops) == 3 and ops[1] in lui:
            hi, _ = lui[ops[1]]
            try:
                lo = int(ops[2], 0)
            except ValueError:
                continue
            if m == 'addiu' and lo >= 0x8000:      # sign-extended
                lo -= 0x10000
            target = (hi + lo) & 0xFFFFFFFF
            refs.setdefault(target, []).append((ins.address, m))
            continue
        # lw rD, imm(rS) / sw rS, imm(rB) -> global variable access.
        # Base is either a register we just lui'd, or $gp (small-data section).
        if m in ('lw', 'sw', 'lb', 'lbu', 'lh', 'lhu', 'sb', 'sh') and len(ops) == 2:
            if '(' in ops[1] and ops[1].endswith(')'):
                imm_s, reg = ops[1][:-1].split('(')
                base_val = None
                if reg in lui:
                    base_val = lui[reg][0]
                elif reg == '$gp':
                    base_val = GP
                if base_val is not None:
                    try:
                        lo = int(imm_s, 0)
                    except ValueError:
                        continue
                    if lo >= 0x8000:
                        lo -= 0x10000
                    target = (base_val + lo) & 0xFFFFFFFF
                    refs.setdefault(target, []).append((ins.address, m))
        # any write to a reg invalidates its lui
        if ops and ops[0].startswith('$') and m not in ('lui',):
            lui.pop(ops[0], None)
    return refs


def find_functions(insns):
    """Recover function starts.

    A MIPS function that uses the stack starts with `addiu $sp, $sp, -N`.
    Leaf functions may not, so we also treat any jal/j target as a start.
    """
    starts = set()
    for ins in insns:
        if ins.mnemonic == 'addiu' and ins.op_str.replace(' ', '').startswith('$sp,$sp,-'):
            starts.add(ins.address)
        if ins.mnemonic in ('jal',):
            try:
                starts.add(int(ins.op_str, 0))
            except ValueError:
                pass
    return sorted(starts)


def func_containing(starts, va):
    """Which function start precedes va?"""
    lo, hi = 0, len(starts) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if starts[mid] <= va:
            best = starts[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def callers(insns, target):
    """All `jal target` sites."""
    out = []
    for ins in insns:
        if ins.mnemonic == 'jal':
            try:
                if int(ins.op_str, 0) == target:
                    out.append(ins.address)
            except ValueError:
                pass
    return out
