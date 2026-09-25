"""``barndoor-login`` — an interactive login from a terminal.

Node-only in the TypeScript SDK because it binds a port; here it is simply a
separate entry point, kept out of the package root so importing the SDK never
drags in an HTTP server.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import webbrowser

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .auth import complete_authorization_code, start_authorization_code
from .config import PRODUCTION_ISSUER, environment_from_env


#: Loopback only. A public redirect would hand the authorization code to
#: whoever controls that host.
_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        query = parse_qs(urlparse(self.path).query)
        _CallbackHandler.result = {k: v[0] for k, v in query.items()}

        ok = "code" in _CallbackHandler.result
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        # No interpolation of anything the IdP sent: `error` and
        # `error_description` are attacker-influencable, and reflecting them
        # into HTML is a scripting sink on a page served from localhost.
        body = (
            "<h1>Signed in</h1><p>You can close this window.</p>"
            if ok
            else "<h1>Sign-in failed</h1><p>Check the terminal for details.</p>"
        )
        self.wfile.write(body.encode())

    def log_message(self, *_: object) -> None:
        """Silence the default stderr access log."""


async def login(port: int = _DEFAULT_PORT, client_id: str = "barndoor-cli") -> dict:
    """Run the browser flow and return the token response."""
    env = environment_from_env()
    issuer = env.issuer if env else PRODUCTION_ISSUER
    redirect_uri = f"http://{_HOST}:{port}/callback"

    request = start_authorization_code(client_id=client_id, redirect_uri=redirect_uri, issuer=issuer)

    server = HTTPServer((_HOST, port), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Opening {request.url}")
    webbrowser.open(request.url)
    print(f"Waiting for the redirect on {redirect_uri} ...")

    await asyncio.get_running_loop().run_in_executor(None, thread.join, 300)
    server.server_close()

    result = _CallbackHandler.result
    if "code" not in result:
        raise RuntimeError(f"sign-in failed: {result.get('error', 'no code returned')}")
    # The state check is what stops a different login's code being swapped in.
    if result.get("state") != request.state:
        raise RuntimeError("state mismatch: the redirect did not belong to this login")

    return await complete_authorization_code(
        result["code"], request, client_id=client_id, redirect_uri=redirect_uri, issuer=issuer
    )


def main() -> int:
    """Console-script entry point."""
    try:
        token = asyncio.run(login())
    except Exception as exc:  # noqa: BLE001 - a CLI reports, it does not traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("\nSigned in. Keep the refresh token somewhere your app can read it:")
    print(f"  refresh_token: {token.get('refresh_token', '<none returned>')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
