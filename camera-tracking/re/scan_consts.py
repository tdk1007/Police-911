"""Find candidate image-processing code: functions whose immediates look like
image dimensions / pixel counts, and which contain tight byte-wise loops."""
import collections
import mipslib as M

code, base = M.load()
insns = M.disasm(code)
starts = M.find_functions(insns)

# Dimensions an EyeToy-era tracker would plausibly work at, plus their areas.
DIMS = {
    320: "320 (w)", 240: "240 (h)", 160: "160", 120: "120",
    80: "80", 60: "60", 64: "64", 48: "48", 32: "32",
    76800: "320*240", 38400: "160*240", 19200: "160*120",
    4800: "80*60", 9600: "80*120",
}

# bucket instructions by function
fn_of = {}
by_fn = collections.defaultdict(list)
for ins in insns:
    f = M.func_containing(starts, ins.address)
    by_fn[f].append(ins)

score = {}
for fn, ilist in by_fn.items():
    dims = collections.Counter()
    nbyte_load = 0     # lb/lbu  -> per-pixel reads
    nbyte_store = 0    # sb      -> writing a processed image
    nbranch = 0
    nmul = 0
    for ins in ilist:
        ops = ins.op_str.replace(' ', '')
        if ins.mnemonic in ('lb', 'lbu'):
            nbyte_load += 1
        if ins.mnemonic == 'sb':
            nbyte_store += 1
        if ins.mnemonic.startswith('b'):
            nbranch += 1
        if ins.mnemonic in ('mult', 'multu', 'mul'):
            nmul += 1
        # immediates
        for tok in ops.split(','):
            try:
                v = int(tok, 0)
            except ValueError:
                continue
            if v in DIMS:
                dims[v] += 1
    # a pixel loop: reads bytes, branches a lot, and knows an image dimension
    if nbyte_load >= 2 and dims and nbranch >= 2:
        s = nbyte_load * 2 + nbyte_store * 3 + sum(dims.values()) * 4
        score[fn] = (s, dict(dims), nbyte_load, nbyte_store, len(ilist))

print(f"{len(by_fn)} functions; {len(score)} look like pixel loops\n")
print("top candidates (score, dims seen, lb/lbu, sb, size):")
for fn, (s, dims, nl, ns, sz) in sorted(score.items(), key=lambda kv: -kv[1][0])[:25]:
    ds = " ".join(f"{DIMS[k]}x{v}" for k, v in sorted(dims.items()))
    print(f"  0x{fn:08X}  score={s:4d}  lb={nl:3d} sb={ns:3d} insns={sz:4d}   [{ds}]")
