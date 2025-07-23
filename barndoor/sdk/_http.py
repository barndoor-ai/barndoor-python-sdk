"""Internal HTTP client wrapper for the Barndoor SDK.

This module provides a thin wrapper around httpx to handle connection
pooling and error handling consistently across the SDK.
"""

from __future__ import annotations

import httpx

from .exceptions import ConnectionError


class HTTPClient:
    """Async HTTP client with connection pooling and error handling.

    This internal class wraps httpx.AsyncClient to provide consistent
    error handling and connection management for all SDK HTTP requests.

    The client is created lazily on first use and reused for all
    subsequent requests to benefit from connection pooling.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an HTTP request with automatic client management.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, etc.)
        url : str
            Full URL to request
        **kwargs
            Additional arguments passed to httpx.AsyncClient.request()

        Returns
        -------
        httpx.Response
            The HTTP response

        Raises
        ------
        ConnectionError
            If unable to connect to the server
        httpx.HTTPStatusError
            If the response has an error status code
        RuntimeError
            For other request failures
        """
        if self._client is None:
            self._client = httpx.AsyncClient()
        try:
            resp = await self._client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ConnectionError(url, exc) from exc
        except Exception as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
