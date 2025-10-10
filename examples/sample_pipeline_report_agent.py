"""
Barndoor demo: pull a Salesforce pipeline report and post it to Notion.

This sample shows how an agent can use **two** MCP server integrations
(simultaneously) inside CrewAI:

• Salesforce (read-only) – fetch the latest pipeline metrics.
• Notion (read-write) – update or create a report page.

Run with:
    python sample_pipeline_report_agent.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from dotenv import load_dotenv

import barndoor.sdk as bd
from crewai import Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter


# Default slugs (can be overridden dynamically)
SF_SLUG = "salesforce"
NOTION_SLUG = "notion"


async def ensure_server_exists(sdk, slug: str) -> str:
    """Check if an MCP server exists, else prompt user to select one."""
    servers = await sdk.list_servers()
    available = [s.slug for s in servers]

    if slug not in available:
        print(f"\n⚠️ Server '{slug}' not found in your workspace.")
        print("Available servers:")
        for i, s in enumerate(available, start=1):
            print(f"  {i}. {s}")
        try:
            choice = int(input(f"\n👉 Select replacement for '{slug}' (1-{len(available)}): "))
            slug = available[choice - 1]
            print(f"✅ Using '{slug}' instead of missing server.")
        except Exception:
            raise ValueError(f"❌ No valid replacement chosen for '{slug}'.")
    else:
        print(f"✅ Found server '{slug}'.")
    return slug


async def main() -> None:
    # Load .env
    load_dotenv(Path(__file__).parent.parent / ".env")

    print("🔐 Logging in to Barndoor...")
    sdk = await bd.login_interactive()

    # List available servers
    print("\n🌐 Checking your available MCP servers...")
    servers = await sdk.list_servers()
    for s in servers:
        print(f"  • {s.slug:<12} ({s.connection_status})")

    # Ensure both servers exist or ask user to pick replacements
    sf_slug = await ensure_server_exists(sdk, SF_SLUG)
    notion_slug = await ensure_server_exists(sdk, NOTION_SLUG)

    # Ensure both are connected (OAuth flow if needed)
    print("\n🔄 Ensuring both servers are connected…")
    await bd.ensure_server_connected(sdk, sf_slug)
    await bd.ensure_server_connected(sdk, notion_slug)

    # Build MCP params
    print("🔧 Generating connection parameters...")
    sf_params, _ = await bd.make_mcp_connection_params(sdk, sf_slug)
    notion_params, _ = await bd.make_mcp_connection_params(sdk, notion_slug)

    # Run CrewAI task
    print("\n🤖 Running CrewAI pipeline agent...\n")
    with (
        MCPServerAdapter(sf_params) as sf_tools,
        MCPServerAdapter(notion_params) as notion_tools,
    ):
        tools = list(sf_tools) + list(notion_tools)

        agent = Agent(
            role="Revenue Ops Analyst",
            goal="Pull Salesforce pipeline data and publish it in Notion.",
            backstory="You gather opportunity metrics and share them with execs.",
            tools=tools,
            verbose=True,
        )

        task = Task(
            description=(
                "Generate today's pipeline report and publish it in Notion. "
                "If updating the 'Sales Pipeline – Auto-Report' page fails, "
                "create a new child page with today's data."
            ),
            expected_output="A Notion page URL with today's pipeline summary.",
            agent=agent,
        )

        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
        result = await crew.kickoff_async()
        print(f"\n✅ Finished – Result:\n{result}")

    await sdk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
