"""Token acquisition, caching and refresh — against a stub, never a live IdP."""

from __future__ import annotations

import asyncio

# httpx2: the stack authlib is built on. See barndoor/lib/auth.py.
import httpx2 as httpx
import pytest

from barndoor.lib.auth import (
    ClientCredentialsOptions,
    _expiry_from,
    client_credentials,
    static_token,
)


def _idp(token_calls: list, *, expires_in=3600, discovery_status=200, token_status=200):
    """A Keycloak-shaped stub: a discovery document and a token endpoint.

    Returned as a transport, which is what both the discovery client and
    authlib's own client accept — an injected client would have covered
    discovery only and let the token exchange reach the real IdP.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            if discovery_status != 200:
                return httpx.Response(discovery_status)
            return httpx.Response(200, json={"token_endpoint": "https://idp.test/realms/b/token"})
        token_calls.append(request)
        if token_status != 200:
            return httpx.Response(token_status, json={"error": "invalid_client"})
        body = {"access_token": f"tok-{len(token_calls)}", "token_type": "Bearer"}
        if expires_in is not None:
            body["expires_in"] = expires_in
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


async def test_static_token_is_returned_verbatim():
    assert await static_token("bdai_x")() == "bdai_x"


async def test_client_credentials_exchanges_once_and_caches():
    calls: list = []
    provider = client_credentials(
        ClientCredentialsOptions(
            client_id="id",
            client_secret="s",
            issuer="https://idp.test/realms/b",
            transport=_idp(calls),
        )
    )
    assert await provider() == "tok-1"
    assert await provider() == "tok-1"
    assert len(calls) == 1, "a cached token must not be re-fetched"


async def test_concurrent_callers_share_one_exchange():
    """A burst on a cold cache must not start one exchange per request."""
    calls: list = []
    provider = client_credentials(
        ClientCredentialsOptions(
            client_id="id",
            client_secret="s",
            issuer="https://idp.test/realms/b",
            transport=_idp(calls),
        )
    )
    results = await asyncio.gather(*(provider() for _ in range(8)))
    assert results == ["tok-1"] * 8
    assert len(calls) == 1


async def test_a_failure_is_not_cached():
    """A rejected exchange must be retried, not remembered.

    The TypeScript SDK had to clear a cached promise on rejection for the same
    reason; here the lock plus storing only on success makes it structural.
    """
    calls: list = []
    provider = client_credentials(
        ClientCredentialsOptions(
            client_id="id",
            client_secret="s",
            issuer="https://idp.test/realms/b",
            transport=_idp(calls, token_status=401),
        )
    )
    for _ in range(2):
        with pytest.raises(Exception):
            await provider()
    assert len(calls) == 2, "the second call must try again"


async def test_a_missing_discovery_document_is_an_error_not_a_guess():
    calls: list = []
    provider = client_credentials(
        ClientCredentialsOptions(
            client_id="id",
            client_secret="s",
            issuer="https://idp.test/realms/b",
            transport=_idp(calls, discovery_status=404),
        )
    )
    with pytest.raises(httpx.HTTPStatusError):
        await provider()
    assert calls == [], "the token endpoint must not be assembled by hand"


def test_absent_expires_in_means_never_expires():
    """`expires_in` is optional in OAuth 2.0.

    Treating absent as "already expired" would re-fetch on every request.
    """
    assert _expiry_from(None) == float("inf")


def test_expires_in_zero_means_already_expired():
    """Zero is falsy and must not be confused with absent."""
    assert _expiry_from(0) < float("inf")


def test_the_skew_expires_a_token_before_the_server_does():
    """A token must not die in flight between being signed and validated."""
    import time

    from barndoor.lib.auth import EXPIRY_SKEW_SECONDS

    expiry = _expiry_from(EXPIRY_SKEW_SECONDS + 10)
    assert expiry - time.monotonic() == pytest.approx(10, abs=1)
