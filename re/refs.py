"""refs.py <vaddr> [...]  -- who references these addresses (data or string)?"""
import sys
import mipslib as M

code, base = M.load()
insns = M.disasm(code)
refs = M.find_addr_refs(insns)
starts = M.find_functions(insns)

for a in sys.argv[1:]:
    va = int(a, 0)
    hits = refs.get(va, [])
    print(f"\n=== refs to 0x{va:08X} : {len(hits)} ===")
    for cva, mnem in hits:
        fn = M.func_containing(starts, cva)
        print(f"  0x{cva:08X}  {mnem:5s}  in func 0x{fn:08X}")
