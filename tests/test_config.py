"""The environment table, and the one value this SDK states rather than reads."""

from __future__ import annotations

import pathlib

import pytest
import yaml

from barndoor.lib.config import DEV, LOCAL, PRODUCTION_ISSUER, Environment, environment_from_env


def _spec() -> dict:
    """The OpenAPI document, wherever this package is checked out.

    In the monorepo it is the generator's input; in the publishing repo it is
    the copy pushed alongside the client. A test that silently skipped when it
    could not find either would be a parity gate that never runs.
    """
    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parents[3] / "docs" / "api" / "public-openapi.yaml",  # monorepo
        here.parents[1] / "openapi.yaml",  # SDK repo
    ]
    for path in candidates:
        if path.is_file():
            return yaml.safe_load(path.read_text())
    pytest.fail(f"no spec found at any of: {[str(c) for c in candidates]}")


def test_production_issuer_matches_the_spec():
    """PRODUCTION_ISSUER is a hand-copied value; this is what holds it honest.

    The TypeScript SDK emits the issuer from a vendored template, so it cannot
    drift. The Python generator emits no equivalent and vendoring
    configuration.mustache for one string is a poor trade — so the copy is
    checked against the source instead.
    """
    schemes = _spec()["components"]["securitySchemes"]
    declared = schemes["OAuth2"]["x-issuer"]
    assert PRODUCTION_ISSUER == declared


def test_production_base_url_is_not_restated_here():
    """The base URL comes from the spec's `servers` block via the generator.

    If someone ever adds a PRODUCTION_BASE_URL constant beside the issuer, it is
    a second copy of something already generated — and the two will disagree.
    """
    import barndoor.lib.config as config

    assert not any(n.endswith("BASE_URL") for n in dir(config))


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, None),
        ({"BARNDOOR_ENV": "dev"}, DEV),
        ({"BARNDOOR_ENV": "DEV"}, DEV),
        ({"BARNDOOR_ENV": " local "}, LOCAL),
        ({"BARNDOOR_ENV": "production"}, None),
        ({"BARNDOOR_ENV": "nonsense"}, None),
    ],
)
def test_named_environments(env, expected):
    assert environment_from_env(env) == expected


def test_url_override_without_a_named_environment_uses_the_production_issuer():
    """A bare URL override still needs an issuer to authenticate against."""
    result = environment_from_env({"BARNDOOR_API_URL": "https://example.test"})
    assert result == Environment(issuer=PRODUCTION_ISSUER, base_url="https://example.test")


def test_url_override_keeps_the_named_environment_issuer():
    """Pointing at a dev URL must not leave the token coming from production."""
    result = environment_from_env({"BARNDOOR_ENV": "dev", "BARNDOOR_API_URL": "https://example.test"})
    assert result.issuer == DEV.issuer
    assert result.base_url == "https://example.test"


def test_the_environment_is_never_read_unless_asked():
    """The SDK must not re-point itself because of an ambient variable.

    `environment_from_env` is opt-in; nothing else may consult os.environ.
    """
    import barndoor.lib.client as client_module

    source = pathlib.Path(client_module.__file__).read_text()
    assert "os.environ" not in source
    assert "getenv" not in source
