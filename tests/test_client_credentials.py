"""Tests for OAuth client-credentials (M2M) support."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from barndoor.sdk import (
    BarndoorSDK,
    get_client_credentials_token,
    get_client_credentials_token_async,
)
from barndoor.sdk.client import _token_near_expiry
from barndoor.sdk.exceptions import HTTPError


def _jwt(exp_seconds_from_now: int) -> str:
    """Return an unsigned-looking JWT with the given ``exp`` offset."""
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time()) + exp_seconds_from_now}).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


class TestTokenNearExpiry:
    def test_token_well_within_window(self):
        assert _token_near_expiry(_jwt(3600), skew_seconds=60) is False

    def test_token_inside_skew(self):
        assert _token_near_expiry(_jwt(30), skew_seconds=60) is True

    def test_token_already_expired(self):
        assert _token_near_expiry(_jwt(-10), skew_seconds=60) is True

    def test_unparseable_token_treated_as_expired(self):
        assert _token_near_expiry("not-a-jwt", skew_seconds=60) is True


class TestGetClientCredentialsToken:
    def test_sync_posts_grant_and_returns_access_token(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "abc.def.ghi"}
        mock_resp.raise_for_status.return_value = None

        with (
            patch("barndoor.sdk.auth.get_oidc_config") as mock_oidc,
            patch("barndoor.sdk.auth.httpx.post") as mock_post,
        ):
            mock_oidc.return_value = {"token_endpoint": "https://issuer.test/token"}
            mock_post.return_value = mock_resp

            token = get_client_credentials_token(
                domain="",
                client_id="cid",
                client_secret="csec",
                audience="https://barndoor.ai/",
                issuer="https://issuer.test",
            )

        assert token == "abc.def.ghi"
        args, kwargs = mock_post.call_args
        assert args[0] == "https://issuer.test/token"
        assert kwargs["data"] == {
            "grant_type": "client_credentials",
            "client_id": "cid",
            "client_secret": "csec",
            "audience": "https://barndoor.ai/",
        }

    def test_sync_requires_issuer_or_domain(self):
        with pytest.raises(ValueError, match="issuer.*domain"):
            get_client_credentials_token(
                domain="",
                client_id="cid",
                client_secret="csec",
                audience="https://barndoor.ai/",
            )

    @pytest.mark.asyncio
    async def test_async_uses_async_client(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok"}
        mock_resp.raise_for_status.return_value = None

        with (
            patch("barndoor.sdk.auth.get_oidc_config") as mock_oidc,
            patch("barndoor.sdk.auth.httpx.AsyncClient") as mock_cls,
        ):
            mock_oidc.return_value = {"token_endpoint": "https://issuer.test/token"}
            client = AsyncMock()
            client.post.return_value = mock_resp
            mock_cls.return_value.__aenter__.return_value = client

            token = await get_client_credentials_token_async(
                client_id="cid",
                client_secret="csec",
                audience="https://barndoor.ai/",
                issuer="https://issuer.test",
            )

        assert token == "tok"
        client.post.assert_awaited_once()
        (call_url,) = client.post.call_args.args
        assert call_url == "https://issuer.test/token"


class TestBarndoorSDKFromClientCredentials:
    @pytest.mark.asyncio
    async def test_factory_fetches_token_and_sets_credentials(self):
        token = _jwt(3600)
        with patch(
            "barndoor.sdk.auth.get_client_credentials_token_async",
            new=AsyncMock(return_value=token),
        ) as mock_fetch:
            sdk = await BarndoorSDK.from_client_credentials(
                "https://api.barndoor.host",
                client_id="cid",
                client_secret="csec",
                audience="https://barndoor.ai/",
                issuer="https://issuer.test",
            )

        try:
            assert sdk.token == token
            assert sdk._credentials is not None
            assert sdk._credentials.client_id == "cid"
            mock_fetch.assert_awaited_once()
        finally:
            await sdk.aclose()

    @pytest.mark.asyncio
    async def test_request_refreshes_token_near_expiry(self):
        stale = _jwt(10)  # within default 60s skew
        fresh = _jwt(3600)

        with patch(
            "barndoor.sdk.auth.get_client_credentials_token_async",
            new=AsyncMock(side_effect=[stale, fresh]),
        ):
            sdk = await BarndoorSDK.from_client_credentials(
                "https://api.barndoor.host",
                client_id="cid",
                client_secret="csec",
                audience="https://barndoor.ai/",
                issuer="https://issuer.test",
            )

            try:
                with patch.object(
                    sdk._http, "request", new=AsyncMock(return_value={"data": []})
                ) as mock_req:
                    await sdk._req("GET", "/api/servers")

                assert sdk.token == fresh
                assert mock_req.await_count == 1
                _, kwargs = mock_req.call_args
                assert kwargs["headers"]["Authorization"] == f"Bearer {fresh}"
            finally:
                await sdk.aclose()

    @pytest.mark.asyncio
    async def test_request_retries_once_on_401(self):
        first = _jwt(3600)
        second = _jwt(3600)

        with patch(
            "barndoor.sdk.auth.get_client_credentials_token_async",
            new=AsyncMock(side_effect=[first, second]),
        ):
            sdk = await BarndoorSDK.from_client_credentials(
                "https://api.barndoor.host",
                client_id="cid",
                client_secret="csec",
                audience="https://barndoor.ai/",
                issuer="https://issuer.test",
            )

            try:
                with patch.object(
                    sdk._http,
                    "request",
                    new=AsyncMock(side_effect=[HTTPError(401, "expired"), {"ok": True}]),
                ) as mock_req:
                    result = await sdk._req("GET", "/api/servers")

                assert result == {"ok": True}
                assert mock_req.await_count == 2
                assert sdk.token == second
                # Second call should carry the refreshed bearer token.
                _, kwargs = mock_req.call_args_list[1]
                assert kwargs["headers"]["Authorization"] == f"Bearer {second}"
            finally:
                await sdk.aclose()

    @pytest.mark.asyncio
    async def test_request_does_not_retry_401_without_credentials(self, sdk_client):
        """Plain BarndoorSDK (no M2M creds) should propagate 401 as-is."""
        with patch.object(
            sdk_client._http,
            "request",
            new=AsyncMock(side_effect=HTTPError(401, "expired")),
        ) as mock_req:
            with pytest.raises(HTTPError):
                await sdk_client._req("GET", "/api/servers")

        assert mock_req.await_count == 1
