"""Guild-scoped Discord application with no autonomous execution paths."""

import asyncio
import json
import logging
from typing import Literal

import discord
from discord import app_commands

from ..domain.discord import (
    COMMAND_CHANNELS, OUTPUT_DESTINATIONS, PANELS, ActorContext, DiscordPolicyError, SetupError, authorize,
)
from ..discovery.overpass import OverpassDiscoveryAdapter
from ..discovery.philippines_extract import PhilippinesExtractAdapter
from ..domain.errors import AppError
from ..domain.values import snowflake, utc_now
from ..jobs.discovery import (
    claim_discover_job,
    enqueue_manual_discovery,
    execute_manual_discovery_job,
    execute_manual_discovery_job_async,
)
from ..repositories import campaigns as campaign_repository
from ..repositories import discord as repository
from ..repositories.async_database import AsyncDatabase
from ..services.setup import SetupService
from .transport import DiscordPort
from .views import SetupConfirmation, PanelView

logger = logging.getLogger("mi_boti.discord")


class MiBotiClient(discord.Client):
    def __init__(self, settings, database, *, port_factory=DiscordPort, discovery_source_factory=None):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none(),
                         application_id=int(settings.application_id) if settings.application_id else None,
                         max_ratelimit_timeout=None)
        self.settings, self.database = settings, database
        self.tree = app_commands.CommandTree(self)
        self.port = port_factory(self, settings)
        self.setup_service = SetupService(database, self.port, settings)
        self.discovery_source_factory = discovery_source_factory or self._default_discovery_source
        self.tasks = set()
        self._register_commands()
        self.tree.on_error = self.command_error

    def _default_discovery_source(self):
        ext_cfg = self.settings.sources.get("philippines_extract")
        if ext_cfg and ext_cfg.get("enabled"):
            return PhilippinesExtractAdapter(self.settings.data_dir, ext_cfg)
        cfg = self.settings.sources.get("overpass")
        if cfg and cfg.get("enabled"):
            return OverpassDiscoveryAdapter(cfg)
        return None

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

    async def _validate_operational_resources(self, current, snapshot):
        if set(current["outputs"]) != set(OUTPUT_DESTINATIONS) or any(p["state"] != "ACTIVE" for p in current["panels"].values()) or set(current["panels"]) != set(PANELS):
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
            await self._validate_operational_resources(current, snapshot)
        return actor, current

    async def _fresh_job_authorized(self, payload: dict) -> bool:
        try:
            command_key = str(payload.get("command_key", "discover"))
            channel_id = str(payload.get("channel_id", ""))
            user_id = str(payload.get("actor_id", ""))
            fresh = await self.port.fresh_actor(channel_id, user_id)
            snapshot = await self.port.snapshot()
            latest = await self.database.call(repository.state)
            authorize(
                fresh,
                command_key,
                guild_id=self.settings.guild_id,
                owner_ids=self.settings.owner_ids,
                operator_roles=latest["roles"],
                config=latest["config"],
                mappings=latest["mappings"],
                snapshot=snapshot,
            )
            await self._validate_operational_resources(latest, snapshot)
            return True
        except Exception:
            return False

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
                  "", f"Operator role IDs: {', '.join(plan['roles']) or 'none (owners/administrators only)'}", "", "**Also included**: save missing command/output ID mappings and publish or update five panels, including the tool guide. Existing custom mappings are preserved unless this preview changes them."]
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
            elif command == "guide":
                from .guide import build_guide_embed
                await self.reply(interaction, embed=build_guide_embed(current, discovery_enabled=self.settings.safe_summary()["discovery_enabled"]))
            else:
                await self.reply(interaction, self.status_text(command))
        await self._safe(interaction, action)

    def status_text(self, command):
        if command in {"usage", "connections"}:
            return "No AI provider is verified or enabled. AGY allowance compatibility remains blocked; no capacity estimate is invented. No CLI task or paid API has been called."
        discovery = "Local snapshot discovery is enabled; use /discover in its assigned channel." if self.settings.safe_summary()["discovery_enabled"] else "Discovery is disabled until the approved local snapshot is prepared and enabled."
        return "Hunting is disabled and no hunt worker is running. " + discovery + " Live website research, scoring and CRM workflows are not implemented yet."

    @staticmethod
    def _role_ids(value):
        roles = [] if value.strip().lower() == "none" else [snowflake(v.strip()) for v in value.split(",")]
        if len(roles) != len(set(roles)) or len(roles) > 10:
            raise SetupError("Choose up to ten distinct operator role IDs.")
        return roles

    async def operation(self, interaction, command, *, action_name=None, key=None, value=None, options_dict=None):
        async def action():
            actor, current = await self._authorized(interaction, command, admin=command == "connections" and action_name == "verify")
            if command == "guide":
                from .guide import build_guide_embed
                await self.reply(interaction, embed=build_guide_embed(current, discovery_enabled=self.settings.safe_summary()["discovery_enabled"]))
                return
            if command == "config":
                if action_name == "view":
                    settings_json = json.loads(current["config"].get("settings_json") or "{}")
                    body = {"setup_state": current["config"]["setup_state"], "revision": current["config"]["revision"],
                            "active_campaign_id": settings_json.get("active_campaign_id"),
                            "command_channels": current["mappings"], "operator_role_ids": sorted(current["roles"]),
                            "ai_enabled": False, "hunting_enabled": False}
                    await self.reply(interaction, embed=discord.Embed(title="Mi Boti configuration", description="```json\n" + json.dumps(body, indent=2) + "\n```"))
                    return
                if action_name != "set" or key is None or value is None:
                    raise SetupError("Use /config view, or provide an allowed key and value for /config set.")
                if key == "active_campaign_id":
                    target_id = None if value.strip().lower() == "none" else value.strip()
                    await self.database.call(lambda db: campaign_repository.set_active_campaign(db, actor.user_id, target_id))
                    await self.reply(interaction, f"Active campaign updated to `{target_id or 'none'}`. " + self.status_text("hunt.status"))
                    return
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
                    raise SetupError("This phase supports active_campaign_id, operator_role_ids and command/output channel mappings. Other settings remain unavailable.")
                await self.show_preview(interaction, await self.setup_service.preview(actor, **options))
                return
            if command.startswith("campaign."):
                opts = options_dict or {}
                if command == "campaign.list":
                    page = opts.get("page") or 1
                    listing = await self.database.call(lambda db: campaign_repository.list_campaigns(db, page=page, page_size=self.settings.values["ui.page_size"]))
                    lines = [f"Page {listing['page']} · Total campaigns: {listing['total']}"]
                    for item in listing["items"]:
                        cats = ", ".join(item.config["target_categories"])
                        loc = item.config["geography"]["locality"]
                        lines.append(f"• `{item.id}` · **{discord.utils.escape_markdown(item.name)}** (v{item.current_version}, {item.state}) — {loc} [{cats}]")
                    await self.reply(interaction, "\n".join(lines))
                    return
                if command == "campaign.create":
                    cats = [c.strip() for c in (opts.get("categories") or "restaurant,cafe").split(",") if c.strip()]
                    try:
                        bbox = [float(x.strip()) for x in (opts.get("bbox") or "14.648,121.047,14.657,121.061").split(",")]
                    except ValueError:
                        from ..domain.campaigns import CampaignError
                        raise CampaignError("Geographic bbox must be four comma-separated numbers.") from None
                    cfg = {
                        "schema_version": 1,
                        "target_categories": cats,
                        "geography": {"country_code": "PH", "locality": opts.get("locality") or "Quezon City", "bbox": bbox},
                        "exclusions": [],
                        "provider_id": None,
                        "service_description": opts.get("service_description") or "",
                    }
                    created = await self.database.call(lambda db: campaign_repository.create_campaign(db, actor.user_id, opts.get("name") or "", cfg))
                    await self.reply(interaction, f"Saved **{discord.utils.escape_markdown(created.name)}** (v{created.current_version}). Campaign ID: `{created.id}`. " + self.status_text("hunt.status"))
                    return
                if command == "campaign.edit":
                    cfg = None
                    if opts.get("categories") or opts.get("bbox") or opts.get("locality") or opts.get("service_description") is not None:
                        existing = await self.database.call(lambda db: campaign_repository.get_campaign(db, opts.get("campaign_id") or ""))
                        cats = [c.strip() for c in opts["categories"].split(",") if c.strip()] if opts.get("categories") else existing.config["target_categories"]
                        try:
                            bbox = [float(x.strip()) for x in opts["bbox"].split(",")] if opts.get("bbox") else existing.config["geography"]["bbox"]
                        except ValueError:
                            from ..domain.campaigns import CampaignError
                            raise CampaignError("Geographic bbox must be four comma-separated numbers.") from None
                        loc = opts.get("locality") or existing.config["geography"]["locality"]
                        desc = opts["service_description"] if opts.get("service_description") is not None else existing.config["service_description"]
                        cfg = {
                            "schema_version": 1,
                            "target_categories": cats,
                            "geography": {"country_code": "PH", "locality": loc, "bbox": bbox},
                            "exclusions": existing.config["exclusions"],
                            "provider_id": None,
                            "service_description": desc,
                            "rubric": existing.config["rubric"],
                        }
                    updated = await self.database.call(
                        lambda db: campaign_repository.edit_campaign(
                            db,
                            actor.user_id,
                            opts.get("campaign_id") or "",
                            expected_version=opts.get("expected_version") or 0,
                            name=opts.get("name"),
                            config=cfg,
                            archive=bool(opts.get("archive", False)),
                        )
                    )
                    await self.reply(interaction, f"Updated campaign `{updated.id}` (**{discord.utils.escape_markdown(updated.name)}**, v{updated.current_version}, {updated.state}).")
                    return
            if command == "discover":
                opts = options_dict or {}
                if opts.get("job_id"):
                    if opts.get("campaign_id") is not None or opts.get("limit") is not None:
                        raise SetupError("Use job_id alone with optional page to view saved results; omit campaign_id and limit.")
                    from .discovery_results import show_results
                    await show_results(self, interaction, opts["job_id"], opts.get("page", 1))
                    return
                source_adapter = self.discovery_source_factory()
                if source_adapter is None:
                    from ..discovery.overpass import SourcePolicyError
                    raise SourcePolicyError("Prepare and enable the approved local source in config.toml under [sources.philippines_extract]. No job was enqueued.")
                target_campaign_id = opts.get("campaign_id")
                if not target_campaign_id:
                    active_camp = await self.database.call(campaign_repository.get_active_campaign)
                    if active_camp is None:
                        from ..domain.campaigns import CampaignError
                        raise CampaignError("Specify `campaign_id` or set `active_campaign_id` via `/config set`.")
                    target_campaign_id = active_camp.id
                limit_val = opts.get("limit") if opts.get("limit") is not None else self.settings.values["discovery.manual_default_limit"]
                if type(limit_val) is not int or not 1 <= limit_val <= self.settings.values["discovery.manual_max_limit"]:
                    from ..jobs.discovery import JobSchedulerError
                    raise JobSchedulerError(f"Manual discovery limit must be between 1 and {self.settings.values['discovery.manual_max_limit']}.")
                idemp_key = f"discover:interaction:{getattr(interaction, 'id', target_campaign_id + ':' + utc_now())}"
                enqueued = await self.database.call(
                    lambda db: enqueue_manual_discovery(
                        db,
                        actor_id=actor.user_id,
                        guild_id=actor.guild_id,
                        channel_id=actor.channel_id,
                        idempotency_key=idemp_key,
                        campaign_id=target_campaign_id,
                        limit=limit_val,
                        max_attempts=self.settings.values["jobs.max_attempts"],
                    )
                )
                await self.reply(
                    interaction,
                    f"Discovery job `{enqueued['id']}` queued for campaign `{target_campaign_id}` (limit {limit_val}). Running in background; no AI or hunting is invoked.",
                )
                async def run_discover_worker():
                    try:
                        active_src_cfg = (
                            getattr(source_adapter, "policy", None)
                            or self.settings.sources.get("philippines_extract")
                            or self.settings.sources.get("overpass")
                            or {}
                        )
                        max_daily = int(active_src_cfg.get("max_requests_per_day", 100))
                        max_attempts_q = min(
                            int(active_src_cfg.get("max_attempts", 3)),
                            self.settings.values["jobs.max_attempts"],
                        )
                        claimed = await self.database.call(
                            lambda db: claim_discover_job(
                                db,
                                enqueued["id"],
                                lease_seconds=self.settings.values["jobs.lease_seconds"],
                                max_concurrency=self.settings.values["jobs.max_concurrency"],
                                manual_max_age_seconds=self.settings.values["jobs.manual_max_age_seconds"],
                            )
                        )
                        if claimed is None:
                            return
                        done_job = await execute_manual_discovery_job_async(
                            self.database,
                            claimed,
                            source_adapter,
                            authorize_dispatch=self._fresh_job_authorized,
                            lease_seconds=self.settings.values["jobs.lease_seconds"],
                            heartbeat_seconds=self.settings.values["jobs.heartbeat_seconds"],
                            max_job_requests=self.settings.values["hunt.base_discovery_requests"],
                            max_requests_per_day=max_daily,
                            max_attempts_per_query=max_attempts_q,
                            manual_max_age_seconds=self.settings.values["jobs.manual_max_age_seconds"],
                            coverage_ttl_seconds=self.settings.values["discovery.coverage_ttl_seconds"],
                            similarity_threshold=self.settings.values["discovery.similarity_review_threshold"],
                        )
                        if done_job is not None:
                            prog = json.loads(done_job["progress_json"] or "{}")
                            summary = (
                                f"Discovery job `{done_job['id']}` finished with state `{done_job['state']}`"
                                + (f" (`{done_job['error_code']}`)" if done_job.get("error_code") else "")
                                + f" · requests={prog.get('discovery_requests', 0)}, seen={prog.get('seen', 0)}, "
                                f"new={prog.get('new', 0)}, existing={prog.get('existing', 0)}, "
                                f"ambiguous={prog.get('ambiguous', 0)}, invalid={prog.get('invalid', 0)}."
                            )
                            await self.reply(interaction, summary)
                            from .discovery_results import show_results
                            await show_results(self, interaction, done_job["id"])
                    except discord.HTTPException:
                        logger.warning("Discovery completion receipt could not be sent; job state is persisted in SQLite.")
                task = asyncio.create_task(run_discover_worker(), name="mi-boti-discover-" + enqueued["id"])
                self.tasks.add(task)
                task.add_done_callback(self._setup_done)
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
        async def guide(interaction: discord.Interaction):
            await self.operation(interaction, "guide")
        self.tree.add_command(app_commands.Command(name="guide", description="Learn each tool, its channel, usage and availability", callback=guide), guild=guild)
        async def connections(interaction: discord.Interaction, action: Literal["status", "verify"] = "status"):
            await self.operation(interaction, "connections", action_name=action)
        self.tree.add_command(app_commands.Command(name="connections", description="Inspect unavailable AI connections; verification remains gated", callback=connections), guild=guild)
        hunt_group = app_commands.Group(name="hunt", description="Mi Boti hunt controls (execution disabled)")
        for action in ("start", "pause", "resume", "stop", "status"):
            hunt_group.add_command(self._placeholder(action, f"hunt.{action}"))
        self.tree.add_command(hunt_group, guild=guild)
        campaign_group = app_commands.Group(name="campaign", description="Mi Boti non-AI campaign management")
        async def campaign_create(interaction: discord.Interaction, name: str, locality: str = "Quezon City",
                                  categories: str = "restaurant,cafe", bbox: str = "14.648,121.047,14.657,121.061",
                                  service_description: str = ""):
            await self.operation(interaction, "campaign.create", options_dict={
                "name": name, "locality": locality, "categories": categories, "bbox": bbox, "service_description": service_description,
            })
        async def campaign_list(interaction: discord.Interaction, page: int = 1):
            await self.operation(interaction, "campaign.list", options_dict={"page": page})
        async def campaign_edit(interaction: discord.Interaction, campaign_id: str, expected_version: int,
                                name: str | None = None, locality: str | None = None, categories: str | None = None,
                                bbox: str | None = None, service_description: str | None = None, archive: bool = False):
            await self.operation(interaction, "campaign.edit", options_dict={
                "campaign_id": campaign_id, "expected_version": expected_version, "name": name,
                "locality": locality, "categories": categories, "bbox": bbox,
                "service_description": service_description, "archive": archive,
            })
        campaign_group.add_command(app_commands.Command(name="create", description="Create a versioned non-AI PH campaign", callback=campaign_create))
        campaign_group.add_command(app_commands.Command(name="list", description="List campaigns in this deployment", callback=campaign_list))
        campaign_group.add_command(app_commands.Command(name="edit", description="Update or archive a campaign with version check", callback=campaign_edit))
        self.tree.add_command(campaign_group, guild=guild)
        async def discover(interaction: discord.Interaction, campaign_id: str | None = None, limit: int | None = None,
                           job_id: str | None = None, page: int = 1):
            await self.operation(interaction, "discover", options_dict={"campaign_id": campaign_id, "limit": limit, "job_id": job_id, "page": page})
        self.tree.add_command(app_commands.Command(name="discover", description="Run bounded non-AI business discovery for an approved campaign", callback=discover), guild=guild)
        async def lead(interaction: discord.Interaction, id: str | None = None, page: int = 1,
                       action: Literal["inspect", "link", "separate"] = "inspect",
                       target: str | None = None, rationale: str | None = None):
            from .identity import lead as show_lead
            await show_lead(self, interaction, identifier=id, page=page, action=action, target=target, rationale=rationale)
        self.tree.add_command(app_commands.Command(name="lead", description="Inspect registry records and confirm identity reviews", callback=lead), guild=guild)
        for key in COMMAND_CHANNELS:
            if "." not in key and key not in {"guide", "setup", "config", "connections", "discover", "lead"}:
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
