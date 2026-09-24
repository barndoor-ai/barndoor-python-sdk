"""Assembling a client.

The generated ``Configuration`` takes ``access_token`` as a plain string, but
``auth_settings()`` reads the attribute every time a request is signed. So a
subclass whose ``access_token`` is a property can refresh transparently, with no
hook and no wrapper around every API method — the same result the TypeScript SDK
gets by passing a callable.
"""

from __future__ import annotations

import functools
import inspect
import uuid

from dataclasses import dataclass
from typing import Any

# httpx2: the SDK's single http stack. See barndoor/lib/http.py.
import httpx2 as httpx

from barndoor.api.dlp_api import DlpApi
from barndoor.api.identity_api import IdentityApi
from barndoor.api.llm_gateway_api import LlmGatewayApi
from barndoor.api.notification_api import NotificationApi
from barndoor.api.policy_api import PolicyApi
from barndoor.api.registry_api import RegistryApi
from barndoor.api.system_management_api import SystemManagementApi
from barndoor.api_client import ApiClient
from barndoor.configuration import Configuration
from barndoor.lib.auth import ClientCredentialsOptions, TokenProvider, client_credentials, static_token
from barndoor.lib.config import Environment
from barndoor.lib.http import RetryOptions, create_async_client


class _NoStaticToken(Configuration):
    """A ``Configuration`` that never carries a token of its own.

    ``auth_settings()`` emits an ``Authorization`` header only when
    ``access_token`` is set. Leaving it unset means the generated client builds
    the request without one, and :func:`_install_auth` attaches the current
    token at call time — which is the only point where an async provider can be
    awaited.

    The alternative, a property that resolves the provider synchronously, needs
    a thread and a second event loop on every cold start and can only ever prime
    once. Refresh has to happen per request, because that is when a token turns
    out to have expired.
    """


@dataclass
class BarndoorClient:
    """One namespace per service, plus the pieces they share."""

    registry: RegistryApi
    policy: PolicyApi
    identity: IdentityApi
    notification: NotificationApi
    dlp: DlpApi
    llm_gateway: LlmGatewayApi
    system_management: SystemManagementApi
    #: The underlying configuration, for constructing an API class this does
    #: not expose.
    configuration: Configuration
    api_client: ApiClient

    async def aclose(self) -> None:
        """Release the connection pool.

        Explicit because the generated ``ApiClient`` owns an
        ``httpx.AsyncClient``, and leaving it to garbage collection produces the
        "Unclosed client session" warning at interpreter shutdown.
        """
        await self.api_client.close()

    async def __aenter__(self) -> "BarndoorClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


def _coerce_uuid_arguments(api: Any) -> None:
    """Let a caller pass back the UUIDs this SDK hands them.

    The spec types 68 response properties as `format: uuid` but 11 path
    parameters as plain `string`, so `list_policies()` returns `id` as a
    `UUID` and `get_policy()` then rejects it:

        Input should be a valid string [input_type=UUID]

    The natural chaining — take an id from a list, fetch the detail — fails,
    and only on the endpoints that happen to be typed inconsistently. The other
    path parameters ARE declared `format: uuid`, so they generate a `UUID`
    annotation and work.

    Coercing UUID to str is safe for both shapes: a `StrictStr` parameter
    requires it, and a `UUID` parameter accepts a well-formed string because
    pydantic parses it. Nothing else is touched — this converts one type, not
    "whatever looks close".

    The real fix is `format: uuid` on those 11 parameters, which means changing
    the FastAPI annotations in registry-service and policy-service. That alters
    what those endpoints reject and is not the SDK's call to make; see
    sdk/README.md.
    """
    for name in dir(api):
        if name.startswith("_"):
            continue
        method = getattr(api, name)
        if not inspect.iscoroutinefunction(method):
            continue
        setattr(api, name, _uuid_coercing(method))


