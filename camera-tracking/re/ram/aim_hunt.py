"""Find the crosshair's absolute X/Y in EE RAM.

The gun is PCSX2's USB HID mouse fed from the host pointer (Pointer-0), so we
move the Windows cursor with SendInput while PCSX2 is focused, hold the head at
an exposed position so the reticle is drawn, and at each stop dump all 32 MB of
EE RAM over PINE plus a screenshot. The reticle's on-screen centre (green ring)
is the reference we correlate against, so mouse acceleration doesn't matter.

Positions are revisited in shuffled order (see README "The decoy problem").

    py aim_hunt.py capture --out sweeps/aim1 [--steps 24]
    py aim_hunt.py hunt sweeps/aim1
"""
import argparse, ctypes, json, os, random, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, '..', '..', 'synth')]
import pine as P
import hook as H

EE_SIZE = 32 * 1024 * 1024
u32 = ctypes.windll.user32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', ctypes.c_ulong),
                ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    _fields_ = [('type', ctypes.c_ulong), ('mi', MOUSEINPUT)]


def mouse_move(dx, dy, steps=10):
    """Relative move in small chunks, like a real mouse."""
    sx, sy = 0, 0
    for i in range(1, steps + 1):
        tx, ty = round(dx * i / steps), round(dy * i / steps)
        inp = INPUT(0, MOUSEINPUT(tx - sx, ty - sy, 0, 0x0001, 0, None))
        u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        sx, sy = tx, ty
        time.sleep(0.01)


def reticle(img):
    """Centre of the green aiming ring, or None."""
    import cv2
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (50, 120, 90), (75, 255, 255))
    ys, xs = np.nonzero(m)
    if len(xs) < 30:
        return None
    # the ring is the dominant green cluster; median is robust to stray pixels
    cx, cy = float(np.median(xs)), float(np.median(ys))
    keep = (abs(xs - cx) < 120) & (abs(ys - cy) < 120)
    return float(xs[keep].mean()), float(ys[keep].mean()), int(keep.sum())


def focus_pcsx2():
    import subprocess
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    "$p=Get-Process pcsx2* | ?{$_.MainWindowTitle} | select -f 1;"
                    "Add-Type -Name W -Namespace X -MemberDefinition "
                    "'[DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr h);';"
                    "[X.W]::SetForegroundWindow($p.MainWindowHandle)"], capture_output=True)


