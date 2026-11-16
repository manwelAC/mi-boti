"""Fake Discord boundary; real services and SQLite are exercised by tests."""

from dataclasses import replace

from mi_boti.domain.discord import (
    ActorContext, RemoteChannel, GuildSnapshot, REQUIRED_BOT_PERMISSIONS,
    OUTPUT_PERMISSIONS, SetupError, UncertainOperation,
)
from mi_boti.discord_app.transport import DiscordPort


class FakePort:
    def __init__(self, settings):
        self.settings = settings
        self.members = {settings.owner_ids[0]: ActorContext(settings.guild_id, "900", settings.owner_ids[0])}
        self.channels = {"900": RemoteChannel("900", "unrelated-bootstrap", "TEXT", None, (), REQUIRED_BOT_PERMISSIONS)}
        self.role_ids = frozenset({settings.guild_id, "444", "445"})
        self.bot_permissions = REQUIRED_BOT_PERMISSIONS
        self.calls = []
        self.messages = {}
        self.counter = 1000
        self.failure_key = None
        self.uncertain = False

    async def snapshot(self):
        return GuildSnapshot(self.settings.guild_id, "777", tuple(self.channels.values()), self.role_ids,
                             tuple((role, 1) for role in sorted(self.role_ids)),
                             frozenset(self.settings.owner_ids), self.bot_permissions)

    async def fresh_actor(self, channel_id, user_id):
        if user_id not in self.members or channel_id not in self.channels:
            raise SetupError("Member or channel not found.")
        return replace(self.members[user_id], channel_id=channel_id)

    def overwrites(self, spec, snapshot, roles):
        return DiscordPort.overwrites(self, spec, snapshot, roles)

    async def provision(self, spec, action, parent_id, roles):
        self.calls.append((spec.key, action["action"]))
        if self.failure_key == spec.key and not self.uncertain:
            raise SetupError("Permission failure fixture.")
        snapshot = await self.snapshot()
        if action["action"] == "CREATE":
            self.counter += 1
            identifier = str(self.counter)
            self.channels[identifier] = RemoteChannel(identifier, action["name"], spec.kind, parent_id,
                                                       self.overwrites(spec, snapshot, roles), REQUIRED_BOT_PERMISSIONS)
        else:
            identifier = action["remote_id"]
            self.channels[identifier] = replace(self.channels[identifier], parent_id=parent_id,
                                                 overwrites=self.overwrites(spec, snapshot, roles))
        if self.failure_key == spec.key:
            raise UncertainOperation("Creation may have succeeded fixture.")
        return identifier

    async def panel_exists(self, channel_id, message_id):
        return (channel_id, message_id) in self.messages

    async def publish_panel(self, key, channel_id, panel_id, revision, message_id, current):
        self.calls.append(("panel." + key, "UPDATE" if message_id else "CREATE"))
        if not message_id:
            self.counter += 1
            message_id = str(self.counter)
        self.messages[channel_id, message_id] = (key, panel_id, revision)
        if self.failure_key == "panel." + key:
            raise UncertainOperation("Panel message outcome is uncertain fixture.")
        return message_id

    async def refresh_guide(self, channel_id, panel, current):
        if (channel_id, panel["message_id"]) not in self.messages:
            raise SetupError("Guide fixture is missing.")
        self.calls.append(("panel.guide", "REFRESH"))