def _uuid_coercing(method: Any) -> Any:
    @functools.wraps(method)
    async def call(*args: Any, **kwargs: Any) -> Any:
        args = tuple(str(a) if isinstance(a, uuid.UUID) else a for a in args)
        kwargs = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in kwargs.items()}
        return await method(*args, **kwargs)

    return call


def _resolve_auth(
    auth: str | ClientCredentialsOptions | TokenProvider,
    env: Environment | None,
) -> TokenProvider:
    if isinstance(auth, str):
        return static_token(auth)
    if isinstance(auth, ClientCredentialsOptions):
        # Credentials inherit the environment's issuer, so pointing at dev
        # cannot leave the API on dev while the token comes from production.
        if env is not None and auth.issuer is None:
            auth = ClientCredentialsOptions(
                client_id=auth.client_id,
                client_secret=auth.client_secret,
                issuer=env.issuer,
                scope=auth.scope,
                transport=auth.transport,
            )
        return client_credentials(auth)
    return auth


def create_client(
    auth: str | ClientCredentialsOptions | TokenProvider,
    *,
    env: Environment | None = None,
    retry: RetryOptions | None = None,
    headers: dict[str, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> BarndoorClient:
    """Assemble a client.

    Synchronous, and nothing here touches the network: OIDC discovery and the
    first token exchange are deferred to the first request, so constructing a
    client cannot fail because an identity provider is briefly unreachable.

    Retries are on unless switched off with ``retry=RetryOptions(retries=0)``.
    Wiring the transport by hand is easy to forget, and forgetting it fails
    invisibly — the client simply becomes less resilient, with nothing to notice
    until a deploy produces a burst of 503s.
    """
    provider = _resolve_auth(auth, env)

    configuration = _NoStaticToken()
    if env is not None:
        configuration.host = env.base_url

    api_client = ApiClient(configuration)
    if headers:
        for name, value in headers.items():
            api_client.set_default_header(name, value)

    # The generated REST client builds an httpx client lazily and only if one is
    # not already set, which is the injection point for retries.
    api_client.rest_client.pool_manager = http_client or create_async_client(retry)

    client = BarndoorClient(
        registry=RegistryApi(api_client),
        policy=PolicyApi(api_client),
        identity=IdentityApi(api_client),
        notification=NotificationApi(api_client),
        dlp=DlpApi(api_client),
        llm_gateway=LlmGatewayApi(api_client),
        system_management=SystemManagementApi(api_client),
        configuration=configuration,
        api_client=api_client,
    )

    _install_auth(api_client, provider)
    for namespace in (
        client.registry,
        client.policy,
        client.identity,
        client.notification,
        client.dlp,
        client.llm_gateway,
        client.system_management,
    ):
        _coerce_uuid_arguments(namespace)
    return client


def _install_auth(api_client: ApiClient, provider: TokenProvider) -> None:
    """Attach the current token to every request.

    ``call_api`` is the one async point that still has the header dict in hand,
    so it is where an async provider can be awaited. Doing it per request rather
    than once at construction is what makes refresh work: a provider caches
    internally and returns immediately while its token is good, and exchanges a
    new one the moment it is not.

    Wrapping rather than subclassing ``ApiClient`` because the generated API
    classes are handed an instance, not a class.
    """
    inner = api_client.call_api

    async def call_api(
        method: str,
        url: str,
        header_params: dict[str, str] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        headers = dict(header_params or {})
        # A caller's explicit Authorization wins: they are overriding on
        # purpose, and silently replacing it would be the surprise.
        headers.setdefault("Authorization", f"Bearer {await provider()}")
        return await inner(method, url, headers, *args, **kwargs)

    api_client.call_api = call_api  # type: ignore[method-assign]
    # Published so the MCP client can borrow the same provider: one login
    # serves both protocols, and a refresh made for one is seen by the other.
    api_client._barndoor_token_provider = provider  # noqa: SLF001
