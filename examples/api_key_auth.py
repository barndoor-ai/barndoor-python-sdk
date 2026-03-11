"""Example: API key authentication (simplest path).

This is the fastest way to get started with the Barndoor SDK.  No OAuth,
no browser pop-ups, no OIDC configuration — just an API key.

Setup:
    1. Generate an API key in the Barndoor dashboard.
       (Keys start with ``bdai_``.)
    2. Export it:
           export BARNDOOR_API_KEY="bdai_your_key_here"

    Alternatively, pass it directly to the SDK constructor.

Usage:
    python examples/api_key_auth.py
"""

from __future__ import annotations

import asyncio
import os

from barndoor.sdk import BarndoorSDK


async def main() -> None:
    # Option A — read from environment (recommended)
    # Just set BARNDOOR_API_KEY and the SDK picks it up automatically.
    #
    # Option B — pass explicitly:
    #   sdk = BarndoorSDK(base_url, api_key="bdai_your_key_here")

    base_url = os.getenv("BARNDOOR_URL", "https://your-org.platform.barndoor.ai")

    async with BarndoorSDK(base_url) as sdk:
        # List available MCP servers
        servers = await sdk.list_servers()
        print(f"\n✅ Connected — found {len(servers)} server(s):\n")
        for s in servers:
            print(f"  • {s.slug:<20} status={s.connection_status}")


if __name__ == "__main__":
    asyncio.run(main())
