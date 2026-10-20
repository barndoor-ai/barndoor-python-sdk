"""A tool result larger than 1 MiB must reach an ``mcp_client`` caller (BCP-5163).

Barndoor answers ``tools/call`` as ONE server-sent event, so the whole result is
one event. MCP SDK 2 reads that stream with ``httpx2.EventSource``, whose default
``max_event_size`` is 1 MiB, and swallows the ``SSEError`` it raises into
"SSE stream ended without a response". SDK 1 used httpx-sse, which had no
per-event cap; ``mcp_client`` now lifts it (``_lift_sse_event_cap``). These tests run the real ``mcp_client`` -> SDK -> httpx2 stack
against a fake MCP endpoint on a real socket; the 64 KiB case is the control.
"""

from __future__ import annotations

import inspect
import json
import socket
import threading
import time

from collections.abc import Iterator
from types import SimpleNamespace

import httpx2
import mcp.client.sse as sdk_sse
import mcp.client.streamable_http as sdk_streamable_http
import mcp.shared._httpx_utils as sdk_httpx_utils
import pytest
import uvicorn

from barndoor.lib import mcp as barndoor_mcp
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


_TOOL = {"name": "t", "description": "d", "inputSchema": {"type": "object", "properties": {}}}
# Newlines and quotes double on the wire as JSON escapes, as a real CSV export does.
_CSV_ROW = 'id,"name",value\n'


class _FakeMcp:
    """A Barndoor MCP stand-in that answers `tools/call` with `self.text` as one SSE event."""

    def __init__(self) -> None:
        self.text = ""

    async def endpoint(self, request: Request) -> Response:
        if request.method != "POST":
            return Response(status_code=405)
        body = json.loads(await request.body())
        rid = body.get("id")
        method = body.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": body["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-barndoor", "version": "1"},
            }
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": result}, headers={"mcp-session-id": "s1"})
        if rid is None:
            return Response(status_code=202)
        if method == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": {"tools": [_TOOL]}})
        result = {"content": [{"type": "text", "text": self.text}], "isError": False}
        message = json.dumps({"jsonrpc": "2.0", "id": rid, "result": result})
        return Response(f"event: message\r\ndata: {message}\r\n\r\n", media_type="text/event-stream")


@pytest.fixture(scope="module")
def fake_mcp() -> Iterator[tuple[_FakeMcp, str]]:
    fake = _FakeMcp()
    app = Starlette(routes=[Route("/mcp", fake.endpoint, methods=["GET", "POST", "DELETE"])])
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            server.should_exit = True
            sock.close()
            raise RuntimeError("fake MCP server did not start")
        time.sleep(0.01)
    try:
        yield fake, f"http://127.0.0.1:{sock.getsockname()[1]}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("fake MCP server did not stop within 5s")


def _client() -> SimpleNamespace:
    """Just the two attributes `mcp_client` reads off a `create_client()` result."""

    async def token() -> str:
        return "tok"

    return SimpleNamespace(
        configuration=SimpleNamespace(host="http://platform.invalid"),
        api_client=SimpleNamespace(_barndoor_token_provider=token),
    )


@pytest.mark.parametrize("text_bytes", [64 * 1024, 1_900_000])
async def test_a_large_tool_result_reaches_the_caller_intact(fake_mcp, monkeypatch, text_bytes):
    fake, url = fake_mcp
    fake.text = (_CSV_ROW * (text_bytes // len(_CSV_ROW) + 1))[:text_bytes]
    # The organization subdomain (`acme.127.0.0.1`) would not resolve; the URL
    # shape is not what is under test, the transport is.
    monkeypatch.setattr(barndoor_mcp, "_with_organization", lambda base, org: url)

    async with barndoor_mcp.mcp_client(_client(), "acme") as session:
        result = await session.call_tool("t", {})

    assert result.is_error is False
    assert len(result.content) == 1
    assert result.content[0].text == fake.text


def test_the_sdk_still_offers_no_sse_event_size_knob():
    """`mcp_client` rebinds SDK readers only because mcp 2.x cannot be told the cap.

    If this fails, the SDK takes the cap (or httpx2's default changed): pass the
    knob and delete `_lift_sse_event_cap`.
    """
    assert "max_event_size" not in inspect.getsource(sdk_streamable_http)
    assert "max_event_size" not in inspect.getsource(sdk_httpx_utils)
    assert inspect.signature(httpx2.EventSource).parameters["max_event_size"].default == 1024 * 1024


@pytest.fixture
def sdk_readers_reset(monkeypatch):
    """The SDK's own readers for one test; monkeypatch restores the lifted ones after."""
    monkeypatch.setattr(sdk_streamable_http, "EventSource", httpx2.EventSource)
    monkeypatch.setattr(sdk_streamable_http, "sse_within_origin", barndoor_mcp._sdk_sse_within_origin)
    monkeypatch.setattr(sdk_sse, "sse_within_origin", barndoor_mcp._sdk_sse_within_origin)


def test_every_sdk_reader_is_lifted(sdk_readers_reset):
    """POST answers, the GET stream and the legacy SSE transport alike."""
    barndoor_mcp._lift_sse_event_cap(barndoor_mcp.MAX_SSE_EVENT_BYTES)

    assert sdk_streamable_http.EventSource._bd_max_sse_event_bytes == barndoor_mcp.MAX_SSE_EVENT_BYTES
    assert sdk_streamable_http.sse_within_origin is sdk_sse.sse_within_origin
    assert sdk_sse.sse_within_origin is not barndoor_mcp._sdk_sse_within_origin


def test_the_cap_is_only_ever_raised(sdk_readers_reset):
    barndoor_mcp._lift_sse_event_cap(barndoor_mcp.MAX_SSE_EVENT_BYTES)
    lifted = (sdk_streamable_http.EventSource, sdk_streamable_http.sse_within_origin, sdk_sse.sse_within_origin)
    barndoor_mcp._lift_sse_event_cap(1024)

    assert (sdk_streamable_http.EventSource, sdk_streamable_http.sse_within_origin, sdk_sse.sse_within_origin) == lifted
    assert sdk_streamable_http.EventSource._bd_max_sse_event_bytes == barndoor_mcp.MAX_SSE_EVENT_BYTES


def test_an_unbounded_lift_from_another_copy_is_left_alone(sdk_readers_reset):
    """The probe library marks an unbounded lift with `None`; that already covers this SDK's cap."""

    def unbounded(response):
        return httpx2.EventSource(response, max_event_size=None)

    unbounded._bd_max_sse_event_bytes = None
    sdk_streamable_http.EventSource = unbounded

    barndoor_mcp._lift_sse_event_cap(barndoor_mcp.MAX_SSE_EVENT_BYTES)

    assert sdk_streamable_http.EventSource is unbounded
