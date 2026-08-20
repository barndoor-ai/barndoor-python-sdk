from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import os

import barndoor.sdk as bd
from barndoor.sdk.config import get_config
from crewai import Agent, Task, Crew
from crewai_tools import MCPServerAdapter


async def main() -> None:
    # 1️⃣ Load environment
    load_dotenv(Path(__file__).parent / ".env")

    print("🔐 Logging into Barndoor...")
    sdk = await bd.login_interactive()
    config = get_config()

    print(f"\n✅ Logged in! Workspace: {config.api_base_url}")
    print(f"🔌 MCP Base URL: {config.mcp_base_url}\n")

    # 2️⃣ List available MCP servers
    servers = await sdk.list_servers()

    if not servers:
        print("❌ No MCP servers available for this workspace.")
        return

    print("🌐 Available MCP servers:")
    for idx, s in enumerate(servers, start=1):
        print(f"  {idx}. {s.slug:<15} status={s.connection_status}")

    # 3️⃣ Let user pick which server to use
    while True:
        choice = input("\nEnter the number of the MCP server to use: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(servers):
            chosen_server = servers[int(choice) - 1]
            break
        print("⚠️ Invalid choice. Please enter a valid number.")

    server_slug = chosen_server.slug
    print(f"\n🔧 Selected MCP server: {server_slug}\n")

    # 4️⃣ Ensure the selected server is connected
    await bd.ensure_server_connected(sdk, server_slug)
    params, public_url = await bd.make_mcp_connection_params(sdk, server_slug)
    print(f"🔗 Connected MCP URL: {params['url']}")

    # 5️⃣ Ask for a custom prompt
    user_prompt = input(
        "\n💬 Enter the task you'd like the agent to perform (e.g., 'List 10 Salesforce opportunities'): "
    ).strip()

    if not user_prompt:
        user_prompt = f"Describe and summarize data from the {server_slug} workspace."

    # 6️⃣ Create and run the CrewAI agent
    with MCPServerAdapter(params) as mcp_tools:
        agent = Agent(
            role=f"{server_slug.capitalize()} Assistant",
            goal=f"Use the {server_slug} MCP server to perform useful queries and summarize results.",
            backstory=f"A multi-domain assistant that can interact with {server_slug} through Barndoor MCP.",
            tools=mcp_tools,
            verbose=True,
        )

        task = Task(
            description=user_prompt,
            expected_output="A detailed but concise response based on the MCP data.",
            agent=agent,
        )

        crew = Crew(agents=[agent], tasks=[task], verbose=True)

        print("\n🚀 Running CrewAI task...\n")
        result = await crew.kickoff_async()

    # 7️⃣ Save a Markdown report
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"{server_slug}_result_{ts}.md"
    report_file.write_text(f"# {server_slug.capitalize()} Agent Report\n\n{result}", encoding="utf-8")

    print(f"\n✅ Task complete! Result saved to:\n   {report_file.resolve()}")
    await sdk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
