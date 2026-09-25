"""The MCP client.

The platform serves the Model Context Protocol alongside REST, on the same
hostname with the organization in front of it. None of that is in the OpenAPI
document — MCP is a different protocol — so it is described here.
"""

from __future__ import annotations

import secrets
import uuid

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from .client import BarndoorClient


@dataclass(frozen=True)
class McpOptions:
    """Where to connect, and who to say you are."""

    #: The host serving MCP, WITHOUT the organization subdomain. Defaults to
    #: the client's API base URL, since one vhost serves both /api and /mcp.
    base_url: str | None = None
    #: Correlates every call in one session in Barndoor's audit trail.
    session_id: str | None = None
    #: Reported to the MCP server during initialisation.
    client_name: str = "barndoor-sdk"
    client_version: str = "2.0.0"


def _new_session_id() -> str:
    """A session id that does not depend on a secure context.

    ``uuid4`` is fine on the server side; the TypeScript SDK needs a fallback
    because ``crypto.randomUUID`` is undefined over plain HTTP in a browser.
    """
    try:
        return str(uuid.uuid4())
    except Exception:  # pragma: no cover - uuid4 does not fail in practice
        return secrets.token_hex(16)


def _with_organization(base_url: str, org_slug: str) -> str:
    """Put the tenant in front of the host.

    ``platform.example.com`` becomes ``acme.platform.example.com``.
    """
    parsed = urlparse(base_url)
    if not parsed.hostname:
        raise ValueError(f"{base_url!r} has no host to prefix")
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse(parsed._replace(netloc=f"{org_slug}.{parsed.hostname}{port}", path="/mcp"))


async def mcp_connection_params(
    client: BarndoorClient,
    org_slug: str,
    options: McpOptions | None = None,
) -> tuple[str, dict[str, str]]:
    """The URL and headers to reach MCP, without opening a connection.

    For handing to another framework — CrewAI, LangChain, your own client —
    rather than using :func:`create_mcp_client`. The headers carry a bearer
    token; treat them as a secret.
    """
    if not org_slug:
        raise ValueError("An organization slug is required: it selects the tenant serving MCP")

    opts = options or McpOptions()
    base = opts.base_url or client.configuration.host
    url = _with_organization(base, org_slug)

    # The same provider the REST client uses, so one login serves both and a
    # refresh is shared.
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {await _token_for(client)}",
        "x-barndoor-session-id": opts.session_id or _new_session_id(),
    }
    return url, headers


async def _token_for(client: BarndoorClient) -> str:
    """Borrow the REST client's token provider.

    ``create_client`` installs it on ``call_api``; reaching it through a
    dedicated attribute rather than re-deriving it means one login serves both
    protocols and a refresh is shared.
    """
    provider = getattr(client.api_client, "_barndoor_token_provider", None)
    if provider is None:
        raise RuntimeError("client was not built by create_client()")
    return await provider()


def mcp_client(
    client: BarndoorClient,
    org_slug: str,
    options: McpOptions | None = None,
):
    """An MCP session, as an async context manager.

    A context manager rather than a returned session because the transport owns
    a connection: leaving it to the caller to close is the "resource lifecycle"
    trap, and an ``async with`` cannot be forgotten on an early return.

        async with mcp_client(client, "acme") as session:
            tools = await session.list_tools()
    """
    return _McpSession(client, org_slug, options)


class _McpSession:
    def __init__(self, client: BarndoorClient, org_slug: str, options: McpOptions | None):
        self._client = client
        self._org = org_slug
        self._options = options
        self._transport = None

    async def __aenter__(self) -> ClientSession:
        url, headers = await mcp_connection_params(self._client, self._org, self._options)
        # `streamable_http_client` takes no headers of its own: authentication
        # rides on the http client it is handed. `create_mcp_http_client` is the
        # package's own constructor, so timeouts and limits stay whatever the
        # MCP client expects rather than whatever this SDK would have guessed.
        self._http = create_mcp_http_client(headers=headers)
        self._transport = streamable_http_client(url, http_client=self._http)
        read, write = await self._transport.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        try:
            await self._session.__aexit__(*exc)
        finally:
            try:
                if self._transport is not None:
                    await self._transport.__aexit__(*exc)
            finally:
                if getattr(self, "_http", None) is not None:
                    await self._http.aclose()
