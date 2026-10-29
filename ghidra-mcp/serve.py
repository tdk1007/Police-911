"""Long-lived headless GhidraMCP server with clean stop and autosave.

Wraps `ghidra-mcp --headless` (LaurieWired/GhidraMCP) so a shared server can be
stopped without losing work: upstream only saves the program when the process
shuts down cleanly, and a background process on Windows can't be sent Ctrl+C.

Adds, on Ghidra's main thread (the only thread its project API tolerates):
  * stop file   run/<name>.stop  -> clean shutdown (program saved)
  * autosave    every AUTOSAVE_S seconds while the program has unsaved changes
  * pid file    run/<name>.pid

Usage (normally via start.ps1):
  serve.py <name> <ghidra-mcp args...>
"""
import logging
import os
import sys
import time
from pathlib import Path

from ghidra_mcp import cli, headless

RUN = Path(__file__).resolve().parent / "run"
AUTOSAVE_S = 120

log = logging.getLogger("ghidra-mcp-serve")


def main() -> None:
    name, argv = sys.argv[1], sys.argv[2:]
    RUN.mkdir(exist_ok=True)
    stop_file = RUN / f"{name}.stop"
    pid_file = RUN / f"{name}.pid"
    stop_file.unlink(missing_ok=True)
    pid_file.write_text(str(os.getpid()))

    base = headless.HeadlessSession

    class Session(base):
        def run(self) -> None:
            try:
                self.load()
            except Exception as e:
                if not self._closing.is_set():
                    log.exception("Headless startup failed")
                    self.backend.set_failed(f"{e.__class__.__name__}: {e}")
            # Save right after a fresh import/analysis so a crash can't cost the analysis.
            self._autosave()
            last = time.monotonic()
            while not self._closing.wait(0.5):
                if stop_file.exists():
                    log.info("Stop file found; shutting down cleanly")
                    self.request_stop()
                    break
                if time.monotonic() - last >= AUTOSAVE_S:
                    self._autosave()
                    last = time.monotonic()

        def _autosave(self) -> None:
            p = self._program
            if p is None or not p.isChanged() or p.getCurrentTransactionInfo() is not None:
                return
            try:
                p.save("ghidra-mcp autosave", self._task_monitor())
                log.info("Autosaved %s", p.getName())
            except Exception:
                log.exception("Autosave failed")

        def close(self) -> None:
            try:
                super().close()
            finally:
                stop_file.unlink(missing_ok=True)
                pid_file.unlink(missing_ok=True)

    headless.HeadlessSession = Session
    cli.main(argv)


if __name__ == "__main__":
    main()
