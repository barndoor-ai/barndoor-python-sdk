"""Exception classes for the Barndoor SDK.

This module defines custom exceptions that can be raised by SDK operations,
providing more specific error handling than generic exceptions.
"""

from __future__ import annotations


class BarndoorError(Exception):
    """Base exception for all Barndoor SDK errors.

    All custom exceptions in the SDK inherit from this base class,
    allowing applications to catch all SDK-specific errors with a
    single except clause if desired.
    """

    pass


class HTTPError(BarndoorError):
    """Raised when an HTTP request returns an error status code.

    This exception provides access to both the HTTP status code and
    the response body, allowing for detailed error handling based on
    the specific API error.

    Attributes
    ----------
    status_code : int
        The HTTP status code (e.g., 400, 401, 404, 500)
    body : str
        The response body, typically containing error details
    """

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


class ConnectionError(BarndoorError):
    """Raised when unable to connect to the Barndoor API.

    This typically indicates network issues, incorrect API URL,
    or the API service being unavailable.

    Attributes
    ----------
    url : str
        The URL that failed to connect
    original_error : Exception
        The underlying exception that caused the connection failure
    """

    def __init__(self, url: str, original_error: Exception):
        self.url = url
        self.original_error = original_error
        super().__init__(f"Failed to connect to {url}: {original_error}")
