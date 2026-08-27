"""Pydantic models for the Barndoor SDK.

This module defines the data models used for API requests and responses,
providing type safety and automatic validation.
"""

from pydantic import BaseModel


class ServerSummary(BaseModel):
    """Summary information about an MCP server.

    Represents basic server information as returned by the list servers
    endpoint. This is a lightweight representation suitable for listing
    many servers at once.

    Attributes
    ----------
    id : str
        Unique identifier (UUID) for the server
    name : str
        Human-readable name of the server
    slug : str
        URL-friendly identifier used in API paths
    provider : str, optional
        Third-party provider name (e.g., "github", "slack")
    connection_status : str
        Current connection status: "available", "pending", or "connected"
    """

    id: str
    name: str
    slug: str
    provider: str | None = None
    connection_status: str
    proxy_url: str | None = None


class ServerDetail(ServerSummary):
    """Detailed information about an MCP server.

    Extends ServerSummary with additional fields returned when fetching
    a single server's details.

    Attributes
    ----------
    url : str, optional
        MCP base URL from the server directory
    """

    url: str | None = None  # MCP base url from directory


class AgentToken(BaseModel):
    """Response from the agent token exchange endpoint.

    Contains the agent access token and expiration information returned
    when exchanging client credentials.

    Attributes
    ----------
    agent_token : str
        The agent access token to use for agent operations
    expires_in : int
        Token lifetime in seconds
    """

    agent_token: str
    expires_in: int


# ---------------------------------------------------------------------------
# Notification channels (BCP-3758)
#
# Mirrors the platform's public channel-management surface at
# /api/notification/public/v1/channels. Field docs are deliberately terse here;
# the authoritative descriptions live in the platform's OpenAPI document.
# ---------------------------------------------------------------------------


class ChannelSubscription(BaseModel):
    """One alert type a channel is subscribed to.

    Attributes
    ----------
    alert_type : str
        The alert type delivered to the channel (e.g. "break_glass_used"). Read the
        live vocabulary from :meth:`BarndoorSDK.get_channel_options` rather than
        hardcoding it — the set grows over time and is gated per organization.
    """

    alert_type: str


class Channel(BaseModel):
    """A notification delivery destination.

    ``type`` discriminates the whole model: personal channels (``in_app``,
    ``user_email``) are owned by one user, while ``email`` / ``webhook`` / ``slack``
    / ``teams`` are organization-wide. Only the destination field belonging to the
    type is populated; the rest are ``None``.

    Attributes
    ----------
    id : str
        Server-assigned channel id.
    type : str
        One of "in_app", "user_email", "email", "webhook", "slack", "teams".
    enabled : bool
        Whether the channel currently delivers.
    user_id : str, optional
        Owning user for a personal channel; ``None`` for organization-wide types.
    email_address : str, optional
        Destination for ``type="email"``.
    url : str, optional
        Destination for ``type="webhook"``.
    label : str, optional
        Human-readable name, set for ``slack`` and ``teams``.
    slack_channel_id : str, optional
        Slack channel id for ``type="slack"``.
    subscriptions : list of ChannelSubscription
        Alert types this channel delivers. Empty means it delivers nothing.
    has_signing_secret : bool
        Whether a webhook channel has a stored signing secret. The secret itself is
        never readable back.
    has_workflow_url : bool
        Whether a teams channel has a stored Workflows URL (itself a secret).
    signing_secret : str, optional
        One-time reveal of a newly generated webhook signing secret. Populated ONLY
        on the response that created it, and ``None`` on every later read — store it
        when you receive it, or rotate with
        :meth:`BarndoorSDK.regenerate_channel_secret`.
    """

    id: str
    type: str
    enabled: bool
    user_id: str | None = None
    email_address: str | None = None
    url: str | None = None
    label: str | None = None
    slack_channel_id: str | None = None
    subscriptions: list[ChannelSubscription] = []
    created_at: str | None = None
    updated_at: str | None = None
    has_signing_secret: bool = False
    has_workflow_url: bool = False
    signing_secret: str | None = None


class AlertTypeOption(BaseModel):
    """One subscribable alert type, with its intrinsic category and severity.

    Attributes
    ----------
    value : str
        What to send as a subscription's ``alert_type``.
    label : str
        Human-readable label.
    category : str
        The type's category. Intrinsic to the type, not configurable.
    severity : str
        The type's severity ("info", "warning", "critical"). Also intrinsic.
    """

    value: str
    label: str
    category: str
    severity: str


class LabeledOption(BaseModel):
    """An enum value paired with its display label."""

    value: str
    label: str


class ChannelOptions(BaseModel):
    """The subscription vocabulary a channel's ``subscriptions`` may draw from.

    ``alert_types`` is filtered to what the caller's organization is admitted to —
    subscribing to a type absent here is accepted but never delivers.

    Attributes
    ----------
    alert_types : list of AlertTypeOption
        Every alert type this organization may subscribe a channel to.
    categories : list of LabeledOption
        The full category vocabulary, unfiltered.
    severities : list of LabeledOption
        The full severity vocabulary, unfiltered.
    """

    alert_types: list[AlertTypeOption] = []
    categories: list[LabeledOption] = []
    severities: list[LabeledOption] = []


class ChannelTestResult(BaseModel):
    """Result of sending a connectivity-test message through a channel.

    A transport failure is reported here as ``ok=False`` with a reason, not as an
    HTTP error: the request to test succeeded, the delivery is what failed.

    Attributes
    ----------
    ok : bool
        Whether the test message reached the destination transport.
    error : str, optional
        Why delivery failed, when ``ok`` is False.
    """

    ok: bool
    error: str | None = None


class WebhookSecret(BaseModel):
    """The one-time reveal of a webhook channel's signing secret.

    Attributes
    ----------
    signing_secret : str
        Standard Webhooks secret (``whsec_`` + base64), shown exactly once. Rotating
        invalidates the previous secret immediately, so deploy this value before the
        next alert fires.
    """

    signing_secret: str
