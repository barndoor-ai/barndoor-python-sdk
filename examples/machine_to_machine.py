"""Authenticate with client credentials rather than an API key.

The token is obtained on the first request and refreshed before it expires —
there is nothing to schedule or cache yourself.

Run: BARNDOOR_CLIENT_ID=… BARNDOOR_CLIENT_SECRET=… python machine_to_machine.py
"""

import asyncio
import os

from barndoor import ClientCredentialsOptions, create_client


async def main() -> None:
    client_id = os.environ.get("BARNDOOR_CLIENT_ID")
    client_secret = os.environ.get("BARNDOOR_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("Set BARNDOOR_CLIENT_ID and BARNDOOR_CLIENT_SECRET")

    auth = ClientCredentialsOptions(client_id=client_id, client_secret=client_secret)
    async with create_client(auth=auth) as client:
        page = await client.registry.list_mcp_servers(limit=5)
        print([s.name for s in page.data])


asyncio.run(main())
