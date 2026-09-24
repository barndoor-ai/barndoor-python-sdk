"""Retry semantics.

Every case here is one the SDK has to get right on a real deploy: the rule that
decides whether a failed write is repeated is the difference between a retry and
a duplicate charge.
"""

from __future__ import annotations

import httpx2 as httpx
import pytest

from barndoor.lib.http import RetryOptions, _retry_after_seconds, create_async_client


class _Counting(httpx.AsyncBaseTransport):
    def __init__(self, status: int = 503, headers: dict | None = None, raises: bool = False):
        self.attempts = 0
        self._status = status
        self._headers = headers or {}
        self._raises = raises

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if self._raises:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(self._status, headers=self._headers, request=request)


async def _send(transport, method="GET", retries=3):
    async with create_async_client(RetryOptions(retries=retries, backoff=0.001), transport=transport) as client:
        return await client.request(method, "https://example.invalid/x")


async def test_a_retryable_status_is_retried_up_to_the_limit():
    t = _Counting(503)
    await _send(t)
    assert t.attempts == 4, "one attempt plus three retries"


async def test_retries_zero_disables_retrying():
    t = _Counting(503)
    await _send(t, retries=0)
    assert t.attempts == 1


@pytest.mark.parametrize("status", [501, 505])
async def test_statuses_the_server_will_refuse_identically_are_not_retried(status):
    """The server understood the request. Repeating it changes nothing."""
    t = _Counting(status)
    await _send(t)
    assert t.attempts == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_transient_statuses_are_retried(status):
    t = _Counting(status)
    await _send(t)
    assert t.attempts == 4


@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_non_idempotent_methods_are_never_retried(method):
    """A 502 does not say whether the write landed.

    A gateway can time out waiting for a response to work it already committed,
    so retrying risks a duplicate. The SDK this replaces retried every method,
    which was a latent double-write on any 5xx during a create.
    """
    t = _Counting(503)
    await _send(t, method=method)
    assert t.attempts == 1


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "PUT", "DELETE"])
async def test_idempotent_methods_are_retried(method):
    t = _Counting(503)
    await _send(t, method=method)
    assert t.attempts == 4


async def test_a_transport_error_is_retried_for_idempotent_methods():
    t = _Counting(raises=True)
    with pytest.raises(httpx.ConnectError):
        await _send(t)
    assert t.attempts == 4


async def test_a_transport_error_is_not_retried_for_a_write():
    t = _Counting(raises=True)
    with pytest.raises(httpx.ConnectError):
        await _send(t, method="POST")
    assert t.attempts == 1


def test_retry_after_accepts_seconds():
    r = httpx.Response(429, headers={"retry-after": "2"})
    assert _retry_after_seconds(r) == pytest.approx(2.0)


def test_retry_after_accepts_an_http_date():
    """Both forms are legal, and servers use both."""
    r = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2099 07:28:00 GMT"})
    assert _retry_after_seconds(r) > 0


def test_retry_after_absent_is_none():
    assert _retry_after_seconds(httpx.Response(429)) is None


def test_a_past_retry_after_date_does_not_produce_a_negative_sleep():
    r = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 1999 07:28:00 GMT"})
    assert _retry_after_seconds(r) == 0.0
