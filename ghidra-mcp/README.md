# GhidraMCP: Ghidra as MCP tools for agents

[LaurieWired/GhidraMCP](https://github.com/LaurieWired/GhidraMCP) (v2.0.0, built for
Ghidra 12.1.4) exposes Ghidra to MCP clients: decompile, disassemble, xrefs, call graphs,
strings, memory reads, and **writes** (rename functions/data/variables, set prototypes and
local types, decompiler/disassembly comments). REA can't open our targets (PowerPC, MIPS
R5900), so this is the interactive static-RE path.

## Servers (`.mcp.json` at the repo root)

| MCP server      | Port | Program                                           | Ghidra project                     |
|-----------------|------|---------------------------------------------------|------------------------------------|
| `ghidra-ps2`    | 8092 | `extracted/SLES_502.85` (PS2 EE, `r5900:LE:32`)   | `extracted/ps2_ghidra_proj/police247` |
| `ghidra-arcade` | 8091 | `extracted/arcade/p911ud_ram_sensorbad.bin` (PPC) | `extracted/arcade/ghidra_proj/arcade` |
| `ghidra-gui`    | 8080 | whatever is open in a running Ghidra CodeBrowser  | (GUI)                              |

The PS2 program is analyzed with `ghidra-emotionengine-reloaded`, so R5900 MMI and
128-bit `lq`/`sq` decode (the Capstone blocker in `camera-tracking/re/RE_FINDINGS.md`).

The two headless servers are **shared** HTTP processes: every Claude session talks to the
same Ghidra program, so renames and comments made by one agent are visible to all.

## Run

```bat
ghidra-mcp\start.cmd            &:: idempotent; both targets (or: start.cmd ps2)
ghidra-mcp\stop.cmd             &:: clean stop, saves the project (or: stop.cmd arcade)
```

Start the servers before starting a Claude session (a session started earlier won't have the tools until it is restarted; use `call.py` below meanwhile).
Each is a hidden ~1 GB JVM; stop them when you're playing so PCSX2 has the machine.
Logs: `ghidra-mcp\run\<name>.log`.

Without the MCP tools loaded (e.g. a session started before the servers), call from Bash:

```bash
tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py ps2 --list
tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py ps2 decompile_function_by_address address=00228660
tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py arcade list_strings filter=SENSOR
```

## Saving and locking

- Upstream only saves on a clean shutdown. `serve.py` adds an autosave every 2 min (when
  changed) and a stop file that `stop.cmd` uses. **Don't kill the python processes**:
  you'd lose up to 2 min of edits and leave a stale `*.lock` in the project directory.
- A Ghidra project can only be open once. Before opening `arcade` or `police247` in the Ghidra
  GUI, run `stop.cmd <target>`. The GUI can use the `ghidra-gui` server instead (the plugin
  is enabled in the CodeBrowser tool; port under Edit → Tool Options → GhidraMCP HTTP Server).

## Setup (already done on the Windows rig, 2026-10-20)

1. `git clone https://github.com/LaurieWired/GhidraMCP tools/src/GhidraMCP`
2. `cd tools/src/GhidraMCP/extension; $env:GHIDRA_INSTALL_DIR=<repo>\tools\ghidra_12.1.4_PUBLIC; & "$env:GHIDRA_INSTALL_DIR\support\gradle\gradlew.bat" buildExtension`
3. Unzip `extension/dist/*.zip` into `%APPDATA%\ghidra\ghidra_12.1.4_PUBLIC\Extensions\`
   (next to `ghidra-emotionengine-reloaded`). GUI plugin enabled by adding
   `com.lauriewired.GhidraMCPPlugin` under the `Developer` package in
   `%APPDATA%\ghidra\ghidra_12.1.4_PUBLIC\tools\_code_browser.tcd` (backup `.pre-ghidramcp`).
4. `py -3.14 -m venv tools/ghidramcp-venv; tools/ghidramcp-venv/Scripts/python -m pip install "./tools/src/GhidraMCP[headless]"`

## Adding a target

Add an entry to `targets.ps1` (port, binary, project, `--language` if the loader can't
infer it, `--no-analyze` for an already-analyzed project) and a matching `http` entry in
`.mcp.json`.
