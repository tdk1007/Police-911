"""Validate the PINE client's wire format without PCSX2.

Stands up a fake PINE server backed by a bytearray, implementing the framing
exactly as pcsx2/PINE.cpp does, and drives the real client against it. Catches
endianness, length-field and batching mistakes on the desk instead of during a
live memory hunt, where a silent encoding bug would look like "the address
isn't there".

    py pine_selftest.py
"""
import os
import socket
import struct
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pine as P

RAM_BASE = 0x00100000
RAM_SIZE = 0x00200000


class FakePine(threading.Thread):
    """Minimal PINE server. Same framing, a bytearray for memory."""

    daemon = True

    def __init__(self):
        super().__init__()
        self.ram = bytearray(RAM_SIZE)
        self.saved_slots = []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]

    def _mem(self, addr, n):
        off = addr - RAM_BASE
        if off < 0 or off + n > RAM_SIZE:
            raise IndexError(addr)
        return off

    def handle(self, body):
        out = bytearray()
        i = 0
        while i < len(body):
            op = body[i]
            i += 1
            if op in (P.MSG_READ8, P.MSG_READ16, P.MSG_READ32, P.MSG_READ64):
                size = {P.MSG_READ8: 1, P.MSG_READ16: 2,
                        P.MSG_READ32: 4, P.MSG_READ64: 8}[op]
                addr = struct.unpack_from('<I', body, i)[0]
                i += 4
                off = self._mem(addr, size)
                out += self.ram[off:off + size]
            elif op in (P.MSG_WRITE8, P.MSG_WRITE16, P.MSG_WRITE32, P.MSG_WRITE64):
                size = {P.MSG_WRITE8: 1, P.MSG_WRITE16: 2,
                        P.MSG_WRITE32: 4, P.MSG_WRITE64: 8}[op]
                addr = struct.unpack_from('<I', body, i)[0]
                i += 4
                off = self._mem(addr, size)
                self.ram[off:off + size] = body[i:i + size]
                i += size
            elif op == P.MSG_STATUS:
                out += struct.pack('<I', P.STATUS_RUNNING)
            elif op in (P.MSG_VERSION, P.MSG_TITLE, P.MSG_ID,
                        P.MSG_UUID, P.MSG_GAMEVERSION):
                s = {P.MSG_VERSION: b'PCSX2 fake-1.2.3',
                     P.MSG_TITLE: b'Police 24-7',
                     P.MSG_ID: b'SLES-50285',
                     P.MSG_UUID: b'deadbeef',
                     P.MSG_GAMEVERSION: b'1.00'}[op] + b'\0'
                out += struct.pack('<I', len(s)) + s
            elif op in (P.MSG_SAVESTATE, P.MSG_LOADSTATE):
                self.saved_slots.append((op, body[i]))
                i += 1
            else:
                raise ValueError(f'bad opcode {op}')
        return bytes(out)

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                while True:
                    head = conn.recv(4)
                    if len(head) < 4:
                        break
                    total = struct.unpack('<I', head)[0]
                    body = b''
                    while len(body) < total - 4:
                        c = conn.recv(total - 4 - len(body))
                        if not c:
                            break
                        body += c
                    try:
                        payload = self.handle(body)
                        reply = struct.pack('<I', 5 + len(payload)) + \
                            bytes([P.IPC_OK]) + payload
                    except Exception:
                        reply = struct.pack('<I', 5) + bytes([P.IPC_FAIL])
                    conn.sendall(reply)


def main():
    srv = FakePine()
    srv.start()
    checks = 0
    failures = []

    def check(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f'{label}: got {got!r}, want {want!r}')

    with P.Pine(port=srv.port, timeout=5.0) as p:
        check('status', p.status(), P.STATUS_RUNNING)
        check('version', p.version(), 'PCSX2 fake-1.2.3')
        check('game_id', p.game_id(), 'SLES-50285')

        # width-by-width round trips, including the sign-free high bit
        for size, value in ((1, 0xA5), (2, 0xBEEF), (4, 0xDEADBEEF),
                            (8, 0xFEEDFACECAFEBABE)):
            addr = RAM_BASE + 0x100 + size * 16
            p.write(addr, value, size)
            check(f'rw{size * 8}', p.read(addr, size), value)

        # little-endian byte order, checked against the server's own bytes
        p.write32(RAM_BASE + 0x200, 0x11223344)
        check('endianness', bytes(srv.ram[0x200:0x204]),
              bytes((0x44, 0x33, 0x22, 0x11)))

        # floats, which is how a tracker coordinate most likely lands
        p.write_f32(RAM_BASE + 0x300, -0.625)
        check('f32', p.read_f32(RAM_BASE + 0x300), -0.625)

        # batching: replies must come back in command order, not sorted
        addrs = [RAM_BASE + 0x400 + 4 * k for k in range(64)]
        p.write_many([(a, 1000 + i) for i, a in enumerate(addrs)], size=4)
        check('read_many order', p.read_many(addrs, size=4),
              [1000 + i for i in range(64)])
        check('read_many reversed', p.read_many(addrs[::-1], size=4),
              [1000 + i for i in range(64)][::-1])

        # batches big enough to be SPLIT across packets. write_many packs 9 B
        # per command (cap 72221/packet) and read_many 4 B of reply (cap
        # 112498), so 150000 forces 3 request packets and 2 reply packets --
        # the case where an off-by-one in the chunking would corrupt order.
        n = 150000
        big = [RAM_BASE + 0x1000 + 4 * k for k in range(n)]
        p.write_many([(a, k & 0xFFFF) for k, a in enumerate(big)], size=4)
        got = p.read_many(big, size=4)
        check('chunked batch len', len(got), n)
        check('chunked batch content', got, [k & 0xFFFF for k in range(n)])

        # contiguous block read, 1 MB, which spans 3 read_block packets
        # (56249 x 8 B = ~450 KB each)
        blk = p.read_block(RAM_BASE + 0x100000, 0x100000)
        check('read_block', blk, bytes(srv.ram[0x100000:0x200000]))

        # savestate is fire-and-forget, but must still be framed correctly
        p.save_state(3)
        p.load_state(3)
        check('savestate', srv.saved_slots,
              [(P.MSG_SAVESTATE, 3), (P.MSG_LOADSTATE, 3)])

        # a FAIL reply must raise, not return garbage
        try:
            p.read32(0x7FFFFFFF)
            failures.append('out-of-range read: expected PineError, got a value')
            checks += 1
        except P.PineError:
            checks += 1

    for f in failures:
        print(f'  FAIL  {f}')
    print(f'pine_selftest: {checks - len(failures)}/{checks} checks passed')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
