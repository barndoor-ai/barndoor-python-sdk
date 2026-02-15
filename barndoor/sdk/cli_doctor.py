"""Diagnostic command for the Barndoor SDK.

``barndoor doctor`` performs a series of connectivity and configuration
checks so users (and support) can quickly identify what's broken.

Entry point:  ``barndoor doctor``  (registered in pyproject.toml)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx
from jose import jwt

from .auth_store import TOKEN_FILE
from .config import AUTH_CONFIG, BarndoorConfig, get_static_config, load_dotenv_for_sdk
from .logging import get_logger

logger = get_logger("doctor")

# ---------------------------------------------------------------------------
# Pretty helpers
# ---------------------------------------------------------------------------

_PASS = "\u2705"  # ✅
_FAIL = "\u274c"  # ❌
_WARN = "\u26a0\ufe0f"  # ⚠️


def _ok(msg: str) -> None:
    print(f"  {_PASS}  {msg}")


def _fail(msg: str, *, fix: str | None = None) -> None:
    print(f"  {_FAIL}  {msg}")
    if fix:
        print(f"        ↳ Fix: {fix}")


def _warn(msg: str, *, fix: str | None = None) -> None:
    print(f"  {_WARN}  {msg}")
    if fix:
        print(f"        ↳ {fix}")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_config(cfg: BarndoorConfig) -> None:
    """Check 1: Config resolution."""
    print("\n── Config resolution ──")
    _ok(f"Environment: {cfg.environment}")
    _ok(f"Auth issuer: {cfg.auth_issuer}")
    _ok(f"Base URL template: {cfg.base_url}")

    if cfg.environment not in AUTH_CONFIG:
        _warn(
            f"Environment '{cfg.environment}' is not a built-in environment",
            fix="Check BARNDOOR_ENV or MODE — valid values: " + ", ".join(sorted(AUTH_CONFIG)),
        )


def check_credentials() -> str | None:
    """Check 2: Available credentials. Returns the auth method detected."""
    print("\n── Credentials ──")
    api_key = os.getenv("BARNDOOR_API_KEY", "").strip()
    client_id = os.getenv("AGENT_CLIENT_ID", "") or os.getenv("AUTH_CLIENT_ID", "")
    client_secret = os.getenv("AGENT_CLIENT_SECRET", "") or os.getenv("AUTH_CLIENT_SECRET", "")

    method: str | None = None

    if api_key:
        if api_key.startswith("bdai_"):
            _ok(f"BARNDOOR_API_KEY set (bdai_…{api_key[-4:]})")
            method = "api_key"
        else:
            _fail(
                "BARNDOOR_API_KEY is set but doesn't start with 'bdai_'",
                fix="API keys should start with 'bdai_'. Regenerate in the dashboard.",
            )
    else:
        _warn(
            "BARNDOOR_API_KEY not set",
            fix="Set BARNDOOR_API_KEY for the simplest auth path.",
        )

    if client_id and client_secret:
        _ok(f"AGENT_CLIENT_ID set ({client_id[:8]}…)")
        _ok("AGENT_CLIENT_SECRET set (****)")
        if not method:
            method = "oidc"
    elif client_id or client_secret:
        _fail(
            "Only one of AGENT_CLIENT_ID / AGENT_CLIENT_SECRET is set",
            fix="Both must be set for OIDC authentication.",
        )
    else:
        if not method:
            _warn(
                "No OIDC client credentials set",
                fix="Set AGENT_CLIENT_ID and AGENT_CLIENT_SECRET for OIDC auth.",
            )

    if not method:
        _fail(
            "No usable credential found",
            fix="Set BARNDOOR_API_KEY (simplest) or AGENT_CLIENT_ID + AGENT_CLIENT_SECRET.",
        )

    return method


def check_oidc_discovery(cfg: BarndoorConfig) -> bool:
    """Check 3: OIDC discovery endpoint reachability."""
    print("\n── OIDC discovery ──")
    issuer = cfg.auth_issuer.rstrip("/")
    discovery_url = f"{issuer}/.well-known/openid-configuration"

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(discovery_url)
            resp.raise_for_status()
            data = resp.json()
            _ok(f"OIDC discovery OK — {discovery_url}")
            # Verify key fields
            for field in ("token_endpoint", "authorization_endpoint", "jwks_uri"):
                if field in data:
                    _ok(f"  {field}: {data[field]}")
                else:
                    _warn(f"  {field} missing from discovery response")
            return True
    except httpx.ConnectError:
        _fail(
            f"Cannot reach {discovery_url}",
            fix="Check your network or VPN. The issuer may be unreachable.",
        )
    except httpx.HTTPStatusError as exc:
        _fail(
            f"OIDC discovery returned HTTP {exc.response.status_code}",
            fix="The issuer URL may be misconfigured. Check BARNDOOR_ENV.",
        )
    except Exception as exc:
        _fail(f"OIDC discovery failed: {exc}")
    return False


def check_cached_token(cfg: BarndoorConfig) -> str | None:
    """Check 4: Cached token status. Returns the access_token if usable."""
    print("\n── Cached token ──")
    token_path = TOKEN_FILE

    if not token_path.exists():
        _warn(
            f"{token_path} does not exist",
            fix="Run 'barndoor-login' to create a cached token, or use BARNDOOR_API_KEY instead.",
        )
        return None

    try:
        with open(token_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        _fail(
            f"Cannot read {token_path}: {exc}",
            fix="Delete the file and re-run 'barndoor-login'.",
        )
        return None

    access_token = data.get("access_token")
    if not access_token:
        _fail(
            "Token file exists but has no access_token",
            fix="Delete the file and re-run 'barndoor-login'.",
        )
        return None

    _ok(f"Token file found: {token_path}")

    # Decode claims (unverified) for diagnostics
    try:
        claims = jwt.get_unverified_claims(access_token)
    except Exception:
        _warn("Could not decode JWT claims (token may be opaque)")
        return access_token

    # Expiry check
    exp = claims.get("exp")
    if exp:
        remaining = exp - time.time()
        if remaining <= 0:
            _fail(
                f"Token expired {int(-remaining)}s ago",
                fix="Run 'barndoor-login' to get a fresh token.",
            )
        elif remaining < 300:
            _warn(f"Token expires in {int(remaining)}s (< 5 min)")
        else:
            _ok(f"Token valid for {int(remaining / 60)} more minutes")
    else:
        _warn("Token has no 'exp' claim")

    # Issuer mismatch
    token_issuer = (claims.get("iss") or "").rstrip("/")
    config_issuer = cfg.auth_issuer.rstrip("/")
    if token_issuer and config_issuer:
        if token_issuer == config_issuer:
            _ok(f"Issuer matches config: {token_issuer}")
        else:
            _fail(
                f"Issuer MISMATCH — token: {token_issuer}, config: {config_issuer}",
                fix="Cached token is from a different environment. "
                "Delete ~/.barndoor/token.json and re-login, "
                "or check BARNDOOR_ENV.",
            )

    # Refresh token
    if data.get("refresh_token"):
        _ok("Refresh token present")
    else:
        _warn(
            "No refresh token cached",
            fix="Token cannot be auto-refreshed. Re-login when it expires.",
        )

    return access_token


async def check_api_connectivity(
    cfg: BarndoorConfig,
    credential: str,
    auth_method: str | None,
) -> None:
    """Check 5: Hit /api/servers with the available credential."""
    print("\n── API connectivity ──")

    # Resolve base URL — if it still has {org_slug} we can't hit it
    base_url = cfg.base_url
    if "{org_slug}" in base_url:
        # Try to extract org from token
        if auth_method != "api_key":
            try:
                claims = jwt.get_unverified_claims(credential)
                org = None
                if user_claims := claims.get("user"):
                    org = user_claims.get("organization_name")
                if not org:
                    org = claims.get("organization_name")
                if org:
                    base_url = base_url.format(org_slug=org)
            except Exception:
                pass

        if "{org_slug}" in base_url:
            _warn(
                f"Base URL still contains template: {base_url}",
                fix="Set BARNDOOR_URL explicitly or ensure your token contains organization_name.",
            )
            return

    url = f"{base_url.rstrip('/')}/api/servers"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {credential}"},
            )
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, list):
                count = len(body)
            else:
                count = len(body.get("data", []))
            _ok(f"GET {url} → 200 OK ({count} server(s) on first page)")
        elif resp.status_code == 401:
            _fail(
                f"GET {url} → 401 Unauthorized",
                fix="Your credential may be invalid or expired. "
                "Try re-login or check your API key.",
            )
        else:
            _fail(f"GET {url} → HTTP {resp.status_code}")
    except httpx.ConnectError:
        _fail(
            f"Cannot reach {url}",
            fix="Check your network, VPN, or BARNDOOR_URL.",
        )
    except Exception as exc:
        _fail(f"API request failed: {exc}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def _run_doctor() -> int:
    """Run all diagnostic checks. Returns 0 on success, 1 if any critical check failed."""
    load_dotenv_for_sdk()

    print("🩺 Barndoor Doctor")
    print("=" * 50)

    cfg = get_static_config()

    # 1. Config
    check_config(cfg)

    # 2. Credentials
    auth_method = check_credentials()

    # 3. OIDC discovery
    check_oidc_discovery(cfg)

    # 4. Cached token
    cached_token = check_cached_token(cfg)

    # 5. API connectivity — pick the best available credential
    credential: str | None = None
    if auth_method == "api_key":
        credential = os.getenv("BARNDOOR_API_KEY", "").strip()
    elif cached_token:
        credential = cached_token

    if credential:
        await check_api_connectivity(cfg, credential, auth_method)
    else:
        print("\n── API connectivity ──")
        _fail(
            "Skipped — no usable credential for API check",
            fix="Set BARNDOOR_API_KEY or run 'barndoor-login' first.",
        )

    print("\n" + "=" * 50)
    print("Done. Review any ❌ items above.\n")

    return 0


def cli_main() -> None:
    """Entry point for ``barndoor doctor``."""
    try:
        rc = asyncio.run(_run_doctor())
    except KeyboardInterrupt:
        print("\nAborted.")
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    cli_main()
