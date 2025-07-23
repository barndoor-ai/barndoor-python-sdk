"""Example demonstrating token validation functionality in the Barndoor SDK."""

import asyncio
import os

from pathlib import Path

from barndoor.sdk import BarndoorSDK
from barndoor.sdk.auth_store import clear_cached_token, is_token_active, validate_token


async def main() -> None:
    """Demonstrate token validation functionality."""

    # Load environment variables
    api = os.getenv("BARNDOOR_API", "http://localhost:8003")

    print("=== Barndoor SDK Token Validation Example ===\n")

    # 1. Check if there's a cached token
    print("1. Checking for cached token...")
    from barndoor.sdk.auth_store import load_user_token

    cached_token = load_user_token()

    if cached_token:
        print(f"   ✓ Found cached token: {cached_token[:20]}...")
    else:
        print("   ✗ No cached token found")
        print("   Run 'barndoor-login' to obtain a token first")
        return

    # 2. Validate the token using the auth_store function
    print("\n2. Validating token using auth_store...")
    is_active = await is_token_active(api)
    print(f"   Token is active: {is_active}")

    # 3. Get detailed validation info
    print("\n3. Getting detailed validation info...")
    result = await validate_token(cached_token, api)
    print(f"   Valid: {result['valid']}")
    print(f"   Error: {result['error']}")
    if result["user_info"]:
        print(f"   User info: {result['user_info']}")

    # 4. Test SDK initialization with validation
    print("\n4. Testing SDK initialization with token validation...")
    try:
        # Initialize SDK with validation enabled (default)
        # Disable auto-validation
        sdk = BarndoorSDK(api, validate_token_on_init=False)

        # Manually validate token
        print("   Validating token through SDK...")
        is_valid = await sdk.validate_cached_token()
        print(f"   Token is valid: {is_valid}")

        if is_valid:
            # Test an API call
            print("   Testing API call...")
            servers = await sdk.list_servers()
            print(f"   ✓ Successfully retrieved {len(servers)} servers")

            # Show server info
            for server in servers:
                print(
                    f"     - {server.slug} ({server.provider}) -> {server.connection_status}"
                )
        else:
            print("   ✗ Token validation failed")

    except ValueError as e:
        print(f"   ✗ SDK initialization failed: {e}")
    except Exception as e:
        print(f"   ✗ Unexpected error: {e}")

    # 5. Demonstrate token clearing
    print("\n5. Token management...")
    print("   Current token status:", "Active" if is_active else "Inactive")

    # Uncomment the following lines to test token clearing:
    # print("   Clearing cached token...")
    # clear_cached_token()
    # print("   ✓ Token cleared")

    print("\n=== Example completed ===")


if __name__ == "__main__":
    asyncio.run(main())
