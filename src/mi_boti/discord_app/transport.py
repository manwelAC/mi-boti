"""discord.py adapter: fresh membership/permissions and bounded setup effects."""

import asyncio
import logging
import math

import discord

logger = logging.getLogger("mi_boti.discord.transport")

from ..domain.discord import (
    ActorContext, GuildSnapshot, RemoteChannel, SetupError, UncertainOperation,
    REQUIRED_BOT_PERMISSIONS, OUTPUT_PERMISSIONS,
)


def member_permissions(guild, member, roles):
    values = {str(role.id): role.permissions.value for role in roles}
    mask = values.get(str(guild.id), 0)
    role_ids = {str(role.id) for role in member.roles}
    for identifier in role_ids:
        mask |= values.get(identifier, 0)
    permissions = discord.Permissions(mask)
    if member.id == guild.owner_id or permissions.administrator:
        return discord.Permissions.all(), role_ids
    return permissions, role_ids


def effective_permissions(base, role_ids, member_id, guild_id, overwrites):
    if base.administrator:
        return discord.Permissions.all()
    mask = base.value
    everyone = next((o for o in overwrites if o[0] == "r:" + str(guild_id)), None)
    if everyone:
        mask = (mask & ~everyone[2]) | everyone[1]
    allow = deny = 0
    for target, permitted, prohibited in overwrites:
        if target.startswith("r:") and target[2:] != str(guild_id) and target[2:] in role_ids:
            allow |= permitted
            deny |= prohibited
    mask = (mask & ~deny) | allow
    member = next((o for o in overwrites if o[0] == "m:" + str(member_id)), None)
    if member:
        mask = (mask & ~member[2]) | member[1]
    return discord.Permissions(mask)


