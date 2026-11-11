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


def _enum_classes():
    import enum
    import inspect

    import barndoor.models as models

    return [
        cls
        for _, cls in inspect.getmembers(models, inspect.isclass)
        if issubclass(cls, enum.Enum) and cls.__module__.startswith("barndoor.models.")
    ]


def test_unknown_enum_value_is_kept():
    """A value newer than the SDK must not fail the response that carries it.

    Adding an enum value is a minor API change. templates/model_enum.mustache
    adds `_missing_`; dropping it fails here.
    """
    from barndoor.models.alert_type import AlertType
    from barndoor.models.channel_subscription import ChannelSubscription

    sub = ChannelSubscription.from_json('{"alert_type": "added_after_this_sdk"}')
    assert sub.alert_type == "added_after_this_sdk"
    assert sub.alert_type.value == "added_after_this_sdk"
    assert isinstance(sub.alert_type, AlertType)
    assert sub.alert_type not in list(AlertType)
    # How a caller tells it from a listed member; `in AlertType` differs
    # between Python 3.11 and 3.12.
    assert sub.alert_type.name is None
    # It goes back out as it came in.
    assert sub.to_dict() == {"alert_type": "added_after_this_sdk"}
    assert '"added_after_this_sdk"' in sub.to_json()

    # A known value is still the member itself.
    known = next(iter(AlertType))
    assert ChannelSubscription.from_dict({"alert_type": known.value}).alert_type is known


def test_every_enum_keeps_an_unknown_value():
    """The same, for every enum the spec defines, so a new one cannot regress."""
    from pydantic import TypeAdapter

    classes = _enum_classes()
    assert len(classes) >= 30, f"found only {len(classes)} enums; the discovery is broken"
    for cls in classes:
        assert cls("added_after_this_sdk") == "added_after_this_sdk", cls.__name__
        assert TypeAdapter(cls).validate_python("added_after_this_sdk") == "added_after_this_sdk", cls.__name__
        assert cls.from_json('"added_after_this_sdk"') == "added_after_this_sdk", cls.__name__
        # A value of the wrong type is still refused.
        with pytest.raises(ValueError):
            cls(42)


def test_unknown_inline_enum_value_is_kept():
    """The same for a multi-value enum declared inline on a property.

    Upstream generates a `<field>_validate_enum` validator that raises;
    templates/model_generic.mustache skips the check for more than one value.
    """
    from barndoor.models.directory_credential_modes import DirectoryCredentialModes

    modes = DirectoryCredentialModes.from_dict(
        {"automatic": "added_after_this_sdk", "managed": True, "default": "added_after_this_sdk"}
    )
    assert modes.automatic == "added_after_this_sdk"
    assert modes.default == "added_after_this_sdk"


def _signed_artifact() -> dict:
    return {"key_id": "k", "manifest": "m", "signature": "s"}


@pytest.mark.parametrize(
    ("payload", "variant"),
    [
        ({"kind": "embedded", "ref": "com.barndoor.cli.x", "minimum_cli_version": "1.0.0"}, "EmbeddedRuntime"),
        (
            {
                "kind": "local_cli",
                "ref": "com.barndoor.cli.x",
                "minimum_cli_version": "1.0.0",
                "artifact": _signed_artifact(),
            },
            "LocalCliRuntime",
        ),
        (
            {
                "kind": "managed_local_mcp",
                "ref": "com.barndoor.mcp.x",
                "minimum_cli_version": "1.0.0",
                "artifact": _signed_artifact(),
            },
            "ManagedMcpRuntime",
        ),
        ({"kind": "remote"}, "RemoteRuntime"),
    ],
)
def test_a_oneof_payload_parses_as_its_own_variant(payload, variant):
    """Variants differ only by a single-value `kind`, and the wrapper has no
    discriminator mapping: without the tag check every payload also matches
    RemoteRuntime, and LocalCliRuntime and ManagedMcpRuntime match each other.
    """
    import json

    from barndoor.models.runtime import Runtime

    assert type(Runtime.from_json(json.dumps(payload)).actual_instance).__name__ == variant


def test_every_oneof_variant_rejects_another_tag():
    """Every tagged oneOf variant refuses a value its single-value tag does not list.

    templates/model_generic.mustache keeps the enum check for a single-value
    enum. Without it a payload for one variant also validates as every variant
    whose required fields it covers, and the wrapper fails with "Multiple
    matches" or picks the wrong one. Variants with no tag at all (the policy
    expression wrappers) are out of scope here.
    """
    import inspect

    import barndoor.models as models

    from pydantic import ValidationError

    checked = 0
    for wrapper_name, wrapper in inspect.getmembers(models, inspect.isclass):
        schemas = getattr(wrapper, "model_fields", {}).get("one_of_schemas")
        if schemas is None:
            continue

        variants = [getattr(models, name) for name in sorted(schemas.default)]
        tags = {v: [f for f in v.model_fields if hasattr(v, f + "_validate_enum")] for v in variants}
        if not any(tags.values()):
            continue

        for variant, fields in tags.items():
            assert len(fields) == 1, f"{wrapper_name}: {variant.__name__} has tag fields {fields}"
            with pytest.raises(ValidationError) as err:
                variant.model_validate({fields[0]: "added_after_this_sdk"})
            assert any(e["loc"] == (fields[0],) for e in err.value.errors()), (
                f"{wrapper_name}: {variant.__name__}.{fields[0]} accepted another variant's tag"
            )
            checked += 1

    assert checked >= 20, f"checked only {checked} variants; the discovery is broken"


def test_only_oneof_variants_have_a_checked_inline_enum():
    """A single-value inline enum is checked strictly, which is right only for a oneOf tag.

    Anywhere else, the API adding a second value is a minor change that would
    fail every response holding it. A new single-value inline enum outside a
    oneOf fails here so its author decides whether it is a tag.
    """
    import inspect

    import barndoor.models as models

    from pydantic import ValidationError

    variants = set()
    for _, cls in inspect.getmembers(models, inspect.isclass):
        schemas = getattr(cls, "model_fields", {}).get("one_of_schemas")
        if schemas is not None:
            variants |= set(schemas.default)

    strict = []
    for name, cls in inspect.getmembers(models, inspect.isclass):
        for field in getattr(cls, "model_fields", {}):
            if not hasattr(cls, field + "_validate_enum"):
                continue
            try:
                cls.model_validate({field: "added_after_this_sdk"})
            except ValidationError as err:
                if any(e["loc"] == (field,) for e in err.errors()):
                    strict.append((name, field))

    assert len(strict) >= 20, f"found only {len(strict)} checked enums; the discovery is broken"
    assert [s for s in strict if s[0] not in variants] == []
