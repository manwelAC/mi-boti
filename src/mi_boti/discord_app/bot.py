"""Guild-scoped Discord application with no autonomous execution paths."""

import asyncio
import json
import logging
from typing import Literal

import discord
from discord import app_commands

from ..domain.discord import (
    COMMAND_CHANNELS, OUTPUT_DESTINATIONS, ActorContext, DiscordPolicyError, SetupError, authorize,
)
from ..domain.errors import AppError
from ..domain.values import snowflake, utc_now
from ..repositories import discord as repository
from ..repositories.async_database import AsyncDatabase
from ..services.setup import SetupService
from .transport import DiscordPort
from .views import SetupConfirmation, PanelView

logger = logging.getLogger("mi_boti.discord")


class MiBotiClient(discord.Client):
    def __init__(self, settings, database, *, port_factory=DiscordPort):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none(),
                         application_id=int(settings.application_id) if settings.application_id else None,
                         max_ratelimit_timeout=None)
        self.settings, self.database = settings, database
        self.tree = app_commands.CommandTree(self)
        self.port = port_factory(self, settings)
        self.setup_service = SetupService(database, self.port, settings)
        self.tasks = set()
        self._register_commands()
        self.tree.on_error = self.command_error

    async def acknowledge(self, interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

    async def reply(self, interaction, text=None, *, embed=None, view=None):
        options = {"ephemeral": True, "allowed_mentions": discord.AllowedMentions.none()}
        if embed is not None:
            options["embed"] = embed
        if view is not None:
            options["view"] = view
        await interaction.followup.send(content=text, **options)

    async def _authorized(self, interaction, command, *, admin=False):
        if str(interaction.guild_id) != self.settings.guild_id or not isinstance(interaction.channel, discord.TextChannel):
            raise DiscordPolicyError("Use a text channel in the configured Discord server.")
        actor = await self.port.fresh_actor(str(interaction.channel_id), str(interaction.user.id))
        snapshot = await self.port.snapshot()
        current = await self.database.call(repository.state)
        authorize(actor, command, guild_id=self.settings.guild_id, owner_ids=self.settings.owner_ids,
                  operator_roles=current["roles"], config=current["config"], mappings=current["mappings"],
                  snapshot=snapshot, admin_action=admin)
        # Deny operational commands when any configured output or panel is missing.
        if command != "setup":
            if set(current["outputs"]) != set(OUTPUT_DESTINATIONS) or any(p["state"] != "ACTIVE" for p in current["panels"].values()) or len(current["panels"]) != 4:
                raise DiscordPolicyError("Configuration is incomplete; ask an administrator to run /setup.")
            from ..domain.discord import RESOURCES
            if set(current["resources"]) != set(RESOURCES):
                raise DiscordPolicyError("Configuration is incomplete; ask an administrator to run /setup.")
            for key, resource in current["resources"].items():
                remote = snapshot.channel(resource["discord_id"])
                if resource["state"] != "ACTIVE" or remote is None or remote.overwrites != self.port.overwrites(RESOURCES[key], snapshot, current["roles"]):
                    raise DiscordPolicyError("Managed channels or permissions changed; ask an administrator to run /setup.")
            resources_by_id = {resource["id"]: resource for resource in current["resources"].values()}
            panel_checks = [self.port.panel_exists(resources_by_id[panel["resource_id"]]["discord_id"], panel["message_id"])
                            for panel in current["panels"].values()]
            if not all(await asyncio.gather(*panel_checks)):
                raise DiscordPolicyError("A control panel is missing or inaccessible; ask an administrator to run /setup.")
        return actor, current

    async def _safe(self, interaction, action):
        await self.acknowledge(interaction)
        try:
            await action()
        except AppError as error:
            await self.audit_rejection(interaction, error.code)
            await self.reply(interaction, str(error))
        except Exception as error:
            await self.audit_rejection(interaction, "UNEXPECTED_FAILURE")
            logger.error("Discord action failed (%s); no raw interaction or credential logged.", type(error).__name__)
            await self.reply(interaction, "The action failed safely. Check local logs and retry; no autonomous work was started.")

    async def audit_rejection(self, interaction, code):
        try:
            actor_id = snowflake(str(interaction.user.id))
            await self.database.call(lambda db: repository.audit(db.connection, actor_id, "discord.action_rejected", "DENIED", details={"code": code}))
        except Exception as error:
            logger.warning("Could not persist a denial audit (%s); no raw interaction logged.", type(error).__name__)

    async def command_error(self, interaction, error):
        await self.acknowledge(interaction)
        await self.audit_rejection(interaction, "ARGUMENT_OR_COMMAND_ERROR")
        logger.error("Application command rejected (%s).", type(error).__name__)
        await self.reply(interaction, "The command was rejected. Check its arguments and use the configured channel.")

    async def preview_setup(self, interaction, *, resource_key=None, resource_id=None, resolution="inspect", operator_roles=None):
        async def action():
            actor, _ = await self._authorized(interaction, "setup")
            adoptions = {}
            if resource_id:
                if not resource_key:
                    raise SetupError("Adoption requires both a resource key and an existing channel/category ID.")
                adoptions[resource_key] = snowflake(resource_id)
            roles = None if operator_roles is None else self._role_ids(operator_roles)
            plan = await self.setup_service.preview(actor, roles=roles, adoptions=adoptions,
                                                    recreate=(resource_key,) if resource_key and resolution == "recreate" else ())
            await self.show_preview(interaction, plan)
        await self._safe(interaction, action)

    async def show_preview(self, interaction, plan):
        lines = ["**Nothing changes until you confirm.**", "", "**Managed resource plan**"]
        lines += [f"• {a['action']}: {discord.utils.escape_mentions(discord.utils.escape_markdown(a['name'])).replace(chr(10), ' ')} (`{a['key']}` · ID {a['remote_id'] or 'new'})" for a in plan["actions"]]
        lines += ["", "**Permission policy**", "@everyone cannot view managed channels. Owners/administrators can manage the bot; selected operators can view/use assigned command channels. Human text sending is disabled. bot-settings stays administrator-only.",
                  "", f"Operator role IDs: {', '.join(plan['roles']) or 'none (owners/administrators only)'}", "", "**Also included**: save missing command/output ID mappings and publish or update four control panels. Existing custom mappings are preserved unless this preview changes them."]
        for kind in ("command_overrides", "output_overrides"):
            lines += [f"• {key} → {value}" for key, value in plan[kind].items()]
        if plan["warnings"]:
            lines += ["", "**Review carefully**", *plan["warnings"]]
        if plan["blockers"]:
            lines += ["", "**Blocked — do not confirm**", *plan["blockers"]]
        description = "\n".join(lines)
        # Keep every proposed change reviewable; split rather than truncate.
        chunks = []
        while description:
            at = min(3500, len(description))
            if at < len(description):
                at = description.rfind("\n", 0, at) or at
            chunks.append(description[:at])
            description = description[at:].lstrip("\n")
        for index, chunk in enumerate(chunks):
            embed = discord.Embed(title="Mi Boti setup preview" if index == 0 else "Setup preview (continued)", description=chunk, color=0x4F9CF9)
            embed.set_footer(text=f"Plan {plan['id']} · expires {plan['expires_at']}")
            view = SetupConfirmation(self, plan["id"], plan["hash"]) if index == len(chunks) - 1 else None
            await self.reply(interaction, embed=embed, view=view)

    async def confirm_setup(self, interaction, plan_id, digest, *, cancel=False):
        async def action():
            def origin(db):
                row = db.connection.execute("SELECT plan_json FROM setup_plans WHERE id=?", (plan_id,)).fetchone()
                return json.loads(row[0]).get("command_key", "setup") if row else "setup"
            command = await self.database.call(origin)
            actor, _ = await self._authorized(interaction, command)
            plan = await self.setup_service.claim(actor, plan_id, digest, cancel=cancel)
            if plan is None:
                await self.reply(interaction, "Setup preview cancelled. Nothing was provisioned.")
                return
            async def work():
                result = await self.setup_service.apply(plan, actor)
                try:
                    await self.reply(interaction, result)
                except discord.HTTPException:
                    logger.warning("Setup receipt could not be delivered; inspect the persisted setup plan.")
            task = asyncio.create_task(work(), name="mi-boti-setup-" + plan_id)
            self.tasks.add(task)
            task.add_done_callback(self._setup_done)
            try:
                await self.reply(interaction, f"Setup job `{plan_id}` confirmed. Provisioning runs outside the interaction handler; hunting remains disabled.")
            except discord.HTTPException:
                logger.warning("Setup receipt was unavailable; the explicitly confirmed job remains tracked.")
        await self._safe(interaction, action)

    def _setup_done(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Setup worker ended unexpectedly (%s).", type(task.exception()).__name__)

    async def panel_action(self, interaction, command, panel_id, revision):
        async def action():
            actor, current = await self._authorized(interaction, command)
            panel = next((p for p in current["panels"].values() if p["id"] == panel_id), None)
            message = getattr(interaction, "message", None)
            if panel is None or panel["revision"] != revision or panel["state"] != "ACTIVE" or not message or str(message.id) != panel["message_id"]:
                raise SetupError("This panel is stale; use the current channel panel or slash command.")
            if command == "setup":
                await self.show_preview(interaction, await self.setup_service.preview(actor))
            else:
                await self.reply(interaction, self.status_text(command))
        await self._safe(interaction, action)

    @staticmethod
    def status_text(command):
        if command in {"usage", "connections"}:
            return "No AI provider is verified or enabled. AGY allowance compatibility remains blocked; no capacity estimate is invented. No CLI task or paid API has been called."
        return "Hunting is disabled and no hunt worker is running. Discovery, research, scoring and CRM workflows are not implemented yet."

    @staticmethod
    def _role_ids(value):
        roles = [] if value.strip().lower() == "none" else [snowflake(v.strip()) for v in value.split(",")]
        if len(roles) != len(set(roles)) or len(roles) > 10:
            raise SetupError("Choose up to ten distinct operator role IDs.")
        return roles

    async def operation(self, interaction, command, *, action_name=None, key=None, value=None):
        async def action():
            actor, current = await self._authorized(interaction, command, admin=command == "connections" and action_name == "verify")
            if command == "config":
                if action_name == "view":
                    body = {"setup_state": current["config"]["setup_state"], "revision": current["config"]["revision"],
                            "command_channels": current["mappings"], "operator_role_ids": sorted(current["roles"]),
                            "ai_enabled": False, "hunting_enabled": False}
                    await self.reply(interaction, embed=discord.Embed(title="Mi Boti configuration", description="```json\n" + json.dumps(body, indent=2) + "\n```"))
                    return
                if action_name != "set" or key is None or value is None:
                    raise SetupError("Use /config view, or provide an allowed key and value for /config set.")
                options = {"command_key": "config"}
                if key == "operator_role_ids":
                    options["roles"] = self._role_ids(value)
                elif key.startswith(("command_channel.", "output_destination.")):
                    prefix, setting = key.split(".", 1)
                    selected_id = snowflake(value)
                    resource = next((k for k, r in current["resources"].items() if r["discord_id"] == selected_id and r["kind"] == "TEXT" and r["state"] == "ACTIVE"), None)
                    if resource is None:
                        raise SetupError("Select an active managed text-channel ID; unrelated channels are not adopted silently.")
                    options["command_overrides" if prefix == "command_channel" else "output_overrides"] = {setting: resource}
                else:
                    raise SetupError("This phase supports operator_role_ids and command/output channel mappings. Other settings remain unavailable.")
                await self.show_preview(interaction, await self.setup_service.preview(actor, **options))
                return
            if command in {"usage", "hunt.status"} or (command == "connections" and action_name == "status"):
                await self.reply(interaction, self.status_text(command))
                return
            await self.reply(interaction, "This workflow is not implemented or enabled in Phase 2. Authorization was checked; no job, CLI task, source request or outreach was started.")
        await self._safe(interaction, action)

    def _register_commands(self):
        guild = discord.Object(id=int(self.settings.guild_id))
        async def setup(interaction: discord.Interaction, resource_key: str | None = None, resource_id: str | None = None,
                        resolution: Literal["inspect", "recreate"] = "inspect", operator_roles: str | None = None):
            await self.preview_setup(interaction, resource_key=resource_key, resource_id=resource_id, resolution=resolution, operator_roles=operator_roles)
        self.tree.add_command(app_commands.Command(name="setup", description="Preview administrator-confirmed Mi Boti setup or recovery", callback=setup), guild=guild)
        async def config(interaction: discord.Interaction, action: Literal["view", "set"], key: str | None = None, value: str | None = None):
            await self.operation(interaction, "config", action_name=action, key=key, value=value)
        self.tree.add_command(app_commands.Command(name="config", description="Inspect settings or preview approved mapping/role changes", callback=config), guild=guild)
        async def connections(interaction: discord.Interaction, action: Literal["status", "verify"] = "status"):
            await self.operation(interaction, "connections", action_name=action)
        self.tree.add_command(app_commands.Command(name="connections", description="Inspect unavailable AI connections; verification remains gated", callback=connections), guild=guild)
        for group_name, actions in (("hunt", ("start", "pause", "resume", "stop", "status")), ("campaign", ("create", "list", "edit"))):
            group = app_commands.Group(name=group_name, description=f"Mi Boti {group_name} controls (execution disabled)")
            for action in actions:
                command_key = f"{group_name}.{action}"
                # app_commands derives options from the signature. Bind the key
                # in a closure factory, not a hidden default parameter.
                group.add_command(self._placeholder(action, command_key))
            self.tree.add_command(group, guild=guild)
        for key in COMMAND_CHANNELS:
            if "." not in key and key not in {"setup", "config", "connections"}:
                self.tree.add_command(self._placeholder(key, key), guild=guild)

    def _placeholder(self, name, key):
        async def callback(interaction: discord.Interaction):
            await self.operation(interaction, key)
        return app_commands.Command(name=name, description=f"Mi Boti {name}: authorization enforced; later workflow gated", callback=callback)

    async def restore_views(self):
        current = await self.database.call(repository.state)
        for key, panel in current["panels"].items():
            if panel["state"] == "ACTIVE" and panel["message_id"]:
                self.add_view(PanelView(self, key, panel["id"], panel["revision"], current), message_id=int(panel["message_id"]))
        rows = await self.database.call(lambda db: [dict(row) for row in db.connection.execute("SELECT id,plan_hash FROM setup_plans WHERE state='PREVIEW' AND expires_at>?", (utc_now(),))])
        for row in rows:
            self.add_view(SetupConfirmation(self, row["id"], row["plan_hash"]))

    async def setup_hook(self):
        info = await asyncio.wait_for(self.application_info(), timeout=15)
        if self.settings.application_id and str(info.id) != self.settings.application_id:
            raise SetupError("The token belongs to a different application; no commands were synchronized.")
        await self.database.call(repository.recover_setup)
        await self.restore_views()
        await asyncio.wait_for(self.tree.sync(guild=discord.Object(id=int(self.settings.guild_id))), timeout=60)

    async def on_ready(self):
        logger.info("Discord gateway ready; no setup, discovery or hunt is started automatically.")

    async def close(self):
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await super().close()


async def run_bot(settings, database_path):
    settings.require_identity(token=True)
    database = AsyncDatabase(database_path, busy_timeout_ms=settings.values["runtime.sqlite_busy_timeout_ms"])
    try:
        async with MiBotiClient(settings, database) as client:
            await client.start(settings.discord_token)
    except discord.LoginFailure:
        raise SetupError("Discord rejected the token. Configure the regenerated bot token locally.") from None
    except (discord.Forbidden, discord.NotFound):
        raise SetupError("The bot cannot access the configured server. Check its invitation, application identity and permissions.") from None
    except (discord.HTTPException, discord.RateLimited, OSError, asyncio.TimeoutError):
        raise SetupError("Discord is unavailable. Startup stopped without provisioning resources or starting a hunt.") from None
    finally:
        await database.close()
