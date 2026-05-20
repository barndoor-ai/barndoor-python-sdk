"""Minimal machine-to-machine example using OAuth client credentials.

Demonstrates the headless flow: fetch a JWT via OAuth client credentials,
list MCP servers, and tear down cleanly. Suitable for backend services,
scheduled jobs, or CI pipelines where no user is present to complete the
interactive PKCE flow.

Environment variables:

    BARNDOOR_API_BASE_URL   e.g. https://api.barndoor.host
    BARNDOOR_AUTH_ISSUER    e.g. https://auth.barndoor.ai/realms/barndoor
    BARNDOOR_M2M_CLIENT_ID
    BARNDOOR_M2M_CLIENT_SECRET
    BARNDOOR_API_AUDIENCE   defaults to "https://barndoor.ai/"
"""

from __future__ import annotations

import asyncio
import os

from barndoor.sdk import BarndoorSDK


async def main() -> None:
    base_url = os.environ["BARNDOOR_API_BASE_URL"]
    issuer = os.environ["BARNDOOR_AUTH_ISSUER"]
    client_id = os.environ["BARNDOOR_M2M_CLIENT_ID"]
    client_secret = os.environ["BARNDOOR_M2M_CLIENT_SECRET"]
    audience = os.environ.get("BARNDOOR_API_AUDIENCE", "https://barndoor.ai/")

    async with await BarndoorSDK.from_client_credentials(
        base_url,
        client_id=client_id,
        client_secret=client_secret,
        audience=audience,
        issuer=issuer,
    ) as sdk:
        servers = await sdk.list_servers()
        for s in servers:
            print(f"{s.slug:30s} {s.connection_status}")


if __name__ == "__main__":
    asyncio.run(main())
