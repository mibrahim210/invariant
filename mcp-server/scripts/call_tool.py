"""Zero-coin: start the server from an installed mcp.json and call one tool.

    uv run --locked --directory <invariant>/mcp-server python scripts/call_tool.py <ABSOLUTE mcp.json> <tool>
"""
import asyncio, json, sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

cfg_path, tool = Path(sys.argv[1]), sys.argv[2]
if not cfg_path.is_absolute():
    sys.exit("call_tool: pass an absolute path to mcp.json")
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))["mcpServers"]["invariant"]

async def main():
    async with stdio_client(StdioServerParameters(command=cfg["command"], args=cfg["args"])) as (r, w):
        async with ClientSession(r, w) as s:
            await asyncio.wait_for(s.initialize(), 60)
            res = await asyncio.wait_for(s.call_tool(tool, {}), 300)
            print("ERROR" if res.isError else "OK", len(res.content[0].text.encode()), "bytes")
            print(res.content[0].text)
asyncio.run(main())