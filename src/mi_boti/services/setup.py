"""Actor-bound setup previews and bounded, journaled provisioning."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

from ..domain.discord import (
    RESOURCES, PANELS, REQUIRED_BOT_PERMISSIONS, OUTPUT_PERMISSIONS,
    SetupError, UncertainOperation, require_actor,
)
from ..domain.values import utc_now
from ..repositories import discord as repository


class SetupService:
    def __init__(self, database, port, settings):
        self.database, self.port, self.settings = database, port, settings
        self._apply_lock = asyncio.Lock()

    async def preview(self, actor, *, roles=None, adoptions=None, recreate=(), command_overrides=None, output_overrides=None, command_key="setup"):
        snapshot = await self.port.snapshot()
        require_actor(actor, self.settings.guild_id, self.settings.owner_ids, administrator=True)
        if command_key not in {"setup", "config"}:
            raise SetupError("Unsupported setup preview origin.")
        if actor.user_id in self.settings.owner_ids and actor.user_id not in snapshot.owner_members:
            raise SetupError("The requesting owner could not be verified as a current server member.")
        if snapshot.guild_id != self.settings.guild_id:
            raise SetupError("The bot is connected to a different server.")
        if not REQUIRED_BOT_PERMISSIONS <= snapshot.bot_permissions:
            missing = ", ".join(sorted(REQUIRED_BOT_PERMISSIONS - snapshot.bot_permissions))
            raise SetupError("The bot needs these permissions before setup: " + missing)
        await self.database.call(lambda db: repository.mark_missing(db, snapshot))
        current = await self.database.call(repository.state)
        roles = sorted(current["roles"] if roles is None else set(roles))
        if len(roles) > 10 or len(self.settings.owner_ids) > 10:
            raise SetupError("Setup supports at most ten owner IDs and ten operator roles.")
        if any(role not in snapshot.role_ids or role == snapshot.guild_id for role in roles):
            raise SetupError("Select valid operator roles from this server; @everyone is not allowed.")
        adoptions, command_overrides, output_overrides = adoptions or {}, command_overrides or {}, output_overrides or {}
        if set(adoptions) - set(RESOURCES) or set(recreate) - (set(RESOURCES) | {"panel." + p for p in PANELS}):
            raise SetupError("Unknown setup resource key.")
        from ..domain.discord import COMMAND_CHANNELS, OUTPUT_DESTINATIONS
        if set(command_overrides) - set(COMMAND_CHANNELS) or set(output_overrides) - set(OUTPUT_DESTINATIONS):
            raise SetupError("Unknown command or destination key.")
        if any(value not in RESOURCES or RESOURCES[value].kind != "TEXT" for value in [*command_overrides.values(), *output_overrides.values()]):
            raise SetupError("Mappings must select a managed text-channel resource key.")
        plan_id = str(uuid4())
        actions, warnings, blockers = [], [], []
        planned_ids = {key: row["discord_id"] for key, row in current["resources"].items()}
        planned_ids.update(adoptions)
        managed_ids = set(planned_ids.values()) - {None}
        for spec in RESOURCES.values():
            old = current["resources"].get(spec.key)
            remote = snapshot.channel(planned_ids.get(spec.key))
            desired = self.port.overwrites(spec, snapshot, roles)
            if remote is not None and remote.kind != spec.kind:
                blockers.append(f"{spec.key}: stored/selected resource has the wrong channel type.")
                continue
            if spec.key in adoptions:
                if remote is None:
                    raise SetupError("An adoption ID does not exist in this server.")
                if any(row["discord_id"] == remote.id and key != spec.key for key, row in current["resources"].items()):
                    raise SetupError("The selected ID already belongs to a different managed resource.")
                action = "ADOPT"
                warnings.append(f"Explicit adoption: {spec.key} will manage ID {remote.id} and replace its overwrites.")
            elif old and old["state"] == "UNCERTAIN" and remote is None and spec.key not in recreate:
                blockers.append(f"{spec.key}: inspect the prior creation; explicitly adopt its ID or confirm recreation.")
                continue
            elif remote is None:
                action = "CREATE"
                if old:
                    warnings.append(f"Approved recovery will replace missing resource {spec.key}; no automatic recreation occurred.")
                if spec.key in recreate:
                    warnings.append(f"You asserted the uncertain {spec.key} creation is absent and requested recreation.")
            else:
                parent = planned_ids.get(spec.parent) if spec.parent else None
                action = "KEEP" if old and old["state"] == "ACTIVE" and remote.overwrites == desired and remote.parent_id == parent and (not spec.parent or parent is not None) else "UPDATE"
            if remote and spec.kind == "CATEGORY" and action != "KEEP":
                if any(c.parent_id == remote.id and c.id not in managed_ids for c in snapshot.channels):
                    blockers.append(f"{spec.key}: category contains unmanaged channels; move them out before changing category permissions.")
            name = remote.name if remote else spec.name
            if remote is None and any(c.name == name for c in snapshot.channels):
                name = f"{spec.name}-mi-boti-{plan_id[:8]}"
                warnings.append(f"Name conflict for {spec.key}: create {name}; unrelated resources remain untouched.")
            actions.append(dict(key=spec.key, action=action, name=name, remote_id=remote.id if remote else None))
        panel_actions = []
        for key, resource_key in PANELS.items():
            panel = current["panels"].get(key)
            present = bool(panel and panel["message_id"] and await self.port.panel_exists(planned_ids.get(resource_key), panel["message_id"]))
            if panel and panel["state"] == "UNCERTAIN" and not present and "panel." + key not in recreate:
                blockers.append(f"panel.{key}: inspect the prior message before explicitly requesting recreation.")
            panel_actions.append({"key": key, "resource_key": resource_key, "present": present})
        plan = {
            "id": plan_id, "actor_id": actor.user_id, "guild_id": snapshot.guild_id, "channel_id": actor.channel_id, "command_key": command_key,
            "revision": current["config"]["revision"], "snapshot": snapshot.fingerprint(), "roles": roles,
            "actions": actions, "panels": panel_actions, "warnings": warnings, "blockers": blockers,
            "command_overrides": command_overrides, "output_overrides": output_overrides,
        }
        encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        expiry = (datetime.now(timezone.utc) + timedelta(seconds=self.settings.values["ui.setup_confirmation_ttl_seconds"])).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        def save(db):
            with db.transaction() as c:
                c.execute("INSERT INTO guild_config VALUES ('guild',?,'UNCONFIGURED',1,'{}',?) ON CONFLICT(id) DO NOTHING", (snapshot.guild_id, utc_now()))
                revision = c.execute("SELECT revision FROM guild_config").fetchone()[0]
                # First configuration starts at revision 1, before this preview.
                if current["config"]["revision"] == 0:
                    plan["revision"] = revision
                actual_encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"))
                actual_hash = hashlib.sha256(actual_encoded.encode()).hexdigest()
                c.execute("INSERT INTO setup_plans VALUES (?,?,?,?,?,?,'PREVIEW',?)", (plan_id, snapshot.guild_id, actor.user_id, actual_encoded, actual_hash, expiry, utc_now()))
                repository.audit(c, actor.user_id, "setup.preview", "SUCCESS", plan_id)
                return actual_hash
        digest = await self.database.call(save)
        return {**plan, "hash": digest, "expires_at": expiry}

    async def claim(self, actor, plan_id, digest, *, cancel=False):
        require_actor(actor, self.settings.guild_id, self.settings.owner_ids, administrator=True)
        snapshot = await self.port.snapshot()
        def claim(db):
            with db.transaction() as c:
                row = c.execute("SELECT * FROM setup_plans WHERE id=?", (plan_id,)).fetchone()
                if row is None or row["actor_id"] != actor.user_id or row["guild_id"] != actor.guild_id:
                    raise SetupError("This setup confirmation belongs to another user or server.")
                plan = json.loads(row["plan_json"])
                if actor.channel_id != plan["channel_id"] or row["plan_hash"] != digest:
                    raise SetupError("This setup confirmation is invalid or in the wrong channel.")
                if cancel:
                    if row["state"] != "PREVIEW":
                        raise SetupError("Only a pending preview can be cancelled.")
                    c.execute("UPDATE setup_plans SET state='EXPIRED' WHERE id=?", (plan_id,))
                    repository.audit(c, actor.user_id, "setup.cancel", "SUCCESS", plan_id)
                    return None
                if row["state"] != "PREVIEW" or row["expires_at"] <= utc_now():
                    raise SetupError("This preview was already used or expired; run /setup again.")
                config = c.execute("SELECT revision FROM guild_config").fetchone()
                if config[0] != plan["revision"] or snapshot.fingerprint() != plan["snapshot"]:
                    raise SetupError("Permissions, resources or configuration changed; request a new preview.")
                if plan["blockers"]:
                    raise SetupError("Resolve the listed setup blockers before confirming.")
                if c.execute("SELECT 1 FROM setup_plans WHERE state IN ('CONFIRMED','APPLYING')").fetchone():
                    raise SetupError("Another setup is already running; wait for its result.")
                c.execute("UPDATE setup_plans SET state='CONFIRMED' WHERE id=?", (plan_id,))
                c.execute("UPDATE guild_config SET setup_state='PARTIAL',revision=revision+1,updated_at=?", (utc_now(),))
                repository.audit(c, actor.user_id, "setup.confirm", "SUCCESS", plan_id)
                return plan
        return await self.database.call(claim)

    async def apply(self, plan, actor):
        """Only a claimed durable plan is admitted; never runs on startup."""
        async with self._apply_lock:
            def admitted(db):
                row = db.connection.execute("SELECT state,plan_json FROM setup_plans WHERE id=?", (plan["id"],)).fetchone()
                if row is None or row["state"] != "CONFIRMED" or json.loads(row["plan_json"]) != plan:
                    raise SetupError("No confirmed setup job matches this request.")
            await self.database.call(admitted)
            try:
                await asyncio.wait_for(self._apply(plan, actor), timeout=180)
                return "Setup completed. Managed channels, ID mappings and controls are saved. Hunting remains disabled."
            except (Exception, asyncio.CancelledError) as error:
                def fail(db):
                    with db.transaction() as c:
                        c.execute("UPDATE setup_plans SET state='PARTIAL' WHERE id=?", (plan["id"],))
                        c.execute("UPDATE guild_config SET setup_state='PARTIAL',updated_at=?", (utc_now(),))
                        c.execute("UPDATE setup_steps SET state='UNCERTAIN',error_code='INTERRUPTED_OR_UNCERTAIN',updated_at=? WHERE plan_id=? AND state='APPLYING'", (utc_now(), plan["id"]))
                        repository.audit(c, actor.user_id, "setup.partial", "FAILED", plan["id"])
                await self.database.call(fail)
                if isinstance(error, asyncio.CancelledError):
                    raise
                detail = f" {error}" if isinstance(error, SetupError) else ""
                return "Setup is partial. Completed resources were retained." + detail + " Check bot permissions and run /setup for a new recovery preview; inspect any uncertain resource before recreating it."

    async def _step(self, plan_id, key, status, remote_id=None, error=None):
        def save(db):
            with db.transaction() as c:
                c.execute("INSERT INTO setup_steps VALUES (?,?,?,?,?,?,?) ON CONFLICT(plan_id,step_key) DO UPDATE SET state=excluded.state,discord_id=excluded.discord_id,error_code=excluded.error_code,updated_at=excluded.updated_at",
                          (str(uuid4()), plan_id, key, status, remote_id, error, utc_now()))
        await self.database.call(save)

    async def _apply(self, plan, actor):
        # Reject direct, forged, expired or stale work even if a caller skips claim().
        fresh = await self.port.fresh_actor(actor.channel_id, actor.user_id)
        require_actor(fresh, self.settings.guild_id, self.settings.owner_ids, administrator=True)
        snapshot = await self.port.snapshot()
        if snapshot.fingerprint() != plan["snapshot"]:
            raise SetupError("Setup resources changed before execution.")
        await self.database.call(lambda db: db.connection.execute("UPDATE setup_plans SET state='APPLYING' WHERE id=?", (plan["id"],)))
        for action in plan["actions"]:
            fresh = await self.port.fresh_actor(actor.channel_id, actor.user_id)
            require_actor(fresh, self.settings.guild_id, self.settings.owner_ids, administrator=True)
            spec = RESOURCES[action["key"]]
            if action["action"] == "KEEP":
                continue
            await self._step(plan["id"], spec.key, "APPLYING", action["remote_id"])
            await self.database.call(lambda db, s=spec, a=action: repository.save_resource(db, actor.guild_id, s, a["remote_id"], "UNCERTAIN"))
            current = await self.database.call(repository.state)
            parent_id = current["resources"][spec.parent]["discord_id"] if spec.parent else None
            try:
                identifier = await self.port.provision(spec, action, parent_id, plan["roles"])
            except UncertainOperation:
                await self._step(plan["id"], spec.key, "UNCERTAIN", action["remote_id"], "REMOTE_OUTCOME_UNKNOWN")
                raise
            except SetupError:
                await self.database.call(lambda db, s=spec, a=action: repository.save_resource(db, actor.guild_id, s, a["remote_id"], "MISSING" if a["remote_id"] is None else "UNCERTAIN"))
                await self._step(plan["id"], spec.key, "FAILED", action["remote_id"], "DISCORD_PERMISSION_OR_RESOURCE_ERROR")
                raise
            await self.database.call(lambda db, s=spec, value=identifier: repository.save_resource(db, actor.guild_id, s, value, "ACTIVE"))
            await self._step(plan["id"], spec.key, "COMPLETED", identifier)
        for panel_action in plan["panels"]:
            fresh = await self.port.fresh_actor(actor.channel_id, actor.user_id)
            require_actor(fresh, self.settings.guild_id, self.settings.owner_ids, administrator=True)
            current = await self.database.call(repository.state)
            from ..domain.discord import COMMAND_CHANNELS
            current["mappings"] = {
                command: current["mappings"].get(command) or current["resources"][key]["discord_id"]
                for command, key in COMMAND_CHANNELS.items()
            }
            for command, key in plan["command_overrides"].items():
                current["mappings"][command] = current["resources"][key]["discord_id"]
            resource = current["resources"][panel_action["resource_key"]]
            existing = current["panels"].get(panel_action["key"])
            panel_id = existing["id"] if existing else str(uuid4())
            revision = existing["revision"] + 1 if existing else 1
            message_id = existing["message_id"] if panel_action["present"] else None
            def pending(db):
                with db.transaction() as c:
                    c.execute("INSERT INTO panels VALUES (?,?,?,?,?,'UNCERTAIN') ON CONFLICT(resource_id,panel_key) DO UPDATE SET revision=excluded.revision,state='UNCERTAIN'", (panel_id, resource["id"], panel_action["key"], message_id, revision))
            await self.database.call(pending)
            await self._step(plan["id"], "panel." + panel_action["key"], "APPLYING", message_id)
            message_id = await self.port.publish_panel(panel_action["key"], resource["discord_id"], panel_id, revision, message_id, current)
            await self.database.call(lambda db, ident=panel_id, msg=message_id: db.connection.execute("UPDATE panels SET state='ACTIVE',message_id=? WHERE id=?", (msg, ident)))
            await self._step(plan["id"], "panel." + panel_action["key"], "COMPLETED", message_id)
        # Verify the final live resources/overwrites before enabling command readiness.
        final_snapshot = await self.port.snapshot()
        fresh = await self.port.fresh_actor(actor.channel_id, actor.user_id)
        require_actor(fresh, self.settings.guild_id, self.settings.owner_ids, administrator=True)
        if not REQUIRED_BOT_PERMISSIONS <= final_snapshot.bot_permissions:
            raise SetupError("Required bot permissions changed during setup.")
        current = await self.database.call(repository.state)
        for spec in RESOURCES.values():
            remote = final_snapshot.channel(current["resources"][spec.key]["discord_id"])
            parent_id = current["resources"][spec.parent]["discord_id"] if spec.parent else None
            if remote is None or remote.kind != spec.kind or remote.parent_id != parent_id or remote.overwrites != self.port.overwrites(spec, final_snapshot, plan["roles"]) or (spec.kind == "TEXT" and not OUTPUT_PERMISSIONS <= remote.bot_permissions):
                raise SetupError("Final channel permissions do not match the approved policy.")
        await self.database.call(lambda db: repository.finish_configuration(db, actor.guild_id, actor.user_id, plan["roles"], plan["command_overrides"], plan["output_overrides"], plan["id"]))
