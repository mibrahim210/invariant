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
            await asyncio.wait_for(s.initialize(), 60)
            print([t.name for t in (await asyncio.wait_for(s.list_tools(), 30)).tools])
            try:
                res = await asyncio.wait_for(s.call_tool("hello", {}), 45)
            except asyncio.TimeoutError:
                sys.exit("check_mcp: hello did not return within 45 s (server hang)")
            if res.isError:
                sys.exit(f"check_mcp: hello returned an error: {res.content}")
            print(res.content[0].text)
asyncio.run(main())