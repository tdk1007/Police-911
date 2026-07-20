#!/usr/bin/env python3
"""
PoliceGun — synthetic sender (no phone needed)

Pretends to be the phone: streams UDP packets that trace a slow circle and pull
the trigger once a second. Point it at gun_helper.py on the Windows PC and you
should see the Windows cursor sweep in a circle and periodically click — proving
the network→helper→SendInput half works BEFORE the iPhone app exists.

Run from Mac or Windows:
    python3 tools/send_test.py --host <WINDOWS_PC_IP>          (default port 52777)
    python3 tools/send_test.py --host 192.168.0.50 --rate 100

Point it at udp_monitor.py instead to just watch the fake packets arrive.
Stop: Ctrl-C
"""

import argparse
import json
import math
import socket
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="target IP (Windows PC or monitor)")
    ap.add_argument("--port", type=int, default=52777)
    ap.add_argument("--rate", type=int, default=100, help="packets per second")
    ap.add_argument("--radius", type=float, default=4.0, help="counts per packet (motion size)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dt = 1.0 / args.rate
    print(f"Sending synthetic gun packets to {args.host}:{args.port} at {args.rate}/s")
    print("Expect: cursor sweeps a circle, clicks once per second. Ctrl-C to stop.\n")

    t = 0.0
    sent = 0
    try:
        while True:
            # Derivative of a circle → per-frame deltas that trace it out.
            dx = -math.sin(t) * args.radius
            dy = math.cos(t) * args.radius
            fire = 1 if (int(t) % 2 == 0 and (t - int(t)) < 0.15) else 0
            msg = json.dumps({"dx": round(dx, 3), "dy": round(dy, 3), "fire": fire})
            sock.sendto(msg.encode(), (args.host, args.port))
            sent += 1
            if sent % args.rate == 0:
                print(f"  sent {sent} packets", end="\r", flush=True)
            t += dt * 2.0  # ~2 rad/s → a lap every ~3s
            time.sleep(dt)
    except KeyboardInterrupt:
        print(f"\nStopped. {sent} packets sent.")


if __name__ == "__main__":
    main()
