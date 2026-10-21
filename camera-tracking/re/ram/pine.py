"""PINE client -- read and write the running game's EE memory from Python.

PINE is PCSX2's own IPC server ("Protocol for Instrumentation of Emulators").
Enable it in PCSX2 under Settings -> Advanced -> PINE, or set in PCSX2.ini:

    [EmuCore]
    EnablePINE = true
    PINESlot = 28011

Wire format, read off pcsx2/PINE.cpp (ClientLoop + ParseCommand) rather than the
wiki, because the wiki 403s:

    request : u32 LE total_length (INCLUDING these 4 bytes) then a stream of
              commands, each  opcode:u8  [args]
    reply   : u32 LE total_length (including itself and the code byte)
              u8 code  (0x00 = OK, 0xFF = FAIL)
              then the concatenated payloads, in command order

Several commands can ride in one packet and their replies come back
concatenated -- that is what makes bulk reads fast enough to be useful.
The emulator caps a request at 650000 bytes and a reply at 450000.

Addresses are EE addresses as the game sees them (e.g. 0x0026B790), which is
also the byte offset into a savestate's eeMemory.bin for anything under 32 MB.
"""
import socket
import struct

DEFAULT_SLOT = 28011

# pcsx2/PINE.cpp :: enum IPCCommand
MSG_READ8, MSG_READ16, MSG_READ32, MSG_READ64 = 0, 1, 2, 3
MSG_WRITE8, MSG_WRITE16, MSG_WRITE32, MSG_WRITE64 = 4, 5, 6, 7
MSG_VERSION, MSG_SAVESTATE, MSG_LOADSTATE = 8, 9, 0xA
MSG_TITLE, MSG_ID, MSG_UUID, MSG_GAMEVERSION, MSG_STATUS = 0xB, 0xC, 0xD, 0xE, 0xF

IPC_OK, IPC_FAIL = 0x00, 0xFF

MAX_REQUEST = 650000
MAX_REPLY = 450000

STATUS_RUNNING, STATUS_PAUSED, STATUS_SHUTDOWN = 0, 1, 2

_READ_OP = {1: MSG_READ8, 2: MSG_READ16, 4: MSG_READ32, 8: MSG_READ64}
_WRITE_OP = {1: MSG_WRITE8, 2: MSG_WRITE16, 4: MSG_WRITE32, 8: MSG_WRITE64}
_PACK = {1: '<B', 2: '<H', 4: '<I', 8: '<Q'}


class PineError(RuntimeError):
    pass


