"""Discord-independent resource manifest, authorization inputs and policy."""

from dataclasses import dataclass
import hashlib
import json

from .errors import AppError


class DiscordPolicyError(AppError):
    code = "DISCORD_POLICY"


class SetupError(AppError):
    code = "SETUP_FAILED"


class UncertainOperation(SetupError):
    """An external mutation may have succeeded: never blindly repeat it."""


@dataclass(frozen=True)
class ResourceSpec:
    key: str
    name: str
    kind: str
    parent: str | None = None


CATEGORIES = (
    ResourceSpec("control_center", "Control Center", "CATEGORY"),
    ResourceSpec("lead_hunting", "Lead Hunting", "CATEGORY"),
    ResourceSpec("sales_crm", "Sales & CRM", "CATEGORY"),
    ResourceSpec("system", "System", "CATEGORY"),
)
CHANNELS = tuple(ResourceSpec(key, key, "TEXT", parent) for parent, keys in (
    ("control_center", ("dashboard", "bot-control", "subscription-usage")),
    ("lead_hunting", ("campaigns", "lead-discovery", "business-research", "qualified-leads")),
    ("sales_crm", ("lead-pipeline", "outreach-drafts", "follow-ups")),
    ("system", ("bot-settings", "activity-logs")),
) for key in keys)
RESOURCES = {r.key: r for r in (*CATEGORIES, *CHANNELS)}
COMMAND_CHANNELS = {
    **{f"hunt.{action}": "bot-control" for action in ("start", "pause", "resume", "stop", "status")},
    **{f"campaign.{action}": "campaigns" for action in ("create", "list", "edit")},
    "discover": "lead-discovery", "research": "business-research", "qualified": "qualified-leads",
    "leads": "lead-pipeline", "lead": "lead-pipeline", "pipeline": "lead-pipeline",
    "outreach": "outreach-drafts", "followup": "follow-ups", "usage": "subscription-usage",
    "connections": "subscription-usage", "config": "bot-settings", "setup": "bot-settings", "backup": "bot-settings",
}
OUTPUT_DESTINATIONS = {
    "dashboard": "dashboard", "hunt_progress": "bot-control", "research": "business-research",
    "qualified_leads": "qualified-leads", "pipeline": "lead-pipeline", "drafts": "outreach-drafts",
    "followups": "follow-ups", "usage": "subscription-usage", "activity": "activity-logs",
}
PANELS = {"dashboard": "dashboard", "hunt_progress": "bot-control", "usage": "subscription-usage", "settings": "bot-settings"}
REQUIRED_BOT_PERMISSIONS = frozenset({
    "view_channel", "send_messages", "embed_links", "attach_files", "read_message_history",
    "manage_channels", "manage_roles",
})
OUTPUT_PERMISSIONS = frozenset({"view_channel", "send_messages", "embed_links", "attach_files", "read_message_history"})


@dataclass(frozen=True)
class ActorContext:
    guild_id: str | None
    channel_id: str | None
    user_id: str
    role_ids: frozenset[str] = frozenset()
    administrator: bool = False
    text_channel: bool = True
    can_view: bool = True


@dataclass(frozen=True)
class RemoteChannel:
    id: str
    name: str
    kind: str
    parent_id: str | None
    overwrites: tuple[tuple[str, int, int], ...]
    bot_permissions: frozenset[str]
    topic: str | None = None


@dataclass(frozen=True)
class GuildSnapshot:
    guild_id: str
    bot_id: str
    channels: tuple[RemoteChannel, ...]
    role_ids: frozenset[str]
    role_permissions: tuple[tuple[str, int], ...]
    owner_members: frozenset[str]
    bot_permissions: frozenset[str]

    def channel(self, identifier):
        return next((c for c in self.channels if c.id == identifier), None)

    def fingerprint(self):
        body = {
            "guild": self.guild_id, "bot": self.bot_id, "owners": sorted(self.owner_members),
            "roles": sorted(self.role_permissions), "permissions": sorted(self.bot_permissions),
            "channels": [dict(id=c.id, name=c.name, kind=c.kind, parent=c.parent_id,
                              overwrites=c.overwrites, topic=c.topic) for c in sorted(self.channels, key=lambda c: c.id)],
        }
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require_actor(actor, guild_id, owner_ids, operator_roles=(), *, administrator=False):
    if actor.guild_id != guild_id or not actor.text_channel or not actor.can_view:
        raise DiscordPolicyError("Use a text channel in the configured Discord server.")
    privileged = actor.user_id in owner_ids or actor.administrator
    if not privileged and (administrator or not set(actor.role_ids).intersection(operator_roles)):
        raise DiscordPolicyError("You are not authorized for this action.")


def authorize(actor, command_key, *, guild_id, owner_ids, operator_roles, config, mappings, snapshot, admin_action=False):
    require_actor(actor, guild_id, owner_ids, operator_roles,
                  administrator=admin_action or command_key in {"setup", "config", "backup"})
    if command_key not in COMMAND_CHANNELS:
        raise DiscordPolicyError("This command is not configured.")
    destination = mappings.get(command_key)
    remote = snapshot.channel(destination) if destination else None
    if command_key == "setup" and (remote is None or "view_channel" not in remote.bot_permissions):
        return  # The only bootstrap/recovery exception.
    if remote is None or remote.kind != "TEXT":
        raise DiscordPolicyError("Command is not configured; ask an administrator to run /setup.")
    if actor.channel_id != destination:
        raise DiscordPolicyError(f"Use <#{destination}> for this command.")
    if command_key != "setup" and (config.get("setup_state") != "READY" or set(mappings) != set(COMMAND_CHANNELS)):
        raise DiscordPolicyError("Configuration is incomplete; ask an administrator to run /setup.")
    if not OUTPUT_PERMISSIONS <= remote.bot_permissions:
        raise DiscordPolicyError("The bot lacks required channel permissions; ask an administrator to run /setup.")
