"""Minimal Barndoor → MCP demo using the SDK quick-start helpers.

The only responsibilities left here are:

1. Load a local ``.env`` so we get *AGENT_CLIENT_ID / AGENT_CLIENT_SECRET*.
2. Call the SDK helpers to
   • login & obtain a ready ``BarndoorSDK``
   • make sure the chosen server is connected
   • prepare the MCP connection params (proxy URL + headers)
3. Feed those params to **any** AI framework.
"""

from __future__ import annotations

import asyncio

from pathlib import Path

# Framework-agnostic SDK helpers ---------------------------------------------
import barndoor.sdk as bd


# Optional: only imported when we actually run the CrewAI demo
from crewai import Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter
from dotenv import load_dotenv


SERVER_SLUG = "salesforce"  # change to the MCP server you want


async def main() -> None:
    # ---------------------------------------------------------------------
    # 0. Environment / login
    # ---------------------------------------------------------------------
    # loads AGENT_CLIENT_ID/SECRET
    load_dotenv(Path(__file__).with_name(".env"))

    sdk = await bd.login_interactive()  # handles cached JWT, PKCE flow, etc.

    # ---------------------------------------------------------------------
    # 1. List available servers for the current user
    # ---------------------------------------------------------------------
    servers = await sdk.list_servers()
    print("\nAvailable MCP servers:")
    for s in servers:
        print(f"  • {s.slug:<12} status={s.connection_status}")

    # ---------------------------------------------------------------------
    # 2. Make sure the target server is connected (will launch OAuth if not)
    # ---------------------------------------------------------------------
    await bd.ensure_server_connected(sdk, SERVER_SLUG)

    # ---------------------------------------------------------------------
    # 3. Build connection params (works locally & in deployed envs)
    # ---------------------------------------------------------------------
    params, public_url = await bd.make_mcp_connection_params(sdk, SERVER_SLUG)
    print(f"✓ Ready – MCP URL: {params['url']}  (public: {public_url})")

    # ---------------------------------------------------------------------
    # 4. Tiny CrewAI demo – replace with LangChain etc. if you prefer
    # ---------------------------------------------------------------------
    with MCPServerAdapter(params) as mcp_tools:
        agent = Agent(
            role=f"{SERVER_SLUG.title()} Data Assistant",
            goal=f"Help users query and manage their {SERVER_SLUG} data",
            backstory="Sample agent using Barndoor MCP integration.",
            tools=mcp_tools,
            verbose=True,
        )

        task = Task(
            description="Pipeline Report",
            expected_output="Give me a report of the sales pipeline with some insights",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

        print("\nRunning CrewAI with MCP tools…")
        result = crew.kickoff()
        print(f"\n✓ Result: {result}")

    await sdk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
