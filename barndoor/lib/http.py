"""The transport every request runs through.

The generated ``RESTClientObject`` creates an ``httpx.AsyncClient`` lazily and
only if one is not already set, so injecting a client here is the single choke
point for retries — the equivalent of ``Configuration.fetchApi`` in the
TypeScript SDK, and for the same reason: a response hook would see each attempt,
and an error hook cannot retry a 503 that arrived successfully.

Retries live in an ``httpx`` transport rather than a loop around the call so a
caller who brings their own client keeps them, and so streaming and connection
pooling behave the way httpx intends.
"""

from __future__ import annotations

import asyncio
import email.utils
import random
import time

from dataclasses import dataclass

# httpx2: the SDK's single http stack. authlib and mcp are built on it, and
# templates/httpx/rest.mustache aliases the generated client onto it too, so a
# transport made here is accepted everywhere and `except httpx.HTTPError` covers
# the whole SDK.
import httpx2 as httpx


#: Statuses worth another attempt: 5xx generally, plus 429. 501 and 505 are
#: excluded — the server understood the request and will refuse it identically
#: next time.
def _is_retryable_status(status: int) -> bool:
    if status == 429:
        return True
    return status >= 500 and status not in (501, 505)


#: Only idempotent methods are retried.
#:
#: A 502 or 504 does not say whether the request reached the application — a
#: gateway can time out waiting for a response to work it already committed. So
#: retrying a POST risks a duplicate write, and silently doing that is worse
#: than surfacing the error. The SDK this replaces retried every method, which
#: was a latent double-write on any 5xx during a create.
_IDEMPOTENT = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


@dataclass(frozen=True)
class RetryOptions:
    """How hard to try. ``retries=0`` disables retrying."""

    #: Attempts after the first.
    retries: int = 3
    #: Per-attempt timeout, seconds.
    timeout: float = 30.0
    #: Base for exponential backoff, seconds.
    backoff: float = 0.25


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """``Retry-After`` is either seconds or an HTTP date; both are legal."""
    header = response.headers.get("retry-after")
    if not header:
        return None
    try:
        return max(0.0, float(header))
    except ValueError:
        pass
    parsed = email.utils.parsedate_to_datetime(header)
    if parsed is None:
        return None
    return max(0.0, parsed.timestamp() - time.time())


class RetryTransport(httpx.AsyncBaseTransport):
    """Wraps a transport and retries what is safe to retry."""

    def __init__(
        self,
        next_transport: httpx.AsyncBaseTransport,
        options: RetryOptions | None = None,
    ) -> None:
        self._next = next_transport
        self._options = options or RetryOptions()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        opts = self._options
        idempotent = request.method.upper() in _IDEMPOTENT

        for attempt in range(opts.retries + 1):
            last = attempt >= opts.retries
            try:
                response = await self._next.handle_async_request(request)
            except httpx.HTTPError:
                # A transport error says nothing about whether the request was
                # applied, so the same idempotency rule governs it.
                if last or not idempotent:
                    raise
                await asyncio.sleep(self._delay(attempt))
                continue

            if last or not idempotent or not _is_retryable_status(response.status_code):
                return response

            # The body is never read on a retried response, so release it rather
            # than leaking the connection.
            await response.aclose()
            await asyncio.sleep(_retry_after_seconds(response) or self._delay(attempt))

        raise AssertionError("unreachable: the loop returns or raises on its last attempt")

    def _delay(self, attempt: int) -> float:
        """Exponential backoff with jitter.

        Jittered because every client of a service that just returned 503 would
        otherwise come back in lockstep, which is how a recovering service gets
        knocked over again.
        """
        return self._options.backoff * (2**attempt) * (0.5 + random.random())  # noqa: S311

    async def aclose(self) -> None:
        await self._next.aclose()


def create_async_client(
    options: RetryOptions | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` that retries.

    ``transport`` exists for tests and for a caller who needs their own
    connection behaviour underneath the retrying.
    """
    opts = options or RetryOptions()
    base = transport or httpx.AsyncHTTPTransport()
    return httpx.AsyncClient(
        transport=RetryTransport(base, opts) if opts.retries else base,
        timeout=httpx.Timeout(opts.timeout),
        trust_env=True,
    )