class Pine:
    """One connection to a PCSX2 PINE server.

    Usable as a context manager. Not thread-safe: one request is in flight at a
    time, because the protocol has no request IDs and replies are matched to
    commands purely by order.
    """

    def __init__(self, host='127.0.0.1', port=DEFAULT_SLOT, timeout=15.0):
        self.addr = (host, port)
        self.timeout = timeout
        self.sock = None

    # ---------------------------------------------------------------- plumbing
    def connect(self):
        if self.sock is not None:
            return self
        s = socket.create_connection(self.addr, timeout=self.timeout)
        s.settimeout(self.timeout)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = s
        return self

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    def _recv_exactly(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise PineError("PINE closed the connection mid-reply "
                                "(is a game actually running?)")
            buf += chunk
        return bytes(buf)

    def _txn(self, body):
        """Send one packet of commands, return the reply payload (code stripped)."""
        if self.sock is None:
            self.connect()
        packet = struct.pack('<I', len(body) + 4) + body
        if len(packet) > MAX_REQUEST:
            raise PineError(f"request {len(packet)} B exceeds PINE's {MAX_REQUEST} B cap")
        self.sock.sendall(packet)

        total = struct.unpack('<I', self._recv_exactly(4))[0]
        if total < 5:
            raise PineError(f"nonsense reply length {total}")
        rest = self._recv_exactly(total - 4)
        if rest[0] == IPC_FAIL:
            raise PineError("PINE returned FAIL -- usually means no VM is running, "
                            "a bad address, or a malformed command")
        if rest[0] != IPC_OK:
            raise PineError(f"unknown PINE result code 0x{rest[0]:02X}")
        return rest[1:]

    # ------------------------------------------------------------ single value
    def read(self, addr, size=4):
        op = _READ_OP[size]
        payload = self._txn(struct.pack('<BI', op, addr))
        return struct.unpack(_PACK[size], payload[:size])[0]

    def write(self, addr, value, size=4):
        op = _WRITE_OP[size]
        self._txn(struct.pack('<BI', op, addr) + struct.pack(_PACK[size], value))

    def read8(self, a):
        return self.read(a, 1)

    def read16(self, a):
        return self.read(a, 2)

    def read32(self, a):
        return self.read(a, 4)

    def read64(self, a):
        return self.read(a, 8)

    def write8(self, a, v):
        self.write(a, v, 1)

    def write16(self, a, v):
        self.write(a, v, 2)

    def write32(self, a, v):
        self.write(a, v, 4)

    def write64(self, a, v):
        self.write(a, v, 8)

    def read_f32(self, addr):
        return struct.unpack('<f', struct.pack('<I', self.read(addr, 4)))[0]

    def write_f32(self, addr, value):
        self.write(addr, struct.unpack('<I', struct.pack('<f', value))[0], 4)

    # -------------------------------------------------------------- bulk value
    def read_many(self, addrs, size=4):
        """Read a scattered list of addresses in as few round trips as possible."""
        op = _READ_OP[size]
        out = []
        # request is 5 B per command, reply is `size` B per command; respect both
        per_packet = min((MAX_REQUEST - 4) // 5, (MAX_REPLY - 5) // size)
        for i in range(0, len(addrs), per_packet):
            chunk = addrs[i:i + per_packet]
            body = b''.join(struct.pack('<BI', op, a) for a in chunk)
            payload = self._txn(body)
            fmt = '<' + _PACK[size][1] * len(chunk)
            out.extend(struct.unpack_from(fmt, payload))
        return out

    def write_many(self, pairs, size=4):
        """Write a list of (addr, value) in as few round trips as possible."""
        op = _WRITE_OP[size]
        per_packet = (MAX_REQUEST - 4) // (5 + size)
        for i in range(0, len(pairs), per_packet):
            body = b''.join(struct.pack('<BI', op, a) + struct.pack(_PACK[size], v)
                            for a, v in pairs[i:i + per_packet])
            self._txn(body)

    def read_block(self, addr, nbytes):
        """Read a contiguous span. addr and nbytes must be 8-byte aligned.

        Batched MsgRead64: ~256 KB per round trip. Fine for spot-checking a few
        megabytes live; for a full 32 MB sweep take a savestate instead, which is
        one atomic snapshot rather than a moving target.
        """
        if addr % 8 or nbytes % 8:
            raise ValueError("read_block needs 8-byte alignment")
        per_packet = min((MAX_REQUEST - 4) // 5, (MAX_REPLY - 5) // 8)
        out = bytearray()
        remaining = nbytes // 8
        cur = addr
        while remaining:
            n = min(remaining, per_packet)
            body = b''.join(struct.pack('<BI', MSG_READ64, cur + 8 * k) for k in range(n))
            out += self._txn(body)[:8 * n]
            cur += 8 * n
            remaining -= n
        return bytes(out)

    # ------------------------------------------------------------ emulator ctl
    def _string_cmd(self, op):
        payload = self._txn(struct.pack('<B', op))
        size = struct.unpack_from('<I', payload, 0)[0]
        return payload[4:4 + size].split(b'\0', 1)[0].decode('utf-8', 'replace')

    def version(self):
        return self._string_cmd(MSG_VERSION)

    def title(self):
        return self._string_cmd(MSG_TITLE)

    def game_id(self):
        return self._string_cmd(MSG_ID)

    def uuid(self):
        return self._string_cmd(MSG_UUID)

    def game_version(self):
        return self._string_cmd(MSG_GAMEVERSION)

    def status(self):
        payload = self._txn(struct.pack('<B', MSG_STATUS))
        return struct.unpack_from('<I', payload, 0)[0]

    def save_state(self, slot):
        """Async: PCSX2 queues this onto its CPU thread and replies immediately.

        The .p2s file is NOT on disk when this returns -- wait for the file's
        mtime to advance before reading it.
        """
        self._txn(struct.pack('<BB', MSG_SAVESTATE, slot))

    def load_state(self, slot):
        self._txn(struct.pack('<BB', MSG_LOADSTATE, slot))


def probe(host='127.0.0.1', port=DEFAULT_SLOT, timeout=3.0):
    """Is PINE up, and what is it running? Returns a dict, or raises PineError."""
    try:
        with Pine(host, port, timeout) as p:
            info = {"version": p.version(), "status": p.status()}
            if info["status"] != STATUS_SHUTDOWN:
                info.update(title=p.title(), game_id=p.game_id(),
                            uuid=p.uuid(), game_version=p.game_version())
            return info
    except (OSError, socket.timeout) as e:
        raise PineError(f"cannot reach PINE at {host}:{port} ({e}). "
                        "Is PCSX2 running with EnablePINE=true?") from e


if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SLOT
    try:
        for k, v in probe(port=port).items():
            print(f"{k:>13}: {v}")
    except PineError as e:
        print(f"PINE: {e}")
        raise SystemExit(1)
