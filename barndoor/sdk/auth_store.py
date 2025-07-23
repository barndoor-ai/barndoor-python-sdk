"""Token storage and validation for the Barndoor SDK.

This module handles persistent storage of user authentication tokens
and provides validation utilities. Tokens are stored in a platform-specific
location for security and convenience.
"""

import json
import os

from pathlib import Path

import httpx


def _get_token_path() -> Path:
    """Get the platform-specific path for storing the authentication token.

    Returns
    -------
    Path
        Path to the token file

    Notes
    -----
    Token locations by platform:
    - Linux/Mac: ~/.barndoor/token.json
    - Windows: %USERPROFILE%\\.barndoor\\token.json
    """
    home = Path.home()
    barndoor_dir = home / ".barndoor"
    return barndoor_dir / "token.json"


def save_user_token(token: str) -> None:
    """Save a user authentication token to persistent storage.

    Stores the token in a JSON file in the user's home directory.
    Creates the directory if it doesn't exist.

    Parameters
    ----------
    token : str
        The JWT token to save

    Notes
    -----
    The token is stored with restricted permissions (600) on Unix-like
    systems for security.
    """
    token_path = _get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    # Write token with restricted permissions
    with open(token_path, "w") as f:
        json.dump({"token": token}, f)

    # Set file permissions to 600 (owner read/write only) on Unix
    if os.name != "nt":  # Not Windows
        os.chmod(token_path, 0o600)


def load_user_token() -> str | None:
    """Load a previously saved user authentication token.

    Returns
    -------
    str or None
        The saved token if it exists, None otherwise

    Notes
    -----
    Returns None if the token file doesn't exist or is invalid JSON.
    Does not validate whether the token is still valid - use
    validate_token() or is_token_active() for that.
    """
    token_path = _get_token_path()
    if not token_path.exists():
        return None

    try:
        with open(token_path, "r") as f:
            data = json.load(f)
            return data.get("token")
    except (json.JSONDecodeError, KeyError):
        return None


def clear_cached_token() -> None:
    """Remove the saved authentication token.

    Deletes the token file if it exists. Safe to call even if no
    token is currently saved.
    """
    token_path = _get_token_path()
    if token_path.exists():
        token_path.unlink()


async def validate_token(token: str, api_base_url: str) -> dict[str, bool]:
    """Validate a token against the Barndoor API.

    Makes a request to the /identity/token endpoint to check if the
    provided token is still valid.

    Parameters
    ----------
    token : str
        The JWT token to validate
    api_base_url : str
        Base URL of the Barndoor API

    Returns
    -------
    dict[str, bool]
        Dictionary with 'valid' key indicating token validity

    Raises
    ------
    httpx.HTTPError
        If the validation request fails
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{api_base_url}/identity/token",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()


async def is_token_active(api_base_url: str) -> bool:
    """Check if the currently saved token is valid.

    Convenience function that loads the saved token and validates it
    against the API.

    Parameters
    ----------
    api_base_url : str
        Base URL of the Barndoor API

    Returns
    -------
    bool
        True if a saved token exists and is valid, False otherwise

    Notes
    -----
    Returns False if no token is saved or if the validation request
    fails for any reason (network error, invalid token, etc).
    """
    token = load_user_token()
    if not token:
        return False

    try:
        result = await validate_token(token, api_base_url)
        return result.get("valid", False)
    except Exception:
        # Any error means the token is not active
        return False
