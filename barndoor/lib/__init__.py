"""The hand-written half of the SDK.

Everything else under ``barndoor/`` is generated from
``docs/api/public-openapi.yaml`` and is not committed — ``make gen-sdk-python``
recreates it. This package holds only what an OpenAPI document cannot describe:
obtaining a token, transport resilience, non-production hosts and the MCP
client.

Re-exported from the package root by ``templates/__init__package.mustache``.
"""

from barndoor.lib.auth import (
    AuthorizationCodeRequest,
    ClientCredentialsOptions,
    TokenProvider,
    client_credentials,
    complete_authorization_code,
    refresh_token,
    start_authorization_code,
    static_token,
)
from barndoor.lib.client import BarndoorClient, create_client
from barndoor.lib.config import DEV, LOCAL, PRODUCTION_ISSUER, Environment, environment_from_env
from barndoor.lib.http import RetryOptions, create_async_client
from barndoor.lib.mcp import McpOptions, mcp_client, mcp_connection_params


__all__ = [
    "DEV",
    "LOCAL",
    "PRODUCTION_ISSUER",
    "AuthorizationCodeRequest",
    "BarndoorClient",
    "ClientCredentialsOptions",
    "Environment",
    "McpOptions",
    "RetryOptions",
    "TokenProvider",
    "client_credentials",
    "complete_authorization_code",
    "create_async_client",
    "create_client",
    "environment_from_env",
    "mcp_client",
    "mcp_connection_params",
    "refresh_token",
    "start_authorization_code",
    "static_token",
]
