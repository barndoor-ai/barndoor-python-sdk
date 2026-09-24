"""Obtaining a token — the half of authentication no OpenAPI document describes.

The spec says a request carries ``Authorization: Bearer <token>``. It does not
say how to get one, refresh it before it expires, or run a browser login. That
is what this module is.

Every flow returns a :data:`TokenProvider`: an async callable the client asks on
every request. The generated ``Configuration.access_token`` is read inside
``auth_settings()`` each time a request is signed, so a provider that refreshes
transparently needs no hook — see :mod:`barndoor.lib.client`.

``authlib`` does the protocol work: discovery, the token endpoint, PKCE. The SDK
this replaces hand-rolled roughly 1,300 lines of it.
"""

from __future__ import annotations

import asyncio
import time

from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urlencode

# httpx2 is the httpx 2.x line, published under a distinct name. It is the SDK's
# single http stack: authlib's AsyncOAuth2Client subclasses it, mcp depends on
# it, and templates/httpx/rest.mustache aliases the generated client onto it.
import httpx2 as httpx

from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc7636 import create_s256_code_challenge


#: Asked for a token on every request. Implementations cache; the client does
#: not.
TokenProvider = Callable[[], Awaitable[str]]

#: Refresh this long before a token actually expires, so a token does not die
#: in flight between being signed and being validated.
EXPIRY_SKEW_SECONDS = 60


def static_token(token: str) -> TokenProvider:
    """A token you already hold — an API key, or one sourced elsewhere."""

    async def provide() -> str:
        return token

    return provide


def _expiry_from(expires_in: float | None) -> float:
    """When a token obtained now should be considered stale.

    ``expires_in`` is optional in OAuth 2.0. Treating an absent value as
    "already expired" would re-fetch on every request; treating it as "never
    expires" is what every other client does. ``expires_in: 0`` means already
    expired, and must not be confused with absent.
    """
    if expires_in is None:
        return float("inf")
    return time.monotonic() + (expires_in - EXPIRY_SKEW_SECONDS)


@dataclass
class _Cache:
    """A token and when to stop trusting it.

    The lock is what stops a burst of concurrent requests on a cold cache from
    each starting its own token exchange — and, on failure, from caching a
    rejection. The TypeScript SDK had to clear a cached *promise* on rejection
    for the same reason; an asyncio lock makes it structural.
    """

    token: str | None = None
    expires_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def fresh(self) -> str | None:
        if self.token is not None and time.monotonic() < self.expires_at:
            return self.token
        return None

    def store(self, token: str, expires_in: float | None) -> str:
        self.token = token
        self.expires_at = _expiry_from(expires_in)
        return token


@dataclass(frozen=True)
class ClientCredentialsOptions:
    """Machine-to-machine credentials, exchanged and refreshed for you."""

    client_id: str
    client_secret: str
    #: Defaults to the issuer the spec declares.
    issuer: str | None = None
    #: Space-delimited. Defaults to what every published operation requires.
    scope: str | None = None
    #: Replaces the transport used to reach the authorization server, for
    #: BOTH discovery and the token exchange.
    #:
    #: A transport rather than a client, because it has to apply to authlib's
    #: own client as well as ours — an injected client would have covered
    #: discovery only, and the token exchange would have gone to the real IdP.
    #: It is also the layer httpx puts proxies and custom connection behaviour
    #: on, so a caller needing those is served by the same seam as a test.
    transport: httpx.AsyncBaseTransport | None = None


async def _discover_token_endpoint(issuer: str, client: httpx.AsyncClient) -> str:
    """Resolve the token endpoint from the issuer's discovery document.

    Discovered rather than assembled: the path is ``/protocol/openid-connect/token``
    on Keycloak and something else everywhere else, and an issuer is allowed to
    move it.
    """
    well_known = issuer.rstrip("/") + "/.well-known/openid-configuration"
    response = await client.get(well_known)
    response.raise_for_status()
    endpoint = response.json().get("token_endpoint")
    if not endpoint:
        raise ValueError(f"{well_known} declares no token_endpoint")
    return endpoint


