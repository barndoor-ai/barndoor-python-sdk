"""Tests for the notification channel methods (BCP-3758).

These cover the platform's public channel-management surface at
/api/notification/public/v1/channels. The emphasis is on the parts a caller can get
wrong and the parts where a refactor could silently change behaviour:

- the exact path and HTTP verb each method uses (a typo here is a 404 in production
  that no type checker catches);
- that ``subscriptions`` is always sent, because the endpoint *replaces* rather than
  merges and an omitted key would silently mean "unsubscribe from everything";
- that the one-time ``signing_secret`` reveal survives model validation;
- that a failed channel test comes back as data (``ok=False``), not an exception.
"""

from unittest.mock import AsyncMock, patch

import pytest

from barndoor.sdk.exceptions import HTTPError
from barndoor.sdk.models import Channel, ChannelOptions, ChannelTestResult, WebhookSecret

CHANNELS = "/api/notification/public/v1/channels"


def _channel_json(**overrides):
    payload = {
        "id": "11111111-1111-1111-1111-111111111111",
        "type": "webhook",
        "enabled": True,
        "user_id": None,
        "email_address": None,
        "url": "https://hooks.example.com/barndoor",
        "label": None,
        "slack_channel_id": None,
        "subscriptions": [{"alert_type": "break_glass_used"}],
        "created_at": "2026-08-26T00:00:00Z",
        "updated_at": "2026-08-26T00:00:00Z",
        "has_signing_secret": True,
        "has_workflow_url": False,
        "signing_secret": None,
    }
    payload.update(overrides)
    return payload


