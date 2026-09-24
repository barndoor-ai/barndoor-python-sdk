"""Client assembly, and the seams that make an async provider work."""

from __future__ import annotations

import uuid

import pytest

from barndoor.lib.client import _uuid_coercing


async def test_a_uuid_argument_becomes_a_string():
    """The spec types 68 response properties as format: uuid but 11 path
    parameters as plain string, so `get_policy(list_policies()[0].id)` — the
    chain any user writes — raised ValidationError on the UUID it was just
    handed.
    """
    seen = {}

    async def method(policy_id, *, limit=None):
        seen["positional"] = policy_id
        seen["keyword"] = limit
        return "ok"

    wrapped = _uuid_coercing(method)
    uid = uuid.uuid4()
    assert await wrapped(uid, limit=uid) == "ok"
    assert seen["positional"] == str(uid)
    assert seen["keyword"] == str(uid)


async def test_nothing_else_is_coerced():
    """One type is converted, not "whatever looks close".

    A stringified int or a None turning into "None" would be a far worse bug
    than the one this fixes.
    """
    seen = []

    async def method(*args, **kwargs):
        seen.extend(args)
        seen.extend(kwargs.values())

    wrapped = _uuid_coercing(method)
    await wrapped(1, None, "abc", [uuid.uuid4()], flag=True)
    assert seen[:3] == [1, None, "abc"]
    assert isinstance(seen[3], list) and isinstance(seen[3][0], uuid.UUID), "a nested UUID is left alone"
    assert seen[4] is True


async def test_the_wrapper_keeps_the_method_identity():
    """`functools.wraps`, so introspection and error messages still name the
    real method rather than an anonymous closure."""

    async def get_policy(policy_id):
        return policy_id

    assert _uuid_coercing(get_policy).__name__ == "get_policy"
