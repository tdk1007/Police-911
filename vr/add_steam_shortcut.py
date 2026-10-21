"""Add "Police 24-7 (VR)" to Steam as a non-Steam game.

    py add_steam_shortcut.py            # needs Steam closed
    py add_steam_shortcut.py --restart  # shut Steam down, add it, start Steam again

Why: a non-VR game launched FROM Steam while SteamVR runs is shown on the
Theater screen with the dashboard hidden, so controller input can reach
frame_bridge (the dashboard keeps every button while it shows PCSX2), and Steam
Input can remap the Frame controllers for the game.

Steam rewrites userdata/<id>/config/shortcuts.vdf on exit, so it must be closed
while this edits it. A timestamped backup is written next to the file.
"""
import argparse, glob, os, shutil, struct, subprocess, sys, time, zlib

STEAM = r'C:\Program Files (x86)\Steam'
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = 'Police 24-7 (VR)'
EXE = r'"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"'
OPTS = (f'-NoProfile -ExecutionPolicy Bypass -File "{os.path.join(ROOT, "Play-Police247.ps1")}" '
        f'-Vr')
ICON = os.path.join(ROOT, 'PCSX2', 'pcsx2-qt.exe')


def load(b, i=0):
    d = {}
    while True:
        t = b[i]; i += 1
        if t == 8:
            return d, i
        e = b.index(0, i); k = b[i:e].decode('utf-8'); i = e + 1
        if t == 0:
            v, i = load(b, i)
        elif t == 1:
            e = b.index(0, i); v = b[i:e].decode('utf-8'); i = e + 1
        elif t == 2:
            v = struct.unpack_from('<I', b, i)[0]; i += 4
        else:
            raise ValueError(f'unknown VDF type {t} at {i}')
        d[k] = v


def dump(d):
    out = bytearray()
    for k, v in d.items():
        kb = k.encode('utf-8') + b'\0'
        if isinstance(v, dict):
            out += b'\0' + kb + dump(v) + b'\x08'
        elif isinstance(v, int):
            out += b'\x02' + kb + struct.pack('<I', v)
        else:
            out += b'\x01' + kb + v.encode('utf-8') + b'\0'
    return bytes(out)


def steam_running():
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq steam.exe', '/NH'],
                       capture_output=True, text=True)
    return 'steam.exe' in r.stdout.lower()


def add(path):
    raw = open(path, 'rb').read() if os.path.exists(path) else b'\0shortcuts\0\x08\x08'
    d, _ = load(raw)
    if dump(d) + b'\x08' != raw:
        raise SystemExit('shortcuts.vdf did not round-trip; not touching it')
    sc = d['shortcuts']
    for v in sc.values():
        if v.get('AppName') == NAME:
            print(f'already present (appid {v["appid"]}); updating its target')
            entry = v
            break
    else:
        entry = {}
        sc[str(max([int(k) for k in sc] + [-1]) + 1)] = entry
    entry.update({
        'appid': zlib.crc32((EXE + NAME).encode()) | 0x80000000,
        'AppName': NAME, 'Exe': EXE, 'StartDir': ROOT + os.sep,'icon': ICON,
        'ShortcutPath': '', 'LaunchOptions': OPTS, 'IsHidden': 0,
        'AllowDesktopConfig': 1, 'AllowOverlay': 1, 'OpenVR': 0, 'Devkit': 0,
        'DevkitGameID': '', 'DevkitOverrideAppID': 0,
        'LastPlayTime': entry.get('LastPlayTime', 0), 'FlatpakAppID': '', 'sortas': '',
        'tags': entry.get('tags', {}),
    })
    if os.path.exists(path):
        shutil.copy2(path, f'{path}.bak-{time.strftime("%Y%m%d-%H%M%S")}')
    with open(path, 'wb') as f:
        f.write(dump(d) + b'\x08')
    print(f'added "{NAME}" (appid {entry["appid"]}) to {path}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--restart', action='store_true', help='close Steam, edit, start Steam')
    args = ap.parse_args()
    users = glob.glob(os.path.join(STEAM, 'userdata', '*', 'config'))
    if not users:
        raise SystemExit('no Steam userdata found')
    if steam_running():
        if not args.restart:
            raise SystemExit('Steam is running -- close it first, or pass --restart')
        print('shutting Steam down...')
        subprocess.run([os.path.join(STEAM, 'steam.exe'), '-shutdown'])
        for _ in range(60):
            if not steam_running():
                break
            time.sleep(1)
        else:
            raise SystemExit('Steam did not exit within 60 s; nothing changed')
        time.sleep(2)
    for cfg in users:
        add(os.path.join(cfg, 'shortcuts.vdf'))
    if args.restart:
        subprocess.Popen([os.path.join(STEAM, 'steam.exe')])
        print('Steam restarting')


if __name__ == '__main__':
    main()
