"""Generated-model regressions found by running against a real deployment.

Each of these was a live failure first. They are here so a generator upgrade,
a config change or a spec edit that reintroduces one fails in CI instead of on
a customer's first call.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml


def _spec() -> dict:
    here = pathlib.Path(__file__).resolve()
    for path in (here.parents[3] / "docs" / "api" / "public-openapi.yaml", here.parents[1] / "openapi.yaml"):
        if path.is_file():
            return yaml.safe_load(path.read_text())
    pytest.fail("no spec found")


def test_connection_status_is_a_plain_enum():
    """It was generated as an anyOf wrapper over ["List[Optional[str]]", "str"].

    The spec has two different things named connection_status: this response
    enum, and an inline query parameter on GET /servers with
    anyOf[array, string, null]. The generator promoted the parameter to a model
    class of the same name and the parameter's shape won, so deserialising a
    real response raised ValidationError on the plain string the API returns.

    gen-config.yaml renames the enum out of the collision. If that mapping is
    dropped, this fails.
    """
    from barndoor.models.server_connection_status import ServerConnectionStatus
    from barndoor.models.server_list_response import ServerListResponse

    assert issubclass(ServerConnectionStatus, str)
    assert ServerConnectionStatus("available") == "available"

    field = ServerListResponse.model_fields["connection_status"]
    assert "ServerConnectionStatus" in str(field.annotation)


def test_every_parameter_schema_collision_is_handled():
    """The general form of the bug above, asserted against the spec.

    A parameter whose name normalises to an existing schema's class name makes
    the generator mint a second class under that name, and which one wins is not
    something to leave to chance.

    The known collision is not removed — the spec is generated from the services
    and correct as it stands — so the invariant is that every collision has a
    modelNameMappings entry, not that none exist. A NEW one fails here, which is
    the point: it would otherwise surface as a ValidationError against live data.
    """
    import re

    spec = _spec()
    schemas = set(spec["components"]["schemas"])

    def to_class(name: str) -> str:
        return "".join(p.title() for p in re.split(r"[_\-]", name) if p)

    def has_ref(node) -> bool:
        if isinstance(node, dict):
            return "$ref" in node or any(has_ref(v) for v in node.values())
        if isinstance(node, list):
            return any(has_ref(v) for v in node)
        return False

    collisions = []
    for path, ops in spec["paths"].items():
        for method, op in (ops or {}).items():
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters", []) or []:
                schema = param.get("schema") or {}
                if has_ref(schema):
                    continue  # reuses a component; cannot mint a colliding class
                if to_class(param.get("name", "")) in schemas:
                    collisions.append(f"{method.upper()} {path} ?{param['name']}")

    config = here_config()
    mapped = {k.lower() for k in (config.get("modelNameMappings") or {})}
    unhandled = [c for c in collisions if to_class(c.rsplit("?", 1)[1]).lower() not in mapped]
    assert unhandled == [], (
        "inline parameter schemas collide with a component schema name and are not "
        "covered by modelNameMappings in gen-config.yaml: " + str(unhandled)
    )


def here_config() -> dict:
    """gen-config.yaml, from either checkout layout."""
    here = pathlib.Path(__file__).resolve()
    for path in (here.parents[1] / "gen-config.yaml",):
        if path.is_file():
            return yaml.safe_load(path.read_text())
    pytest.skip("gen-config.yaml is not shipped to the publishing repo")


def test_a_fastapi_validation_error_body_parses():
    """422 bodies are the one response the happy path never exercises.

    `loc` mixes strings and integers, which the generator renders as an anyOf
    wrapper — the same construct that broke connection_status. It parses; this
    pins that it keeps parsing.
    """
    from barndoor.models.http_validation_error import HTTPValidationError

    body = (
        '{"detail":[{"loc":["query","limit"],"msg":"bad","type":"type_error"},'
        '{"loc":["body",0,"name"],"msg":"required","type":"value_error.missing"}]}'
    )
    err = HTTPValidationError.from_json(body)
    assert len(err.detail) == 2
    # Values are reachable, even though they arrive wrapped.
    assert [x.actual_instance for x in err.detail[0].loc] == ["query", "limit"]
    assert [x.actual_instance for x in err.detail[1].loc] == ["body", 0, "name"]
