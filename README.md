# barndoor

Official Python SDK for the [Barndoor AI](https://barndoor.ai) platform API.

```bash
pip install barndoor
```

Python 3.11 or later. Async, fully typed.

## Quick start

```python
import asyncio
from barndoor import create_client

async def main():
    client = create_client(auth="bdai_…")
    page = await client.registry.list_mcp_servers(limit=10)
    for server in page.data:
        print(server.name, server.slug)
    await client.aclose()

asyncio.run(main())
```

`create_client` is synchronous and touches no network, so building a client
cannot fail because an identity provider is briefly unreachable. Use it as an
async context manager to close the connection pool for you:

```python
async with create_client(auth="bdai_…") as client:
    ...
```

## Authentication

`auth` takes one of three things.

**An API key**, or any token you already hold:

```python
create_client(auth="bdai_…")
```

**Machine-to-machine credentials**, exchanged and refreshed for you:

```python
from barndoor import ClientCredentialsOptions

create_client(auth=ClientCredentialsOptions(
    client_id=os.environ["BARNDOOR_CLIENT_ID"],
    client_secret=os.environ["BARNDOOR_CLIENT_SECRET"],
))
```

**Your own provider**, an async callable asked on every request — for a token
you source from a secrets manager or an inbound request:

```python
create_client(auth=lambda: fetch_token_from_vault())
```

For a user-facing login there is `start_authorization_code` /
`complete_authorization_code` (PKCE), and `barndoor-login` runs the browser flow
from a terminal.

## API surface

| Namespace | Covers |
|---|---|
| `client.registry` | MCP servers, agents, connections, the directory |
| `client.policy` | Policies, rules, impact analysis |
| `client.identity` | Organizations, users, groups, identity providers |
| `client.notification` | Channels, alerts, subscriptions |
| `client.dlp` | Detection rules, findings, redaction |
| `client.llm_gateway` | Models, budgets, API keys, usage |
| `client.system_management` | Operational endpoints |

The full surface is the OpenAPI specification the client is generated from,
published here as [openapi.yaml](./openapi.yaml). Types ship with the package,
so your editor is usually the fastest reference.

## Connecting to MCP

The platform serves [MCP](https://modelcontextprotocol.io) as well as REST,
authenticated with the same credentials:

```python
from barndoor import create_client, mcp_client

async with create_client(auth="bdai_…") as client:
    async with mcp_client(client, "acme") as session:
        tools = await session.list_tools()
```

A context manager because the transport owns a connection — an `async with`
cannot be forgotten on an early return. If you would rather hand connection
details to another framework, `mcp_connection_params` returns the URL and
headers without opening anything.

## Reliability

Requests are retried with jittered exponential backoff. Only idempotent methods
are retried: a 502 does not say whether a write landed, so repeating a POST
risks a duplicate.

```python
from barndoor import RetryOptions

create_client(auth=key, retry=RetryOptions(retries=5, timeout=60.0))
create_client(auth=key, retry=RetryOptions(retries=0))   # off
```

`Retry-After` is honoured, in both its seconds and HTTP-date forms.

## Non-production environments

Production is the default and needs no configuration.

```python
from barndoor import create_client, DEV, environment_from_env

create_client(auth=key, env=DEV)
create_client(auth=key, env=environment_from_env())   # reads BARNDOOR_ENV
```

Credentials inherit the environment's issuer, so pointing at dev cannot leave
you calling dev with a production token. The SDK never reads the environment
unless you ask it to.

## Examples

Runnable examples are in [examples/](./examples).

## Versioning

The version is the version of the **API contract**, so which SDK speaks to which
API needs no lookup table. It is independent of the Barndoor platform's own
release version.

| Part | Changes when |
|---|---|
| MAJOR | the API breaks — an operation removed, a field made required |
| MINOR | the API gains something — a new operation or optional field |
| PATCH | the SDK changes on its own — a fix, a dependency bump |

Versions carrying a `.devN` suffix are prereleases built from unreleased
platform work. `pip install barndoor` gives you the latest formal release.

## This repository is generated

The client, this README and the examples are generated or maintained in
Barndoor's platform monorepo and pushed here, which is where the package is
published from. **Pull requests against generated files here will be
overwritten.** Open an issue instead, or contact your Barndoor representative.

## License

MIT — see [LICENSE](./LICENSE).
