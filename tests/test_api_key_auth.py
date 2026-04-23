"""Tests for API key authentication in BarndoorSDK."""

from unittest.mock import AsyncMock, patch

import pytest

from barndoor.sdk.client import BarndoorSDK
from barndoor.sdk.exceptions import ConfigurationError


class TestAPIKeyAuth:
    """Test API key authentication path in BarndoorSDK."""

    def test_api_key_explicit(self):
        """API key passed directly is accepted."""
        sdk = BarndoorSDK(
            base_url="https://test.barndoor.ai",
            api_key="bdai_test_key_1234",
        )
        assert sdk.token == "bdai_test_key_1234"
        assert sdk._using_api_key is True

    def test_api_key_from_env(self):
        """API key read from BARNDOOR_API_KEY env var."""
        with patch.dict("os.environ", {"BARNDOOR_API_KEY": "bdai_env_key_5678"}):
            sdk = BarndoorSDK(base_url="https://test.barndoor.ai")
            assert sdk.token == "bdai_env_key_5678"
            assert sdk._using_api_key is True

    def test_api_key_explicit_overrides_env(self):
        """Explicit api_key takes priority over env var."""
        with patch.dict("os.environ", {"BARNDOOR_API_KEY": "bdai_env_key"}):
            sdk = BarndoorSDK(
                base_url="https://test.barndoor.ai",
                api_key="bdai_explicit_key",
            )
            assert sdk.token == "bdai_explicit_key"

    def test_api_key_bad_prefix_raises(self):
        """API key without bdai_ prefix raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="must start with 'bdai_'"):
            BarndoorSDK(
                base_url="https://test.barndoor.ai",
                api_key="sk_wrong_prefix",
            )

    def test_api_key_bad_prefix_env(self):
        """Bad prefix in env var raises ConfigurationError."""
        with patch.dict("os.environ", {"BARNDOOR_API_KEY": "bad_prefix_key"}):
            with pytest.raises(ConfigurationError, match="must start with 'bdai_'"):
                BarndoorSDK(base_url="https://test.barndoor.ai")

    def test_api_key_strips_whitespace(self):
        """Leading/trailing whitespace on API key is stripped."""
        sdk = BarndoorSDK(
            base_url="https://test.barndoor.ai",
            api_key="  bdai_spaced_key  ",
        )
        assert sdk.token == "bdai_spaced_key"

    def test_api_key_takes_priority_over_token(self):
        """When both api_key and barndoor_token are given, api_key wins."""
        mock_token = (
            "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"
            ".eyJzdWIiOiJ0ZXN0LXVzZXIiLCJleHAiOjk5OTk5OTk5OTl9.test"
        )
        sdk = BarndoorSDK(
            base_url="https://test.barndoor.ai",
            api_key="bdai_priority",
            barndoor_token=mock_token,
        )
        assert sdk.token == "bdai_priority"
        assert sdk._using_api_key is True

    def test_no_credential_raises_with_helpful_message(self):
        """When no credential at all, ValueError mentions all three auth paths."""
        with patch("barndoor.sdk.auth_store.load_user_token", return_value=None):
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(ValueError, match="BARNDOOR_API_KEY"):
                    BarndoorSDK(base_url="https://test.barndoor.ai")

    @pytest.mark.asyncio
    async def test_ensure_valid_token_skipped_for_api_key(self):
        """ensure_valid_token is a no-op when using API key."""
        sdk = BarndoorSDK(
            base_url="https://test.barndoor.ai",
            api_key="bdai_test_key",
        )
        # Should return immediately without doing any validation
        await sdk.ensure_valid_token()
        # _token_validated may still be False — the point is it didn't raise
        assert sdk._using_api_key is True

    @pytest.mark.asyncio
    async def test_api_key_used_as_bearer_in_requests(self):
        """API key is sent as Bearer token in API requests."""
        sdk = BarndoorSDK(
            base_url="https://test.barndoor.ai",
            api_key="bdai_bearer_test",
        )

        with patch.object(sdk._http, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            await sdk._req("GET", "/api/servers")

            # Check headers passed to the request
            call_kwargs = mock_req.call_args
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
            assert headers["Authorization"] == "Bearer bdai_bearer_test"