def client_credentials(options: ClientCredentialsOptions) -> TokenProvider:
    """Exchange client credentials for access tokens, refreshing as needed."""
    from barndoor.lib.config import PRODUCTION_ISSUER

    issuer = options.issuer or PRODUCTION_ISSUER
    cache = _Cache()

    async def provide() -> str:
        cached = cache.fresh()
        if cached is not None:
            return cached

        async with cache.lock:
            # Another waiter may have refreshed while this one queued.
            cached = cache.fresh()
            if cached is not None:
                return cached

            async with httpx.AsyncClient(transport=options.transport) as discovery:
                endpoint = await _discover_token_endpoint(issuer, discovery)

            async with AsyncOAuth2Client(
                client_id=options.client_id,
                client_secret=options.client_secret,
                scope=options.scope,
                transport=options.transport,
            ) as oauth:
                token = await oauth.fetch_token(endpoint, grant_type="client_credentials")

            return cache.store(token["access_token"], token.get("expires_in"))

    return provide


def refresh_token(
    token: str,
    *,
    client_id: str,
    issuer: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TokenProvider:
    """Keep a user session alive from a refresh token.

    The counterpart to :func:`complete_authorization_code`: that returns a
    refresh token, this turns it into access tokens for as long as it lives.
    """
    from barndoor.lib.config import PRODUCTION_ISSUER

    resolved_issuer = issuer or PRODUCTION_ISSUER
    cache = _Cache()
    current = {"refresh": token}

    async def provide() -> str:
        cached = cache.fresh()
        if cached is not None:
            return cached

        async with cache.lock:
            cached = cache.fresh()
            if cached is not None:
                return cached

            async with httpx.AsyncClient(transport=transport) as discovery:
                endpoint = await _discover_token_endpoint(resolved_issuer, discovery)

            async with AsyncOAuth2Client(client_id=client_id, transport=transport) as oauth:
                granted = await oauth.refresh_token(endpoint, refresh_token=current["refresh"])

            # Rotated refresh tokens are the default in Keycloak: keeping the
            # original would work exactly once.
            if granted.get("refresh_token"):
                current["refresh"] = granted["refresh_token"]

            return cache.store(granted["access_token"], granted.get("expires_in"))

    return provide


@dataclass(frozen=True)
class AuthorizationCodeRequest:
    """Where to send the user, and what to keep until they come back."""

    #: Send the user here.
    url: str
    #: Hold these until the redirect arrives; they are not secrets to the user
    #: but must not be shared between concurrent logins.
    state: str
    code_verifier: str


def start_authorization_code(
    *,
    client_id: str,
    redirect_uri: str,
    issuer: str | None = None,
    scope: str = "openid profile email offline_access",
) -> AuthorizationCodeRequest:
    """Begin an interactive login.

    PKCE always, not only for public clients: it costs nothing and closes
    authorization-code interception, which a loopback redirect on a shared
    machine is exactly exposed to.

    Synchronous on purpose — it builds a URL and touches no network, so a caller
    can render a link without an event loop.
    """
    import secrets

    from barndoor.lib.config import PRODUCTION_ISSUER

    resolved = (issuer or PRODUCTION_ISSUER).rstrip("/")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)

    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": create_s256_code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return AuthorizationCodeRequest(
        url=f"{resolved}/protocol/openid-connect/auth?{query}",
        state=state,
        code_verifier=verifier,
    )


async def complete_authorization_code(
    code: str,
    request: AuthorizationCodeRequest,
    *,
    client_id: str,
    redirect_uri: str,
    issuer: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Exchange the returned code for tokens.

    Returns the raw token response, so a caller can persist ``refresh_token``
    and hand it to :func:`refresh_token` later. The SDK deliberately stores
    nothing on disk: where a credential belongs is the application's decision,
    and the SDK this replaces made it for them.
    """
    from barndoor.lib.config import PRODUCTION_ISSUER

    resolved_issuer = issuer or PRODUCTION_ISSUER
    async with httpx.AsyncClient(transport=transport) as discovery:
        endpoint = await _discover_token_endpoint(resolved_issuer, discovery)

    async with AsyncOAuth2Client(client_id=client_id, redirect_uri=redirect_uri, transport=transport) as oauth:
        return await oauth.fetch_token(
            endpoint,
            code=code,
            code_verifier=request.code_verifier,
            grant_type="authorization_code",
        )
