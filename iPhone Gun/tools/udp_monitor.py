#!/usr/bin/env python3
"""
PoliceGun — UDP monitor (cross-platform, no game/injection)

Run this on ANY machine (Mac or Windows) to confirm the phone is actually
transmitting. It listens for the gun's UDP packets and prints them live, plus
the packet rate. It does NOT move the mouse — it's purely a "is data arriving?"
scope, so you can prove the phone→network half before touching Windows input.

On startup it prints this machine's LAN IP addresses — type one of those into
the phone app's "PC IP" field to aim the phone at THIS machine for the test.

Run:  python3 tools/udp_monitor.py            (listens on 0.0.0.0:52777)
      python3 tools/udp_monitor.py --port 52777
Stop: Ctrl-C
"""

import argparse
import json
import socket
import time


def local_ips():
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    # Fallback: the "route to 8.8.8.8" trick reveals the primary LAN IP.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=52777)
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))

    ips = local_ips()
    print("PoliceGun UDP monitor")
    print(f"  listening on {args.host}:{args.port}")
    if ips:
        print("  this machine's LAN IP(s) — put one in the phone app's 'PC IP':")
        for ip in ips:
            print(f"      {ip}")
    print("\nWaiting for packets... (Ctrl-C to stop)\n")

    count = 0
    window_start = time.monotonic()
    window_count = 0
    rate = 0.0
    first_from = None

    try:
        while True:
            data, addr = sock.recvfrom(512)
            count += 1
            window_count += 1
            if first_from != addr[0]:
                first_from = addr[0]
                print(f"\n[receiving from {addr[0]}]")

            now = time.monotonic()
            if now - window_start >= 1.0:
                rate = window_count / (now - window_start)
                window_start = now
                window_count = 0

            try:
                pkt = json.loads(data)
                line = (f"  #{count:<6} {rate:5.0f}/s   "
                        f"dx {float(pkt.get('dx',0)):+7.2f}   "
                        f"dy {float(pkt.get('dy',0)):+7.2f}   "
                        f"fire {int(pkt.get('fire',0))}")
            except (ValueError, UnicodeDecodeError):
                line = f"  #{count:<6} {rate:5.0f}/s   [non-JSON {len(data)}B: {data[:32]!r}]"
            print(line, end="\r", flush=True)
    except KeyboardInterrupt:
        print(f"\n\nStopped. {count} packets total.")


if __name__ == "__main__":
    main()
