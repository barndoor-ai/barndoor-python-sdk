#!/usr/bin/env python3
"""Simple CLI utility for Barndoor token management."""

import argparse
import asyncio
import os
import sys

from pathlib import Path

from barndoor.sdk.auth_store import (
    clear_cached_token,
    is_token_active,
    load_user_token,
    save_user_token,
    validate_token,
)


async def check_token_status(api_url: str) -> None:
    """Check the status of the cached token."""
    print("=== Token Status Check ===")

    token = load_user_token()
    if not token:
        print("✗ No cached token found")
        return

    print(f"✓ Found cached token: {token[:20]}...")

    # Check if token is active
    is_active = await is_token_active(api_url)
    print(f"Token is active: {'✓ Yes' if is_active else '✗ No'}")

    # Get detailed validation info
    result = await validate_token(token, api_url)
    print(f"Validation result: {'✓ Valid' if result['valid'] else '✗ Invalid'}")
    if result["error"]:
        print(f"Error: {result['error']}")


async def validate_token_cli(api_url: str) -> None:
    """Validate the current token and show detailed info."""
    print("=== Token Validation ===")

    token = load_user_token()
    if not token:
        print("✗ No cached token found")
        return

    result = await validate_token(token, api_url)

    print(f"Valid: {'✓ Yes' if result['valid'] else '✗ No'}")
    print(f"Error: {result['error'] or 'None'}")
    if result["user_info"]:
        print(f"User info: {result['user_info']}")


def clear_token() -> None:
    """Clear the cached token."""
    print("=== Clearing Cached Token ===")

    if load_user_token():
        clear_cached_token()
        print("✓ Token cleared successfully")
    else:
        print("ℹ No cached token to clear")


def save_token_cli(token: str) -> None:
    """Save a token to the cache."""
    print("=== Saving Token ===")

    if not token:
        print("✗ No token provided")
        return

    save_user_token(token)
    print("✓ Token saved successfully")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Barndoor Token Management CLI")
    parser.add_argument(
        "--api-url", default="http://localhost:8003", help="Barndoor API base URL"
    )
    parser.add_argument(
        "--action",
        choices=["status", "validate", "clear", "save"],
        default="status",
        help="Action to perform",
    )
    parser.add_argument("--token", help="Token to save (for save action)")

    args = parser.parse_args()

    try:
        if args.action == "status":
            asyncio.run(check_token_status(args.api_url))
        elif args.action == "validate":
            asyncio.run(validate_token_cli(args.api_url))
        elif args.action == "clear":
            clear_token()
        elif args.action == "save":
            save_token_cli(args.token)
        else:
            print(f"Unknown action: {args.action}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
