"""Barndoor demo: run the Salesforce MCP server against the *dev* environment.

This variant of `sample_salesforce_agent.py` simply sets the environment
variable `BARNDOOR_ENV` to "dev" before invoking the standard quick-start
helpers so that the SDK builds the *external* (staging) MCP URL instead of the
local proxy one.

Usage
-----
    python sample_salesforce_agent_dev.py

Make sure you have a `.env` file alongside this script (see the main sample for
required variables).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

# Framework-agnostic SDK helpers ---------------------------------------------
import barndoor.sdk as bd

# Optional: only imported when we actually run the CrewAI demo
from crewai import Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter

SERVER_SLUG = "salesforce"  # change to the MCP server you want


async def main() -> None:  # noqa: D401
    # ---------------------------------------------------------------------
    # 0. Environment / login
    # ---------------------------------------------------------------------
    # Route through the external *dev* environment
    os.environ["BARNDOOR_ENV"] = "dev"

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
    # 3. Build connection params (external dev environment)
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
            backstory="Sample agent using Barndoor MCP integration (dev env).",
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
