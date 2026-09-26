"""Zero-coin check: start the server exactly as Bob would (from an installed mcp.json), list tools, call hello.

    uv run --locked --directory <invariant>/mcp-server python scripts/check_mcp.py <ABSOLUTE path to target/.bob/mcp.json>

--directory changes the working directory, so the mcp.json path must be absolute.
"""
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pathlib import Path
cfg_path = Path(sys.argv[1])
if not cfg_path.is_absolute():
    sys.exit(f"check_mcp: pass an absolute path to mcp.json, got {cfg_path}")
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))["mcpServers"]["invariant"]
async def main():
    async with stdio_client(StdioServerParameters(command=cfg["command"], args=cfg["args"])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("hello", {})
            print(res.content[0].text[:200])
asyncio.run(main())
