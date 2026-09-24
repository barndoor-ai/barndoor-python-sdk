"""Connect to Barndoor's MCP endpoint and list the tools it exposes.

Every call is authenticated with the same credentials as the REST client and
recorded in your organization's audit trail.

Run: BARNDOOR_API_KEY=bdai_… BARNDOOR_ORG=acme python mcp_client.py
"""

import asyncio
import os

from barndoor import create_client, mcp_client


async def main() -> None:
    key = os.environ.get("BARNDOOR_API_KEY")
    org = os.environ.get("BARNDOOR_ORG")
    if not key or not org:
        raise SystemExit("Set BARNDOOR_API_KEY and BARNDOOR_ORG")

    async with create_client(auth=key) as client:
        async with mcp_client(client, org) as session:
            result = await session.list_tools()
            for tool in result.tools:
                print(f"{tool.name} — {tool.description or 'no description'}")


asyncio.run(main())
