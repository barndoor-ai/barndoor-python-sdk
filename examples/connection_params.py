"""Get MCP connection details without opening a connection, so another
framework — CrewAI, LangChain, your own client — can do the connecting.

Run: BARNDOOR_API_KEY=bdai_… BARNDOOR_ORG=acme python connection_params.py
"""

import asyncio
import os

from barndoor import create_client, mcp_connection_params


async def main() -> None:
    key = os.environ.get("BARNDOOR_API_KEY")
    org = os.environ.get("BARNDOOR_ORG")
    if not key or not org:
        raise SystemExit("Set BARNDOOR_API_KEY and BARNDOOR_ORG")

    async with create_client(auth=key) as client:
        url, headers = await mcp_connection_params(client, org)
        # `headers` carries a bearer token. Treat it as a secret.
        print("url:", url)
        print("headers:", ", ".join(sorted(headers)))


asyncio.run(main())
