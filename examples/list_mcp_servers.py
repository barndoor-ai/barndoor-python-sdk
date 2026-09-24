"""List the MCP servers registered in your organization.

Run: BARNDOOR_API_KEY=bdai_… python list_mcp_servers.py
"""

import asyncio
import os

from barndoor import create_client


async def main() -> None:
    key = os.environ.get("BARNDOOR_API_KEY")
    if not key:
        raise SystemExit("Set BARNDOOR_API_KEY")

    async with create_client(auth=key) as client:
        page = await client.registry.list_mcp_servers(limit=10)
        for server in page.data:
            print(f"{server.name}  ({server.slug})")
        print(f"\n{len(page.data)} of {page.pagination.total} server(s)")


asyncio.run(main())
