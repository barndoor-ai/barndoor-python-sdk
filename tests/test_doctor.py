"""Tests for barndoor doctor CLI diagnostic checks."""

import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from barndoor.sdk.cli_doctor import (
    check_cached_token,
    check_config,
    check_credentials,
    check_oidc_discovery,
)
from barndoor.sdk.config import BarndoorConfig


def _make_jwt(claims: dict) -> str:
    """Build a fake (unsigned) JWT with given claims."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"typ": "JWT", "alg": "HS256"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


@pytest.fixture
def default_config():
    """Production BarndoorConfig with defaults."""
    return BarndoorConfig()


@pytest.fixture
def token_dir():
    """Temp directory with a .barndoor/token.json for cached-token checks."""
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        bd = home / ".barndoor"
        bd.mkdir()
        yield home, bd / "token.json"


# ── check_config ─────────────────────────────────────────────────────────


class TestCheckConfig:
    def test_default_production(self, capsys, default_config):
        check_config(default_config)
        out = capsys.readouterr().out
        assert "production" in out
        assert default_config.auth_issuer in out

    def test_unknown_env_warns(self, capsys):
        cfg = BarndoorConfig(environment="custom-env")
        check_config(cfg)
        out = capsys.readouterr().out
        assert "not a built-in environment" in out


# ── check_credentials ────────────────────────────────────────────────────


class TestCheckCredentials:
    def test_api_key_detected(self, capsys):
        with patch.dict("os.environ", {"BARNDOOR_API_KEY": "bdai_testkey1234"}, clear=True):
            method = check_credentials()
        assert method == "api_key"
        assert "BARNDOOR_API_KEY set" in capsys.readouterr().out

    def test_api_key_bad_prefix(self, capsys):
        with patch.dict("os.environ", {"BARNDOOR_API_KEY": "sk_bad"}, clear=True):
            method = check_credentials()
        assert method is None
        assert "doesn't start with 'bdai_'" in capsys.readouterr().out

    def test_oidc_creds_detected(self, capsys):
        env = {"AGENT_CLIENT_ID": "cid", "AGENT_CLIENT_SECRET": "csec"}
        with patch.dict("os.environ", env, clear=True):
            method = check_credentials()
        assert method == "oidc"

    def test_no_creds(self, capsys):
        with patch.dict("os.environ", {}, clear=True):
            method = check_credentials()
        assert method is None
        assert "No usable credential found" in capsys.readouterr().out

    def test_partial_oidc_warns(self, capsys):
        with patch.dict("os.environ", {"AGENT_CLIENT_ID": "cid"}, clear=True):
            method = check_credentials()
        assert method is None
        assert "Only one of" in capsys.readouterr().out


# ── check_oidc_discovery ─────────────────────────────────────────────────


class TestCheckOIDCDiscovery:
    def test_discovery_success(self, capsys, default_config):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "issuer": default_config.auth_issuer,
            "token_endpoint": f"{default_config.auth_issuer}/protocol/openid-connect/token",
            "authorization_endpoint": f"{default_config.auth_issuer}/protocol/openid-connect/auth",
            "jwks_uri": f"{default_config.auth_issuer}/protocol/openid-connect/certs",
        }

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            ok = check_oidc_discovery(default_config)

        assert ok is True
        assert "OIDC discovery OK" in capsys.readouterr().out

    def test_discovery_connect_error(self, capsys, default_config):
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.ConnectError(
                "refused"
            )
            ok = check_oidc_discovery(default_config)

        assert ok is False
        assert "Cannot reach" in capsys.readouterr().out

    def test_discovery_http_error(self, capsys, default_config):
        resp = MagicMock()
        resp.status_code = 404

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = resp
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=resp,
            )
            ok = check_oidc_discovery(default_config)

        assert ok is False
        assert "HTTP 404" in capsys.readouterr().out


# ── check_cached_token ───────────────────────────────────────────────────


class TestCheckCachedToken:
    def test_no_file(self, capsys, default_config, token_dir):
        home, tf = token_dir
        tf.unlink(missing_ok=True)

        with patch("barndoor.sdk.cli_doctor.TOKEN_FILE", tf):
            result = check_cached_token(default_config)

        assert result is None
        assert "does not exist" in capsys.readouterr().out

    def test_valid_token(self, capsys, default_config, token_dir):
        home, tf = token_dir
        issuer = default_config.auth_issuer
        access_token = _make_jwt({"sub": "u", "iss": issuer, "exp": 9999999999})
        tf.write_text(
            json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": "rt",
                }
            )
        )

        with patch("barndoor.sdk.cli_doctor.TOKEN_FILE", tf):
            result = check_cached_token(default_config)

        assert result == access_token
        out = capsys.readouterr().out
        assert "Token file found" in out
        assert "Issuer matches" in out
        assert "Refresh token present" in out

    def test_expired_token(self, capsys, default_config, token_dir):
        home, tf = token_dir
        access_token = _make_jwt(
            {
                "sub": "u",
                "iss": default_config.auth_issuer,
                "exp": 1000000000,  # long expired
            }
        )
        tf.write_text(json.dumps({"access_token": access_token}))

        with patch("barndoor.sdk.cli_doctor.TOKEN_FILE", tf):
            check_cached_token(default_config)

        out = capsys.readouterr().out
        assert "Token expired" in out

    def test_issuer_mismatch(self, capsys, default_config, token_dir):
        home, tf = token_dir
        access_token = _make_jwt(
            {
                "sub": "u",
                "iss": "https://wrong.issuer.com",
                "exp": 9999999999,
            }
        )
        tf.write_text(json.dumps({"access_token": access_token}))

        with patch("barndoor.sdk.cli_doctor.TOKEN_FILE", tf):
            check_cached_token(default_config)

        out = capsys.readouterr().out
        assert "MISMATCH" in out

    def test_corrupt_json(self, capsys, default_config, token_dir):
        home, tf = token_dir
        tf.write_text("{corrupt")

        with patch("barndoor.sdk.cli_doctor.TOKEN_FILE", tf):
            result = check_cached_token(default_config)

        assert result is None
        assert "Cannot read" in capsys.readouterr().out

    def test_no_refresh_token_warns(self, capsys, default_config, token_dir):
        home, tf = token_dir
        access_token = _make_jwt(
            {
                "sub": "u",
                "iss": default_config.auth_issuer,
                "exp": 9999999999,
            }
        )
        tf.write_text(json.dumps({"access_token": access_token}))

        with patch("barndoor.sdk.cli_doctor.TOKEN_FILE", tf):
            check_cached_token(default_config)

        assert "No refresh token" in capsys.readouterr().out
