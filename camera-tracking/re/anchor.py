"""Anchor the camera subsystem: find the functions that reference the ovtVideo /
camera strings, then look at who calls them. The frame consumer (the tracker)
should be reachable from there."""
import mipslib as M

code, base = M.load()
insns = M.disasm(code)
print(f"disassembled {len(insns):,} instructions")

refs   = M.find_addr_refs(insns)
starts = M.find_functions(insns)
print(f"recovered {len(starts):,} function starts\n")

# strings we care about (from strings.py)
CAM_STRINGS = {
    0x002917E0: "ovtVideo_init(), unsupported video size",
    0x00291810: "ovtVideo_init(), unsupported video format",
    0x00291940: "ovtVideo_init(), unknown source",
    0x002919B8: "ovtVideo_load_cam()",
    0x002919D0: "ovtVideo_alllocate_cam()",
    0x00291A08: "ERROR: video not initialized.",
    0x00291BC8: "ovtVideo_attach(), resized image 1",
    0x00291968: "video source initialize error...",
    0x00291E28: "Error get video",
    0x0028F3C0: "USB camera is not connected.",
}

owners = {}
print("=== functions referencing camera strings ===")
for sva, txt in CAM_STRINGS.items():
    for cva, mnem in refs.get(sva, []):
        fn = M.func_containing(starts, cva)
        owners.setdefault(fn, set()).add(txt)
        print(f"  {txt[:44]:46s} used at 0x{cva:08X}  in func 0x{fn:08X}")

print("\n=== those functions, and who calls them ===")
for fn in sorted(owners):
    cs = M.callers(insns, fn)
    print(f"\nfunc 0x{fn:08X}  ({len(cs)} callers)")
    for s in sorted(owners[fn]):
        print(f"    handles: {s[:60]}")
    for c in cs[:8]:
        print(f"    called from 0x{c:08X} (in func 0x{M.func_containing(starts, c):08X})")
