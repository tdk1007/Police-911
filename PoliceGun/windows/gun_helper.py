#!/usr/bin/env python3
"""
PoliceGun v1.0 — Windows helper (Spike 1)

Listens for UDP packets from the iPhone gun app and injects RELATIVE mouse
motion + left-click into Windows via SendInput. Relative is deliberate: the
PS2 port of Police 911 under PCSX2 reads a relative HID mouse (it does NOT
support absolute/GunCon input), which is the exact path already proven to
move the crosshair and fire.

Packet format (JSON, one per UDP datagram, ~100 Hz):
    {"dx": <float>, "dy": <float>, "fire": <0|1>}
  dx/dy are mouse counts to move since the last packet (may be fractional;
  we carry the remainder so slow aim isn't quantized away).
  fire is the current trigger state; we emit down/up on transitions.

Run:  py -3 gun_helper.py            (listens on 0.0.0.0:52777)
      py -3 gun_helper.py --port 52777 --host 0.0.0.0
Stop: Ctrl-C
"""

import argparse
import ctypes
import json
import socket
import sys
from ctypes import wintypes

# --- Win32 SendInput plumbing -------------------------------------------------

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

ULONG_PTR = ctypes.POINTER(wintypes.ULONG)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


_send_input = ctypes.windll.user32.SendInput


def _emit(dx=0, dy=0, flags=MOUSEEVENTF_MOVE):
    mi = MOUSEINPUT(dx, dy, 0, flags, 0, None)
    inp = INPUT(INPUT_MOUSE, _INPUTunion(mi=mi))
    _send_input(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def move_relative(dx, dy):
    if dx or dy:
        _emit(dx=int(dx), dy=int(dy), flags=MOUSEEVENTF_MOVE)


def set_fire(down):
    _emit(flags=MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP)


# --- Main loop ----------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=52777)
    ap.add_argument("--quiet", action="store_true", help="suppress per-packet stats")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("This helper injects input via the Win32 API and only runs on Windows.")
        print("(You can still lint/read it on the Mac.)")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    print(f"PoliceGun helper listening on {args.host}:{args.port}")
    print("Point the phone, watch this cursor. Ctrl-C to stop.\n")

    # Carry fractional deltas so sub-pixel aim accumulates instead of vanishing.
    rem_x = 0.0
    rem_y = 0.0
    firing = False
    packets = 0

    try:
        while True:
            data, _addr = sock.recvfrom(512)
            try:
                pkt = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                continue

            rem_x += float(pkt.get("dx", 0.0))
            rem_y += float(pkt.get("dy", 0.0))
            step_x = int(rem_x)
            step_y = int(rem_y)
            rem_x -= step_x
            rem_y -= step_y
            move_relative(step_x, step_y)

            want_fire = bool(pkt.get("fire", 0))
            if want_fire != firing:
                set_fire(want_fire)
                firing = want_fire

            packets += 1
            if not args.quiet and packets % 100 == 0:
                print(f"  {packets} packets  last dx={pkt.get('dx'):+.2f} "
                      f"dy={pkt.get('dy'):+.2f} fire={int(want_fire)}", end="\r")
    except KeyboardInterrupt:
        if firing:
            set_fire(False)
        print("\nStopped.")


if __name__ == "__main__":
    main()