class DiscordPort:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    @property
    def guild(self):
        guild = self.client.get_guild(int(self.settings.guild_id))
        if guild is None:
            raise SetupError("The bot is not in the configured server. Invite it before running /setup.")
        return guild

    async def api(self, awaitable, *, mutation=False):
        try:
            return await asyncio.wait_for(awaitable, timeout=15)
        except (discord.Forbidden, discord.NotFound) as error:
            logger.warning("Discord access failure: type=%s status=%s code=%s mutation=%s",
                           type(error).__name__, error.status, error.code, mutation)
            raise SetupError(f"Discord denied access or a resource was deleted (HTTP {error.status}, code {error.code}). Check bot permissions and request a new setup preview.") from None
        except discord.RateLimited as error:
            seconds = max(1, math.ceil(error.retry_after))
            logger.warning("Discord rate limit: retry_after_seconds=%s mutation=%s", seconds, mutation)
            message = f"Discord rate-limited this request. Wait at least {seconds} seconds before trying again."
            if mutation:
                raise UncertainOperation(message + " Inspect the setup journal before recovery; do not assume the change failed.") from None
            raise SetupError(message + " No provisioning was started by this read.") from None
        except (asyncio.TimeoutError, discord.HTTPException, OSError) as error:
            # Log only bounded diagnostic fields, never HTTP bodies, URLs or headers.
            logger.warning("Discord request failed: type=%s status=%s code=%s mutation=%s",
                           type(error).__name__, getattr(error, "status", None),
                           getattr(error, "code", None), mutation)
            if mutation:
                raise UncertainOperation("Discord did not confirm the mutation outcome; inspect the setup journal.") from None
            raise SetupError("Discord is temporarily unavailable. No provisioning was started by this read.") from None

    def _overwrites(self, channel, roles):
        identifiers = {str(role.id) for role in roles}
        result = []
        for target, overwrite in channel.overwrites.items():
            allow, deny = overwrite.pair()
            key = ("r:" if str(target.id) in identifiers else "m:") + str(target.id)
            result.append((key, allow.value, deny.value))
        return tuple(sorted(result))

    async def snapshot(self):
        guild = self.guild
        channels, roles, bot = await asyncio.gather(
            self.api(guild.fetch_channels()), self.api(guild.fetch_roles()),
            self.api(guild.fetch_member(self.client.user.id)),
        )
        base, role_ids = member_permissions(guild, bot, roles)
        owners = set()
        for identifier in self.settings.owner_ids:
            try:
                member = await asyncio.wait_for(guild.fetch_member(int(identifier)), timeout=15)
                owners.add(str(member.id))
            except discord.NotFound:
                continue
            except (discord.HTTPException, asyncio.TimeoutError, OSError):
                raise SetupError("Cannot verify configured owner membership; retry the preview later.") from None
        result = []
        for channel in channels:
            if not isinstance(channel, (discord.TextChannel, discord.CategoryChannel)):
                continue
            overwrites = self._overwrites(channel, roles)
            effective = effective_permissions(base, role_ids, bot.id, guild.id, overwrites)
            flags = frozenset(name for name in REQUIRED_BOT_PERMISSIONS | {"use_application_commands"} if getattr(effective, name))
            result.append(RemoteChannel(str(channel.id), channel.name,
                                       "CATEGORY" if isinstance(channel, discord.CategoryChannel) else "TEXT",
                                       str(channel.category_id) if getattr(channel, "category_id", None) else None,
                                       overwrites, flags, getattr(channel, "topic", None)))
        snapshot = GuildSnapshot(str(guild.id), str(bot.id), tuple(result), frozenset(str(role.id) for role in roles),
                             tuple(sorted((str(role.id), role.permissions.value) for role in roles)),
                             frozenset(owners), frozenset(name for name in REQUIRED_BOT_PERMISSIONS if getattr(base, name)))
        self._last_snapshot = snapshot
        self._targets = {"r:" + str(role.id): role for role in roles}
        self._targets["m:" + str(bot.id)] = bot
        return snapshot

    async def fresh_actor(self, channel_id, user_id):
        guild = self.guild
        member, roles, channel = await asyncio.gather(
            self.api(guild.fetch_member(int(user_id))), self.api(guild.fetch_roles()),
            self.api(guild.fetch_channel(int(channel_id))),
        )
        base, role_ids = member_permissions(guild, member, roles)
        text = isinstance(channel, discord.TextChannel)
        permissions = effective_permissions(base, role_ids, member.id, guild.id, self._overwrites(channel, roles)) if text else base
        return ActorContext(str(guild.id), str(channel.id), str(member.id), frozenset(role_ids),
                            base.administrator, text, permissions.view_channel and permissions.use_application_commands)

    def overwrites(self, spec, snapshot, roles):
        records = {}
        records["r:" + snapshot.guild_id] = discord.PermissionOverwrite(view_channel=False)
        records["m:" + snapshot.bot_id] = discord.PermissionOverwrite(**{key: True for key in REQUIRED_BOT_PERMISSIONS}, use_application_commands=True)
        humans = {"m:" + identifier for identifier in snapshot.owner_members}
        if spec.key != "bot-settings":
            humans.update("r:" + identifier for identifier in roles)
        for identifier in humans:
            records[identifier] = discord.PermissionOverwrite(view_channel=True, read_message_history=True,
                                                              send_messages=False, use_application_commands=spec.key != "activity-logs")
        return tuple(sorted((key, value.pair()[0].value, value.pair()[1].value) for key, value in records.items()))

    async def provision(self, spec, action, parent_id, roles):
        snapshot = self._last_snapshot
        guild = self.guild
        targets = dict(self._targets)
        for identifier in {*snapshot.owner_members, snapshot.bot_id}:
            targets["m:" + identifier] = await self.api(guild.fetch_member(int(identifier)))
        desired = {targets[key]: discord.PermissionOverwrite.from_pair(discord.Permissions(allow), discord.Permissions(deny))
                   for key, allow, deny in self.overwrites(spec, snapshot, roles)}
        reason = "Mi Boti administrator-confirmed setup"
        if action["action"] == "CREATE":
            if spec.kind == "CATEGORY":
                channel = await self.api(guild.create_category(action["name"], overwrites=desired, reason=reason), mutation=True)
            else:
                category = await self.api(guild.fetch_channel(int(parent_id)))
                channel = await self.api(guild.create_text_channel(action["name"], category=category, overwrites=desired,
                                                                  topic="Mi Boti managed channel", reason=reason), mutation=True)
        else:
            channel = await self.api(guild.fetch_channel(int(action["remote_id"])))
            options = {"overwrites": desired, "reason": reason}
            if spec.kind == "TEXT":
                options["category"] = await self.api(guild.fetch_channel(int(parent_id)))
            await self.api(channel.edit(**options), mutation=True)
        return str(channel.id)

    async def panel_exists(self, channel_id, message_id):
        if not channel_id or not message_id:
            return False
        try:
            channel = await self.api(self.guild.fetch_channel(int(channel_id)))
            message = await self.api(channel.fetch_message(int(message_id)))
            return message.author.id == self.client.user.id
        except SetupError:
            return False

    async def publish_panel(self, key, channel_id, panel_id, revision, message_id, current):
        from .views import PanelView
        channel = await self.api(self.guild.fetch_channel(int(channel_id)))
        embed = discord.Embed(title={"guide": "Tool guide", "dashboard": "Mi Boti", "hunt_progress": "Hunt control", "usage": "AI connections", "settings": "Server setup"}[key],
                              description="Use assigned slash-command channels for discovery and reviewed website research. Source and access-policy gates apply. CRM, AI execution and hunting remain disabled. No outreach is sent automatically.",
                              color=0x4F9CF9)
        if key == "guide":
            from .guide import build_guide_embed
            embed = build_guide_embed(current, discovery_enabled=self.settings.safe_summary()["discovery_enabled"])
        embed.set_footer(text=f"Mi Boti panel {panel_id} · revision {revision}")
        view = PanelView(self.client, key, panel_id, revision, current)
        if message_id:
            message = await self.api(channel.fetch_message(int(message_id)))
            if message.author.id != self.client.user.id:
                raise SetupError("The stored panel message is not owned by this bot.")
            await self.api(message.edit(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()), mutation=True)
        else:
            message = await self.api(channel.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()), mutation=True)
        return str(message.id)
