"""Lets other tools talk PINE while the immersive bridge is running.

PCSX2's PINE serves one client at a time (PINE.cpp: accept, then serve that socket until
it disconnects), and the bridge holds that connection for the whole session. Anything
else that connects to 28011 is accepted by the OS and then never answered. So the bridge
listens on RELAY_PORT too and passes each request through its own connection, between
its frames: one PINE client, one request in flight, no locking, and the bridge never
waits on a relay client.

    py live_knobs.py --status --port 28012     (Earpiece F-001 spike) while the bridge runs

Requests are passed through unchanged, so a relayed savestate load or code write behaves
as if sent to PCSX2 directly. The bridge notices a load by itself (Patches re-checks the
patches once a second) and reinstalls them, which also resets the VR slots to stock.
"""
import socket
import struct

RELAY_PORT = 28012
MAX_REQUEST = 650000        # PINE.cpp MAX_IPC_SIZE; a bigger length is garbage
PER_POLL = 8                # requests per bridge frame, so a chatty client can't stall it


class PineRelay:
    def __init__(self, pine, port=RELAY_PORT, host='127.0.0.1'):
        self.pine = pine
        self.srv = socket.socket()
        self.srv.bind((host, port))
        self.srv.listen(1)
        self.srv.setblocking(False)
        self.port = self.srv.getsockname()[1]
        self.client = None
        self.buf = bytearray()

    def close(self):
        self._drop()
        self.srv.close()

    def _drop(self):
        if self.client is not None:
            self.client.close()
        self.client, self.buf = None, bytearray()

    def poll(self):
        """Call once per bridge frame. Never blocks. Returns how many requests it served."""
        if self.client is None:
            try:
                self.client, _ = self.srv.accept()
            except (BlockingIOError, InterruptedError):
                return 0
            self.client.setblocking(False)
            self.client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            while True:
                chunk = self.client.recv(65536)
                if not chunk:                       # the client hung up
                    self._drop()
                    return 0
                self.buf += chunk
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            self._drop()
            return 0
        served = 0
        while served < PER_POLL and len(self.buf) >= 4:
            total = struct.unpack_from('<I', self.buf)[0]
            if total < 5 or total > MAX_REQUEST:
                self._drop()
                return served
            if len(self.buf) < total:
                break
            body = bytes(self.buf[4:total])
            del self.buf[:total]
            # A PINE error here belongs to the bridge's connection: let it propagate the same
            # way a failed read32 in the bridge would.
            reply = self.pine.relay(body)
            try:
                self.client.settimeout(0.05)        # replies are small; don't hang on a stuck reader
                self.client.sendall(reply)
                self.client.setblocking(False)
            except OSError:
                self._drop()
                return served
            served += 1
        return served
