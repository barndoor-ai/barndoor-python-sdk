"""Tests for stale/mismatched cached token detection in auth_store."""

import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from barndoor.sdk.auth_store import load_user_token


def _make_jwt(claims: dict) -> str:
    """Build a fake (unsigned) JWT with the given claims payload."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"typ": "JWT", "alg": "HS256"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


@pytest.fixture
def isolated_token_dir():
    """Temp directory mimicking ~/.barndoor/."""
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        bd_dir = home / ".barndoor"
        bd_dir.mkdir()
        yield home, bd_dir / "token.json"


class TestStaleTokenDetection:
    """Test issuer-mismatch detection in load_user_token."""

    def test_matching_issuer_returns_token(self, isolated_token_dir):
        """Token with matching issuer is returned normally."""
        home, token_file = isolated_token_dir
        issuer = "https://auth.trial.barndoor.ai/realms/barndoor-local"
        access_token = _make_jwt({"sub": "user", "iss": issuer, "exp": 9999999999})
        token_file.write_text(json.dumps({"access_token": access_token}))

        mock_cfg = MagicMock()
        mock_cfg.auth_issuer = issuer

        with (
            patch("pathlib.Path.home", return_value=home),
            patch("barndoor.sdk.config.get_static_config", return_value=mock_cfg),
        ):
            result = load_user_token()
            assert result == access_token

    def test_mismatched_issuer_clears_and_returns_none(self, isolated_token_dir):
        """Token from a different issuer triggers warning + clear."""
        home, token_file = isolated_token_dir
        old_issuer = "https://auth.barndoordev.com"
        new_issuer = "https://auth.trial.barndoor.ai/realms/barndoor-local"
        access_token = _make_jwt({"sub": "user", "iss": old_issuer, "exp": 9999999999})
        token_file.write_text(json.dumps({"access_token": access_token}))

        mock_cfg = MagicMock()
        mock_cfg.auth_issuer = new_issuer

        with (
            patch("pathlib.Path.home", return_value=home),
            patch("barndoor.sdk.config.get_static_config", return_value=mock_cfg),
        ):
            result = load_user_token()
            assert result is None
            # Token file should have been cleared
            assert not token_file.exists()

    def test_trailing_slash_normalization(self, isolated_token_dir):
        """Trailing slashes on issuer URLs don't cause false mismatches."""
        home, token_file = isolated_token_dir
        issuer_no_slash = "https://auth.barndoor.ai"
        access_token = _make_jwt({"sub": "user", "iss": issuer_no_slash + "/", "exp": 9999999999})
        token_file.write_text(json.dumps({"access_token": access_token}))

        mock_cfg = MagicMock()
        mock_cfg.auth_issuer = issuer_no_slash  # no trailing slash

        with (
            patch("pathlib.Path.home", return_value=home),
            patch("barndoor.sdk.config.get_static_config", return_value=mock_cfg),
        ):
            result = load_user_token()
            assert result == access_token

    def test_no_iss_claim_still_returns_token(self, isolated_token_dir):
        """Token without iss claim is returned without error (let downstream validate)."""
        home, token_file = isolated_token_dir
        access_token = _make_jwt({"sub": "user", "exp": 9999999999})
        token_file.write_text(json.dumps({"access_token": access_token}))

        mock_cfg = MagicMock()
        mock_cfg.auth_issuer = "https://auth.barndoor.ai"

        with (
            patch("pathlib.Path.home", return_value=home),
            patch("barndoor.sdk.config.get_static_config", return_value=mock_cfg),
        ):
            result = load_user_token()
            assert result == access_token

    def test_missing_file_returns_none(self, isolated_token_dir):
        """No token file → None, no crash."""
        home, token_file = isolated_token_dir
        if token_file.exists():
            token_file.unlink()

        with patch("pathlib.Path.home", return_value=home):
            result = load_user_token()
            assert result is None

    def test_corrupt_json_returns_none(self, isolated_token_dir):
        """Corrupt token file → None."""
        home, token_file = isolated_token_dir
        token_file.write_text("{bad json")

        with patch("pathlib.Path.home", return_value=home):
            result = load_user_token()
            assert result is None

    def test_unparseable_jwt_still_returned(self, isolated_token_dir):
        """Opaque token that isn't a JWT is still returned (fallback to downstream)."""
        home, token_file = isolated_token_dir
        # Two-part string, not a real JWT, but jose.jwt.get_unverified_claims will throw
        opaque = "opaque_token_value"
        token_file.write_text(json.dumps({"access_token": opaque}))

        with patch("pathlib.Path.home", return_value=home):
            result = load_user_token()
            assert result == opaque