class TestListChannels:
    @pytest.mark.asyncio
    async def test_list_channels_parses_data_envelope(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = {"data": [_channel_json()]}

            channels = await sdk_client.list_channels()

            assert len(channels) == 1
            assert isinstance(channels[0], Channel)
            assert channels[0].url == "https://hooks.example.com/barndoor"
            assert channels[0].subscriptions[0].alert_type == "break_glass_used"
            req.assert_called_once_with("GET", CHANNELS)

    @pytest.mark.asyncio
    async def test_list_channels_handles_empty_and_missing_envelope(self, sdk_client):
        """An org with no shared channels must yield [], not raise."""
        for response in ({"data": []}, {}):
            with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
                req.return_value = response
                assert await sdk_client.list_channels() == []

    @pytest.mark.asyncio
    async def test_list_user_channels_uses_the_user_path(self, sdk_client):
        """Personal channels come from a different path — not a filter on the org list."""
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = {"data": [_channel_json(type="in_app", url=None)]}

            channels = await sdk_client.list_user_channels()

            assert channels[0].type == "in_app"
            req.assert_called_once_with("GET", f"{CHANNELS}/user")


class TestChannelOptions:
    @pytest.mark.asyncio
    async def test_get_channel_options(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = {
                "alert_types": [
                    {
                        "value": "break_glass_used",
                        "label": "Break-glass used",
                        "category": "access_control",
                        "severity": "critical",
                    }
                ],
                "categories": [{"value": "access_control", "label": "Access control"}],
                "severities": [{"value": "critical", "label": "Critical"}],
            }

            options = await sdk_client.get_channel_options()

            assert isinstance(options, ChannelOptions)
            assert options.alert_types[0].severity == "critical"
            assert options.categories[0].label == "Access control"
            req.assert_called_once_with("GET", f"{CHANNELS}/options")


class TestUpsertChannel:
    @pytest.mark.asyncio
    async def test_create_sends_put_without_id(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = _channel_json(signing_secret="whsec_abc")

            channel = await sdk_client.upsert_channel(
                type="webhook",
                url="https://hooks.example.com/barndoor",
                subscriptions=["break_glass_used", "policy_changed"],
            )

            method, path = req.call_args.args
            body = req.call_args.kwargs["json"]
            assert (method, path) == ("PUT", CHANNELS)
            assert "id" not in body, "a create must not send an id"
            assert body["type"] == "webhook"
            assert body["url"] == "https://hooks.example.com/barndoor"
            assert body["subscriptions"] == [
                {"alert_type": "break_glass_used"},
                {"alert_type": "policy_changed"},
            ]
            # The one-time reveal must survive validation — losing it is unrecoverable
            # without a rotation.
            assert channel.signing_secret == "whsec_abc"

    @pytest.mark.asyncio
    async def test_edit_by_id_sends_the_id(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = _channel_json(enabled=False)

            await sdk_client.upsert_channel(
                channel_id=" 22222222-2222-2222-2222-222222222222 ",
                type="webhook",
                url="https://hooks.example.com/barndoor",
                enabled=False,
            )

            body = req.call_args.kwargs["json"]
            assert body["id"] == "22222222-2222-2222-2222-222222222222", "id must be trimmed"
            assert body["enabled"] is False

    @pytest.mark.asyncio
    async def test_subscriptions_are_always_sent(self, sdk_client):
        """Replace-not-merge: omitting subscriptions means "unsubscribe from everything".

        The endpoint replaces the set, so an absent key and an empty list are the same
        thing. Sending it explicitly keeps that destructive default visible on the wire
        instead of depending on server-side defaulting.
        """
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = _channel_json(subscriptions=[])

            await sdk_client.upsert_channel(type="email", email_address="ops@example.com")

            assert req.call_args.kwargs["json"]["subscriptions"] == []

    @pytest.mark.asyncio
    async def test_only_supplied_destination_fields_are_sent(self, sdk_client):
        """Sending a field that does not belong to the type is a 422 server-side.

        So the client must not pad the body with nulls for the other types' fields.
        """
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = _channel_json(
                type="email", url=None, email_address="ops@example.com"
            )

            await sdk_client.upsert_channel(type="email", email_address="ops@example.com")

            body = req.call_args.kwargs["json"]
            assert set(body) == {"type", "enabled", "email_address", "subscriptions"}

    @pytest.mark.asyncio
    async def test_teams_workflow_url_is_forwarded(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = _channel_json(
                type="teams", url=None, label="Ops", has_workflow_url=True
            )

            channel = await sdk_client.upsert_channel(
                type="teams",
                label="Ops",
                teams_workflow_url="https://example.logic.azure.com/workflows/abc",
            )

            body = req.call_args.kwargs["json"]
            assert body["teams_workflow_url"] == "https://example.logic.azure.com/workflows/abc"
            # Write-only server-side: reads expose only the flag.
            assert channel.has_workflow_url is True

    @pytest.mark.asyncio
    async def test_rejects_empty_type(self, sdk_client):
        with pytest.raises(ValueError, match="type"):
            await sdk_client.upsert_channel(type="")

    @pytest.mark.asyncio
    async def test_rejects_blank_channel_id(self, sdk_client):
        with pytest.raises(ValueError, match="Channel ID"):
            await sdk_client.upsert_channel(type="webhook", channel_id="   ")

    @pytest.mark.asyncio
    async def test_validation_error_propagates(self, sdk_client):
        """A body that violates the per-type rules is a 422 from the server."""
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.side_effect = HTTPError(422, "email channel requires email_address")

            with pytest.raises(HTTPError) as exc:
                await sdk_client.upsert_channel(type="email")

            assert exc.value.status_code == 422


class TestDeleteChannel:
    @pytest.mark.asyncio
    async def test_delete_uses_the_channel_path(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = {}

            assert await sdk_client.delete_channel("abc-123") is None
            req.assert_called_once_with("DELETE", f"{CHANNELS}/abc-123")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", ["", "   ", None])
    async def test_delete_rejects_bad_ids(self, sdk_client, bad):
        with pytest.raises(ValueError):
            await sdk_client.delete_channel(bad)

    @pytest.mark.asyncio
    async def test_delete_missing_channel_raises_404(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.side_effect = HTTPError(404, "Channel not found")

            with pytest.raises(HTTPError) as exc:
                await sdk_client.delete_channel("nope")

            assert exc.value.status_code == 404


class TestRegenerateSecret:
    @pytest.mark.asyncio
    async def test_regenerate_returns_the_secret(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = {"signing_secret": "whsec_rotated"}

            result = await sdk_client.regenerate_channel_secret("abc-123")

            assert isinstance(result, WebhookSecret)
            assert result.signing_secret == "whsec_rotated"
            req.assert_called_once_with("POST", f"{CHANNELS}/abc-123/regenerate-secret")


class TestTestChannel:
    @pytest.mark.asyncio
    async def test_success(self, sdk_client):
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = {"ok": True, "error": None}

            result = await sdk_client.test_channel("abc-123")

            assert isinstance(result, ChannelTestResult)
            assert result.ok is True
            req.assert_called_once_with("POST", f"{CHANNELS}/abc-123/test")

    @pytest.mark.asyncio
    async def test_transport_failure_is_data_not_an_exception(self, sdk_client):
        """A 200 with ok=False. Raising here would be wrong: the request succeeded."""
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as req:
            req.return_value = {"ok": False, "error": "connection refused"}

            result = await sdk_client.test_channel("abc-123")

            assert result.ok is False
            assert result.error == "connection refused"
