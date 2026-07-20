#!/usr/bin/env python3
"""
Example sender for the bridge's UDP mode (iPhone ARKit fallback path).

The bridge (police247_bridge.py --source udp) listens on UDP port 47911 for
one JSON object per datagram, either:

    {"duck": true}        explicit duck state — send this if your phone-side
    {"duck": false}       code already decides "ducked or not"

    {"head_y": 0.42}      normalized head height: 0.0 = top of the camera/AR
                          frame, 1.0 = bottom. The bridge applies the same
                          duck-line threshold + hysteresis as webcam mode.

Failsafe: if no datagram arrives for 0.5 s the bridge releases the duck key.
Send at 15-60 Hz.

Adapting your existing ARKit-over-UDP pipeline
----------------------------------------------
From an ARKit body anchor, the head joint's world-space height works best:
compute head_y = 1.0 - clamp((headWorldY - floorY) / standingHeadHeight, 0, 1)
and send it; or just threshold on the phone and send {"duck": ...}.
If you stream via ZIG SIM / TDLidar / LOTA instead, run a tiny relay on the PC
that parses their OSC schema and re-emits the JSON above to 127.0.0.1:47911.

This script itself is a keyboard-driven simulator for testing the pipe from
any machine on your LAN: hold D to duck, release to stand.
"""
import json
import socket
import sys
import time

TARGET = (sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1", 47911)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

try:
    import msvcrt  # Windows console: poll the D key
except ImportError:
    msvcrt = None

print(f"Sending to {TARGET[0]}:{TARGET[1]} — hold D to duck, Q to quit")
ducked = False
last_key_time = 0.0
while True:
    if msvcrt:
        while msvcrt.kbhit():
            ch = msvcrt.getch().lower()
            if ch == b"q":
                sys.exit(0)
            if ch == b"d":
                last_key_time = time.monotonic()
        # key auto-repeat keeps last_key_time fresh while D is held
        ducked = (time.monotonic() - last_key_time) < 0.15
    sock.sendto(json.dumps({"duck": ducked}).encode(), TARGET)
    time.sleep(0.03)  # ~33 Hz
