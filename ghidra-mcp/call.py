"""Call a GhidraMCP tool from the shell (for sessions without the MCP tools loaded).

  tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py ps2 --list
  tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py ps2 decompile_function_by_address address=00228660
  tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py arcade list_strings filter=SENSOR limit=20
  tools/ghidramcp-venv/Scripts/python.exe ghidra-mcp/call.py ps2 set_decompiler_comment '{"address":"00228660","comment":"..."}'

Arguments are key=value pairs (typed from the tool's schema) or one JSON object.
Run with tools/ghidramcp-venv/Scripts/python.exe (needs the `mcp` package).
"""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORTS = {"arcade": 8091, "ps2": 8092}


def parse(args, schema):
    if len(args) == 1 and args[0].lstrip().startswith("{"):
        return json.loads(args[0])
    props = (schema or {}).get("properties", {})
    out = {}
    for a in args:
        k, _, v = a.partition("=")
        types = {props.get(k, {}).get("type")} | {x.get("type") for x in props.get(k, {}).get("anyOf", [])}
        out[k] = int(v, 0) if "integer" in types else (v.lower() == "true" if "boolean" in types else v)
    return out


async def main(argv):
    target, rest = argv[0], argv[1:]
    url = f"http://127.0.0.1:{PORTS.get(target, target)}/mcp" if target in PORTS or target.isdigit() else target
    async with streamablehttp_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            if not rest or rest[0] == "--list":
                for t in tools.values():
                    props = ", ".join((t.inputSchema or {}).get("properties", {}))
                    print(f"{t.name}({props})")
                return
            if rest[0] not in tools:
                return f"unknown tool {rest[0]!r}; use --list"
            res = await s.call_tool(rest[0], parse(rest[1:], tools[rest[0]].inputSchema))
            for c in res.content:
                print(getattr(c, "text", c))
            return 1 if res.isError else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
