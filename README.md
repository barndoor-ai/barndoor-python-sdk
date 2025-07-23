# Barndoor SDK

A lightweight, **framework-agnostic** Python client for the Barndoor Platform REST APIs and Model Context Protocol (MCP) servers.

The SDK removes boiler-plate around:

* Secure, offline-friendly **Auth0 authentication** (interactive PKCE flow + token caching).
* **Server registry** – list, inspect and connect third-party providers (Salesforce, Notion, Slack …).
* **Managed Connector Proxy** – build ready-to-use connection parameters for any LLM/agent framework (CrewAI, LangChain, custom code …) without importing Barndoor-specific adapters.

---

## Installation

```bash
pip install barndoor-sdk  # coming soon – for now use an editable install
# or, inside this repo
pip install -e libs/barndoor[dev]
```

Python ≥ 3.10 is required.

---

## Local development with uv

For the fastest install and reproducible builds you can use [uv](https://github.com/astral-sh/uv) instead of `pip`.

```bash
# 1) (one-off) install uv
brew install uv        # or follow the install script on Linux/Windows

# 2) create an isolated virtual environment in the repo
uv venv .venv
source .venv/bin/activate

# 3) install the SDK in editable mode plus the example extras
uv pip install -e '.[examples]'

# 4) install MCP support for CrewAI examples
uv pip install 'crewai-tools[mcp]'

# 5) copy the environment template and add your credentials
cp env.example .env
# Edit .env to add AGENT_CLIENT_ID, AGENT_CLIENT_SECRET, and OPENAI_API_KEY

# 6) run the interactive login utility once (opens browser)
uv run python -m barndoor.sdk.cli_login

# 7) kick off the Notion sample agent
uv run python examples/sample_notion_agent.py
```

**Note:** The OAuth callback uses port 52765. Make sure this is registered in your Auth0 app as:
```
http://localhost:52765/cb
```

The examples expect a `.env` file next to each script containing:

```bash
AGENT_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
AGENT_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyy
# optional overrides
AUTH0_DOMAIN=barndoor-local.us.auth0.com
BARNDOOR_API=http://localhost:8003
```

---

## Authentication workflow

Barndoor APIs expect a **user JWT** issued by your organisation’s Auth0 tenant.  The SDK offers two ways to obtain & store such a token:

| Option | Command | When to use |
|--------|---------|-------------|
| Interactive CLI | `python -m barndoor.sdk.cli_login` *(alias: `barndoor-login`)* | One-time setup on laptops / CI machines |
| In-code helper | `await barndoor.sdk.login_interactive()` | Notebooks or scripts where you do not want a separate login step |

Both variants:

1. Spin up a tiny localhost callback server.
2. Open the system browser to Auth0.
3. Exchange the returned *code* for a JWT.
4. Persist the token to `~/.barndoor/token.json` (0600 permissions).

Environment variables (or a neighbouring `.env` file) must define the Agent OAuth application:

```
AGENT_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
AGENT_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyy
# optional overrides
AUTH0_DOMAIN=barndoor-local.us.auth0.com
BARNDOOR_API=http://localhost:8003
```

The cached token is auto-refreshed on every run; if it is expired or revoked a new browser flow is launched.

---

## Auth0 Application Setup

When configuring your Auth0 "Agent" application, make sure to:

1. Add the following to **Allowed Callback URLs**:
   ```
   http://localhost:52765/cb
   http://127.0.0.1:52765/cb
   ```

2. Set the **Application Type** to "Native" or "Single Page Application"

3. Enable the **Authorization Code** flow with PKCE

---

## Quick-start in four lines

```python
import barndoor.sdk as bd

sdk = await bd.login_interactive()         # 1️⃣ ensure valid token
await bd.ensure_server_connected(sdk, "salesforce")  # 2️⃣ make sure OAuth is done
params, _public_url = await bd.make_mcp_connection_params(sdk, "salesforce")
```

`params` is a plain dict with `url`, `headers` and (optionally) `transport` – ready to plug into **any** HTTP / SSE / WebSocket client.  See the examples below for CrewAI & LangChain usage.

---

## Using the Registry API

```python
# List all MCP servers available to the current user
servers = await sdk.list_servers()
print([s.slug for s in servers])  # ['salesforce', 'notion', ...]

# Get detailed metadata (quota, scopes, etc.)
details = await sdk.get_server(server_id=servers[0].id)
print(details)
```

Additional helpers:

* `await sdk.initiate_connection(server_id)` – returns an OAuth URL the user must visit.
* `await bd.ensure_server_connected(sdk, "notion")` – combines status polling + browser launch.

---

## Model Context Protocol Connection

Once a server is **connected** you can stream requests through Barndoor’s proxy edge.

```python
params, public_url = await bd.make_mcp_connection_params(sdk, "notion")

print(params["url"])         # http(s)://…/mcp/notion
print(params["headers"])     # {'Authorization': 'Bearer ey…', 'x-barndoor-session-id': …}
```

The helper automatically decides whether to use a local proxy or a regional CloudFront URL based on `BARNDOOR_ENV`:

* `prod` (default) → `https://api.barndoor.ai/mcp/{slug}`
* `dev`  → `https://barndoor.api/mcp/{slug}`
* `local` → `http://proxy-ingress:8080/mcp/{slug}`

---

## Environment overrides (local & dev testing)

By **default** the SDK talks to the production Barndoor cloud.  When you are
hacking on your own infrastructure or a staging cluster you can switch the
target environment entirely via **environment variables** (usually in a local
`.env` file):

| Scenario | Required variables | Typical values |
|----------|-------------------|----------------|
| **Production** (public) | *(none – everything defaults to prod)* | – |
| **Dev cluster** | `BARNDOOR_ENV`, `BARNDOOR_API` | `dev`, `https://barndoor.api` |
| **Local docker-compose** | `BARNDOOR_ENV`, `BARNDOOR_API` | `local`, `http://localhost:8003` |

Example `.env` for a **local** stack:

```bash
BARNDOOR_ENV=local          # makes helpers build http://proxy-ingress:8080/… URLs
BARNDOOR_API=http://localhost:8003
AUTH0_DOMAIN=barndoor-local.us.auth0.com  # sample tenant baked into docker-compose
AGENT_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
AGENT_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyy
```

With this file present the four-line quick-start from above will log in against
your local Auth0 tenant and route MCP traffic through the local proxy ingress –
no code changes required.

---

## End-to-end examples

### 1. Salesforce Assistant (CrewAI)

```bash
cd libs/barndoor/examples
python sample_salesforce_agent.py     # local env / proxy
python sample_salesforce_agent_dev.py # staging env
```

Both scripts demonstrate:

* interactive login + caching
* automatic connection check (OAuth if needed)
* building MCP params → `MCPServerAdapter` (CrewAI)

### 2. Multi-provider Pipeline Report

`sample_pipeline_report_agent.py` shows how to combine **two** MCP adapters (Salesforce **read** + Notion **write**) inside a single agent.

Run with:

```bash
python sample_pipeline_report_agent.py
```

### 3. Token utilities

* `token_cli.py` – small CLI to inspect / clear the cached JWT.
* `token_validation_example.py` – async snippet calling `/identity/token` directly.

---

## Minimal API reference

| Method | Purpose |
|--------|---------|
| `BarndoorSDK.validate_cached_token()` | Validate the cached JWT against `/identity/token` |
| `BarndoorSDK.list_servers()` | Return `List[ServerSummary]` |
| `BarndoorSDK.get_server(server_id)` | Full `ServerDetail` |
| `BarndoorSDK.initiate_connection()` | Start OAuth flow (returns URL) |
| `BarndoorSDK.get_connection_status()` | `connected` / `pending` / `error` |
| `BarndoorSDK.ensure_server_connected()` | High-level helper combining the above |
