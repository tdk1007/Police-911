"""look.py <vaddr> [n]  -- disassemble from an address, annotating string
references and call targets. Also: look.py xref <vaddr> -- who calls it."""
import re, sys
import mipslib as M

code, base = M.load()
raw = open(M.ELF, 'rb').read()
DELTA = 0x000FFF80

# recover strings once so we can annotate address references inline
STR = {}
for m in re.finditer(rb'[\x20-\x7e]{4,}', raw):
    STR[m.start() + DELTA] = m.group().decode('ascii', 'replace')


def cstr(va):
    return STR.get(va)


def dump(start, n=80):
    # Disassemble straight from the requested address. Words capstone can't
    # decode (R5900 MMI/COP2) are printed as raw data and stepped over, so a
    # single exotic opcode doesn't blind us to the rest of the function.
    sub = code[start - M.BASE: start - M.BASE + n * 4]
    insns = M.disasm(sub, base=start)
    lui = {}
    for ins in insns[:n]:
        note = ""
        ops = ins.op_str.replace(' ', '').split(',')
        if ins.mnemonic == 'lui' and len(ops) == 2:
            try:
                lui[ops[0]] = int(ops[1], 0) << 16
            except ValueError:
                pass
        elif ins.mnemonic in ('addiu', 'ori') and len(ops) == 3 and ops[1] in lui:
            try:
                lo = int(ops[2], 0)
                if ins.mnemonic == 'addiu' and lo >= 0x8000:
                    lo -= 0x10000
                tgt = (lui[ops[1]] + lo) & 0xFFFFFFFF
                s = cstr(tgt)
                note = f"   ; 0x{tgt:08X}" + (f'  "{s[:50]}"' if s else "")
            except ValueError:
                pass
        elif ins.mnemonic in ('lw', 'sw', 'lb', 'lbu', 'sb', 'lh', 'lhu', 'sh') and len(ops) == 2:
            mm = re.match(r'(-?\w+)\((\$\w+)\)', ops[1])
            if mm and mm.group(2) in lui:
                lo = int(mm.group(1), 0)
                if lo >= 0x8000:
                    lo -= 0x10000
                tgt = (lui[mm.group(2)] + lo) & 0xFFFFFFFF
                note = f"   ; global 0x{tgt:08X}"
        elif ins.mnemonic in ('jal', 'j'):
            try:
                tgt = int(ins.op_str, 0)
                note = f"   ; -> 0x{tgt:08X}"
            except ValueError:
                pass
        print(f"  0x{ins.address:08X}  {ins.mnemonic:<9s} {ins.op_str}{note}")


if __name__ == '__main__':
    if sys.argv[1] == 'xref':
        tgt = int(sys.argv[2], 0)
        insns = M.disasm(code)
        starts = M.find_functions(insns)
        cs = M.callers(insns, tgt)
        print(f"callers of 0x{tgt:08X}: {len(cs)}")
        for c in cs:
            print(f"  0x{c:08X}  (in func 0x{M.func_containing(starts, c):08X})")
    else:
        a = int(sys.argv[1], 0)
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 80
        dump(a, n)