def capture(args):
    import cv2, probe
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)
    # a grid of target offsets (host pixels), each visited twice in shuffled order
    xs = [-300, -150, 0, 150, 300]
    ys = [-150, 0, 150]
    targets = [(x, y) for x in xs for y in ys]
    order = targets + targets
    rng.shuffle(order)
    order = order[:args.steps]

    with P.Pine() as p:
        H.enable(p)

        # with the guards NOPed the game never stores HEAD_X/Y, so one write sticks
        H.set_head(p, args.head_x, args.head_y)
        try:
            focus_pcsx2()
            time.sleep(0.5)
            cur = (0, 0)
            snaps = []
            for i, tgt in enumerate(order):
                mouse_move(tgt[0] - cur[0], tgt[1] - cur[1])
                cur = tgt
                time.sleep(args.settle)
                ram = p.read_block(0, EE_SIZE)
                img = probe.grab()
                ram2 = p.read_block(0, EE_SIZE) if args.double else None
                fn = os.path.join(args.out, f'ram{i:02d}.bin')
                with open(fn, 'wb') as f:
                    f.write(ram)
                if ram2 is not None:
                    with open(fn + '.b', 'wb') as f:
                        f.write(ram2)
                r = reticle(img)
                cv2.imwrite(os.path.join(args.out, f'shot{i:02d}.jpg'),
                            cv2.resize(img, (img.shape[1] // 3, img.shape[0] // 3)))
                rec = {'i': i, 'cmd_x': tgt[0], 'cmd_y': tgt[1], 'path': os.path.basename(fn),
                       't': time.time()}
                if r:
                    rec['ret_x'], rec['ret_y'], rec['ret_n'] = r
                snaps.append(rec)
                print(f'[{i + 1:2d}/{len(order)}] cmd=({tgt[0]:+4d},{tgt[1]:+4d}) '
                      f'reticle={"(%.0f,%.0f) n=%d" % r if r else "none"}', flush=True)
            mouse_move(-cur[0], -cur[1])
        finally:
            H.set_head(p, *H.NEUTRAL)
    with open(os.path.join(args.out, 'manifest.json'), 'w') as f:
        json.dump({'head': [args.head_x, args.head_y], 'snapshots': snaps}, f, indent=1)


def live(args):
    """The player aims by hand; we sample RAM + screenshot on a fixed cadence.

    J/L/M keyboard lean (lean_keys.KeyLean) runs in-process on the same PINE
    connection, so the player can lean out to make the reticle visible. A sample
    is kept only if the reticle is found AND two RAM reads bracketing the
    screenshot agree at the reticle candidates -- enforced later in hunt by
    requiring the A and B dumps to match.
    """
    import cv2, probe, threading, winsound
    from lean_keys import KeyLean
    os.makedirs(args.out, exist_ok=True)
    lock = threading.Lock()
    stop = threading.Event()
    with P.Pine() as p:
        H.enable(p)
        kl = KeyLean(p, lock)

        def keys():
            while not stop.is_set():
                kl.step()
                time.sleep(1 / 120)
        th = threading.Thread(target=keys, daemon=True)
        th.start()
        snaps = []
        try:
            winsound.Beep(880, 300)
            t0 = time.time()
            i = 0
            while time.time() - t0 < args.seconds:
                with lock:
                    ram = p.read_block(0, EE_SIZE)
                img = probe.grab()
                with lock:
                    ram2 = p.read_block(0, EE_SIZE)
                r = reticle(img)
                if r:
                    a = np.frombuffer(ram, np.uint8)
                    b = np.frombuffer(ram2, np.uint8)
                    stable = np.where(a == b, a, 0).astype(np.uint8)  # moving bytes -> 0
                    fn = os.path.join(args.out, f'ram{i:03d}.bin')
                    stable.tofile(fn)
                    cv2.imwrite(os.path.join(args.out, f'shot{i:03d}.jpg'),
                                cv2.resize(img, (img.shape[1] // 4, img.shape[0] // 4)))
                    snaps.append({'i': i, 'path': os.path.basename(fn), 't': time.time() - t0,
                                  'ret_x': r[0], 'ret_y': r[1], 'ret_n': r[2]})
                    print(f'[{time.time() - t0:5.1f}s] reticle=({r[0]:.0f},{r[1]:.0f}) n={r[2]}',
                          flush=True)
                    i += 1
                time.sleep(args.interval)
            winsound.Beep(440, 200); winsound.Beep(440, 200)
        finally:
            stop.set()
            th.join()
            H.set_head(p, *H.NEUTRAL)
    with open(os.path.join(args.out, 'manifest.json'), 'w') as f:
        json.dump({'mode': 'live', 'snapshots': snaps}, f, indent=1)
    print(f'{len(snaps)} samples with a visible reticle')


def states(args):
    """Like live, but each sample is a savestate: its eeMemory.bin and
    Screenshot.png come from the same frame, so a moving aim can't desync them."""
    import cv2, shutil, threading, winsound, zipfile
    import snap
    from lean_keys import KeyLean
    os.makedirs(args.out, exist_ok=True)
    lock, stop = threading.Lock(), threading.Event()
    snaps = []
    with P.Pine() as p:
        H.enable(p)
        kl = KeyLean(p, lock)

        def keys():
            while not stop.is_set():
                kl.step()
                time.sleep(1 / 120)
        th = threading.Thread(target=keys, daemon=True)
        th.start()
        try:
            winsound.Beep(880, 300)
            t0, i = time.time(), 0
            while time.time() - t0 < args.seconds:
                before = snap.state_snapshot(snap.SSTATES)
                with lock:
                    p.save_state(args.slot)
                src = snap.wait_for_state(snap.SSTATES, before)
                with zipfile.ZipFile(src) as z:
                    ram = z.read('eeMemory.bin')
                    png = z.read('Screenshot.png')
                img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
                r = reticle(img)
                fn = os.path.join(args.out, f'ram{i:03d}.bin')
                with open(fn, 'wb') as f:
                    f.write(ram)
                with open(os.path.join(args.out, f'shot{i:03d}.png'), 'wb') as f:
                    f.write(png)
                rec = {'i': i, 'path': os.path.basename(fn), 't': time.time() - t0,
                       'w': img.shape[1], 'h': img.shape[0]}
                if r:
                    rec['ret_x'], rec['ret_y'], rec['ret_n'] = r
                snaps.append(rec)
                print(f'[{rec["t"]:5.1f}s] reticle={"(%.0f,%.0f) n=%d" % r if r else "none"}',
                      flush=True)
                i += 1
            winsound.Beep(440, 200); winsound.Beep(440, 200)
        finally:
            stop.set()
            th.join()
            H.set_head(p, *H.NEUTRAL)
    with open(os.path.join(args.out, 'manifest.json'), 'w') as f:
        json.dump({'mode': 'states', 'snapshots': snaps}, f, indent=1)
    print(f'{sum("ret_x" in s for s in snaps)}/{len(snaps)} samples with a visible reticle')


def buttons(args):
    """Find the fire/trigger state: beep-cued hold/release phases, savestates in each.

    High beep = hold the trigger, low beep = release. Two savestates per phase
    (skipping the first moment after the cue, while the player reacts). The hunt
    then keeps bytes that are constant within every phase and differ between
    held and released.
    """
    import shutil, threading, winsound, zipfile
    import snap
    from lean_keys import KeyLean
    os.makedirs(args.out, exist_ok=True)
    lock, stop = threading.Lock(), threading.Event()
    snaps = []
    with P.Pine() as p:
        H.enable(p)
        kl = KeyLean(p, lock)

        def keys():
            while not stop.is_set():
                kl.step()
                time.sleep(1 / 120)
        th = threading.Thread(target=keys, daemon=True)
        th.start()
        try:
            i = 0
            for ph in range(args.phases):
                held = ph % 2 == 0
                winsound.Beep(1200 if held else 400, 250)
                time.sleep(args.react)
                for _ in range(2):
                    before = snap.state_snapshot(snap.SSTATES)
                    with lock:
                        p.save_state(args.slot)
                    src = snap.wait_for_state(snap.SSTATES, before)
                    with zipfile.ZipFile(src) as z:
                        ram = z.read('eeMemory.bin')
                        iop = z.read('iopMemory.bin')
                    fn = os.path.join(args.out, f'ram{i:03d}.bin')
                    open(fn, 'wb').write(ram)
                    open(os.path.join(args.out, f'iop{i:03d}.bin'), 'wb').write(iop)
                    snaps.append({'i': i, 'path': os.path.basename(fn), 'held': held,
                                  'phase': ph})
                    print(f'phase {ph} {"HELD" if held else "released"} -> {fn}', flush=True)
                    i += 1
            winsound.Beep(440, 200); winsound.Beep(440, 200)
        finally:
            stop.set()
            th.join()
            H.set_head(p, *H.NEUTRAL)
    with open(os.path.join(args.out, 'manifest.json'), 'w') as f:
        json.dump({'mode': 'buttons', 'snapshots': snaps}, f, indent=1)


def button_hunt(args):
    man = json.load(open(os.path.join(args.dir, 'manifest.json')))['snapshots']
    held = np.array([s['held'] for s in man])
    for kind, size in (('ram', EE_SIZE), ('iop', 2 * 1024 * 1024)):
        stack = np.stack([np.fromfile(os.path.join(args.dir, f'{kind}{s["i"]:03d}.bin'),
                                      dtype=np.uint8) for s in man])
        h, r = stack[held], stack[~held]
        ok = (h.min(0) == h.max(0)) & (r.min(0) == r.max(0)) & (h[0] != r[0])
        idx = np.nonzero(ok)[0]
        print(f'{kind}: {len(idx)} bytes constant-per-state and different')
        for a in idx[:args.top]:
            print(f'  {kind} 0x{a:08X}  held={h[0, a]:#04x} released={r[0, a]:#04x}')


def corr_scan(stack, ref, min_r):
    """Pearson r of each column of stack (n, m) against ref (n,)."""
    x = ref - ref.mean()
    s = stack.astype(np.float64)
    s -= s.mean(axis=0)
    num = x @ s
    den = np.sqrt((s * s).sum(axis=0)) * np.sqrt((x * x).sum())
    with np.errstate(invalid='ignore', divide='ignore'):
        r = num / den
    r[~np.isfinite(r)] = 0
    return r


def hunt(args):
    man = json.load(open(os.path.join(args.dir, 'manifest.json')))
    snaps = [s for s in man['snapshots'] if 'ret_x' in s] if args.against == 'reticle' \
        else man['snapshots']
    print(f'{len(snaps)} usable snapshots')
    key = {'reticle': ('ret_x', 'ret_y'), 'cmd': ('cmd_x', 'cmd_y')}[args.against]
    maps = [np.memmap(os.path.join(args.dir, s['path']), dtype=np.uint8, mode='r')
            for s in snaps]
    refs = {axis: np.array([s[k] for s in snaps], dtype=np.float64)
            for axis, k in zip('xy', key)}
    CH = 1 << 20                                   # bytes per chunk
    found = {('x', e): [] for e in ('i16', 'i32', 'f32')}
    found.update({('y', e): [] for e in ('i16', 'i32', 'f32')})
    for off in range(0, EE_SIZE, CH):
        block = np.stack([m[off:off + CH] for m in maps])
        for enc, dt in (('i16', np.int16), ('i32', np.int32), ('f32', np.float32)):
            stack = block.view(dt)
            if dt == np.float32:
                stack = np.where(np.isfinite(stack) & (np.abs(stack) < 1e6), stack, 0)
            rng = stack.max(axis=0).astype(np.float64) - stack.min(axis=0)
            for axis, ref in refs.items():
                r = corr_scan(stack, ref, args.min_r)
                for h in np.nonzero((np.abs(r) >= args.min_r) & (rng >= 2))[0]:
                    found[(axis, enc)].append((abs(r[h]), off + h * stack.itemsize, float(r[h]),
                                               [float(v) for v in stack[:, h]]))
    out = {}
    for (axis, enc), hits in found.items():
        for _, addr, r, vals in sorted(hits, reverse=True)[:args.top]:
            print(f'{axis} {enc} 0x{addr:08X} r={r:+.4f} range=[{min(vals)}, {max(vals)}]')
            out.setdefault(axis, []).append({'addr': int(addr), 'enc': enc, 'r': r, 'vals': vals})
    with open(os.path.join(args.dir, 'candidates.json'), 'w') as f:
        json.dump(out, f, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--out', required=True)
    c.add_argument('--steps', type=int, default=30)
    c.add_argument('--settle', type=float, default=0.35)
    c.add_argument('--seed', type=int, default=911)
    c.add_argument('--head-x', type=int, default=0)
    c.add_argument('--head-y', type=int, default=71)
    c.add_argument('--double', action='store_true')
    lv = sub.add_parser('live')
    lv.add_argument('--out', required=True)
    lv.add_argument('--seconds', type=float, default=45)
    lv.add_argument('--interval', type=float, default=0.3)
    st = sub.add_parser('states')
    st.add_argument('--out', required=True)
    st.add_argument('--seconds', type=float, default=45)
    st.add_argument('--slot', type=int, default=8)
    b = sub.add_parser('buttons')
    b.add_argument('--out', required=True)
    b.add_argument('--phases', type=int, default=8)
    b.add_argument('--react', type=float, default=1.2)
    b.add_argument('--slot', type=int, default=8)
    bh = sub.add_parser('button-hunt')
    bh.add_argument('dir')
    bh.add_argument('--top', type=int, default=40)
    h = sub.add_parser('hunt')
    h.add_argument('dir')
    h.add_argument('--against', choices=['reticle', 'cmd'], default='reticle')
    h.add_argument('--min-r', type=float, default=0.99)
    h.add_argument('--top', type=int, default=25)
    a = ap.parse_args()
    {'capture': capture, 'live': live, 'states': states, 'buttons': buttons,
     'button-hunt': button_hunt, 'hunt': hunt}[a.cmd](a)


if __name__ == '__main__':
    main()
