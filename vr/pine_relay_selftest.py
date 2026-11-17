"""Check pine_relay.py against the single-client fake PINE server, no PCSX2 needed.

    py pine_relay_selftest.py
"""
import os
import socket
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, '..', 'camera-tracking', 're', 'ram')]
import pine as P
from pine_relay import PineRelay
from pine_selftest import FakePine, RAM_BASE


def packet(*cmds):
    body = b''.join(cmds)
    return struct.pack('<I', len(body) + 4) + body


def recv_reply(c):
    head = c.recv(4)
    total = struct.unpack('<I', head)[0]
    rest = b''
    while len(rest) < total - 4:
        rest += c.recv(total - 4 - len(rest))
    return rest


def pump(relay, c, n=50):
    """Run bridge frames until the client has a reply waiting."""
    for _ in range(n):
        relay.poll()
        c.settimeout(0.02)
        try:
            if c.recv(1, socket.MSG_PEEK):
                c.settimeout(2.0)
                return
        except (socket.timeout, BlockingIOError):
            pass
    raise AssertionError('no reply through the relay')


def main():
    srv = FakePine()
    srv.start()
    bridge = P.Pine(port=srv.port, timeout=2.0).connect()
    bridge.write32(RAM_BASE, 0x11111111)        # the bridge owns PINE from here on
    failures = []

    def check(label, ok):
        print(('ok    ' if ok else 'FAIL  ') + label)
        if not ok:
            failures.append(label)

    # The problem: a second direct client is accepted but never answered.
    direct = socket.create_connection(('127.0.0.1', srv.port), timeout=0.5)
    direct.sendall(packet(bytes([P.MSG_STATUS])))
    try:
        direct.recv(4)
        check('a second direct PINE client is starved', False)
    except socket.timeout:
        check('a second direct PINE client is starved', True)
    direct.close()

    relay = PineRelay(bridge, port=0)
    c = socket.create_connection(('127.0.0.1', relay.port), timeout=2.0)

    c.sendall(packet(bytes([P.MSG_WRITE32]) + struct.pack('<II', RAM_BASE + 8, 0xCAFEF00D),
                     bytes([P.MSG_READ32]) + struct.pack('<I', RAM_BASE)))
    pump(relay, c)
    rest = recv_reply(c)
    check('relayed batch: write lands, read sees the bridge\'s value',
          rest == bytes([P.IPC_OK]) + struct.pack('<I', 0x11111111)
          and struct.unpack_from('<I', srv.ram, 8)[0] == 0xCAFEF00D)
    check('the bridge still works on its own connection', bridge.read32(RAM_BASE + 8) == 0xCAFEF00D)

    pkt = packet(bytes([P.MSG_READ32]) + struct.pack('<I', RAM_BASE + 8))
    c.sendall(pkt[:3])
    check('half a packet is held, not answered', relay.poll() == 0)
    c.sendall(pkt[3:])
    pump(relay, c)
    check('the rest of it is answered', recv_reply(c) == bytes([P.IPC_OK]) + struct.pack('<I', 0xCAFEF00D))

    c.sendall(packet(bytes([P.MSG_READ32]) + struct.pack('<I', 0x10)))   # outside RAM
    pump(relay, c)
    check('a FAIL reply is passed through, not raised in the bridge', recv_reply(c) == bytes([P.IPC_FAIL]))

    c.sendall(packet(bytes([P.MSG_STATUS])) * 20)
    served = 0
    for _ in range(10):
        served += relay.poll()
        if served == 20:
            break
    check('a burst is spread over frames (8 per frame)', served == 20)
    for _ in range(20):
        recv_reply(c)

    c.close()
    relay.poll()
    c2 = socket.create_connection(('127.0.0.1', relay.port), timeout=2.0)
    c2.sendall(struct.pack('<I', 1))            # nonsense length
    for _ in range(5):
        relay.poll()
    c2.settimeout(1.0)
    check('a client that hangs up or sends garbage is dropped', c2.recv(4) == b'')
    c2.close()

    c3 = socket.create_connection(('127.0.0.1', relay.port), timeout=2.0)
    c3.sendall(packet(bytes([P.MSG_STATUS])))
    pump(relay, c3)
    check('the next client is served', recv_reply(c3) == bytes([P.IPC_OK]) + struct.pack('<I', 0))
    c3.close()
    relay.close()
    bridge.close()
    print(f'{len(failures)} failed' if failures else 'all relay checks passed')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
