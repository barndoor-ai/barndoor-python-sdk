"""Non-production overrides.

Production needs nothing here: the generated ``Configuration`` already carries
the production base URL, taken from the spec's ``servers`` block. Only the other
environments need declaring, because one spec cannot describe several
deployments.

The issuer is the one value this module states rather than reads. The
TypeScript SDK gets it from a vendored template that emits the spec's
``x-issuer``; the Python generator emits no equivalent, and vendoring
``configuration.mustache`` to add one would be a large delta for a single
string. ``tests/test_config.py`` asserts it against the spec instead, so there
is still exactly one source of truth — enforced by a test rather than by
templating.
"""

from __future__ import annotations

import os

from dataclasses import dataclass


#: Production OIDC issuer. Mirrors ``x-issuer`` on the spec's OAuth2 scheme.
PRODUCTION_ISSUER = "https://auth.barndoor.ai/realms/barndoor"


@dataclass(frozen=True)
class Environment:
    """A deployment this SDK can be pointed at."""

    #: OIDC issuer, for discovery.
    issuer: str
    #: API base URL, passed to the generated ``Configuration`` as ``host``.
    base_url: str


DEV = Environment(
    issuer="https://auth.barndoordev.com/realms/barndoor",
    base_url="https://platform.barndoordev.com",
)

#: Local Tilt. The host carries an ``mcp.`` prefix rather than ``platform.``,
#: which is why the spec's ``servers`` variable is the whole host and not a
#: domain suffix — see charts/barndoor/values.yaml.
LOCAL = Environment(
    issuer="https://auth.barndoorlocal.com/realms/barndoor",
    base_url="https://mcp.barndoorlocal.com",
)


def environment_from_env(source: dict[str, str] | None = None) -> Environment | None:
    """Read an environment from environment variables.

    Opt-in on purpose. The SDK never reads the environment by itself: a library
    that quietly re-points itself at another cluster because of a variable set
    for some unrelated reason is a bad surprise. Callers who want the behaviour
    ask for it::

        create_client(auth=key, env=environment_from_env())

    ``BARNDOOR_ENV`` selects a known environment (``dev`` or ``local``; anything
    else, including unset, means production). ``BARNDOOR_API_URL`` overrides the
    base URL independently, for a deployment this SDK does not know about.

    Returns ``None`` for production, which is what :func:`create_client` wants
    when it should fall back to the generated defaults.
    """
    env = os.environ if source is None else source

    named = (env.get("BARNDOOR_ENV") or "").strip().lower()
    base = {"dev": DEV, "local": LOCAL}.get(named)

    url = (env.get("BARNDOOR_API_URL") or "").strip()
    if not url:
        return base

    # A bare URL override still needs an issuer, and production's is the only
    # one the SDK knows without being told.
    return Environment(issuer=base.issuer if base else PRODUCTION_ISSUER, base_url=url)
