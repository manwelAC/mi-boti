"""Durable setup state and ID-based Discord configuration."""

import json
from uuid import uuid4

from ..domain.values import utc_now
from ..domain.discord import COMMAND_CHANNELS, OUTPUT_DESTINATIONS, PANELS


def audit(connection, actor_id, action, outcome, entity_id=None, details=None):
    connection.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)", (
        str(uuid4()), str(uuid4()), actor_id, action, "discord_setup", entity_id, outcome,
        json.dumps(details or {}, sort_keys=True), utc_now(),
    ))


def state(db):
    c = db.connection
    row = c.execute("SELECT * FROM guild_config WHERE id='guild'").fetchone()
    config = dict(row) if row else {"setup_state": "UNCONFIGURED", "revision": 0}
    resources = {r["resource_key"]: dict(r) for r in c.execute("SELECT * FROM discord_resources")}
    mappings = {r["command_key"]: resources_by_id["discord_id"]
                for r in c.execute("SELECT * FROM command_channels")
                if (resources_by_id := next((v for v in resources.values() if v["id"] == r["resource_id"] and v["state"] == "ACTIVE"), None))}
    outputs = {r["output_key"]: r["resource_id"] for r in c.execute("SELECT * FROM output_destinations")}
    roles = frozenset(r[0] for r in c.execute("SELECT role_id FROM role_grants WHERE permission='OPERATOR'"))
    panels = {r["panel_key"]: dict(r) for r in c.execute("SELECT * FROM panels")}
    return {"config": config, "resources": resources, "mappings": mappings, "outputs": outputs, "roles": roles, "panels": panels}


def recover_setup(db):
    with db.transaction() as c:
        interrupted = bool(c.execute("SELECT 1 FROM setup_plans WHERE state IN ('CONFIRMED','APPLYING')").fetchone())
        c.execute("UPDATE setup_steps SET state='UNCERTAIN',error_code='RESTART_INTERRUPTION',updated_at=? WHERE state='APPLYING'", (utc_now(),))
        c.execute("UPDATE setup_plans SET state='PARTIAL' WHERE state IN ('CONFIRMED','APPLYING')")
        if interrupted:
            c.execute("UPDATE guild_config SET setup_state='PARTIAL',updated_at=?", (utc_now(),))
        c.execute("UPDATE setup_plans SET state='EXPIRED' WHERE state='PREVIEW' AND expires_at<=?", (utc_now(),))


def mark_missing(db, snapshot):
    with db.transaction() as c:
        missing = []
        for row in c.execute("SELECT * FROM discord_resources WHERE state='ACTIVE'").fetchall():
            if snapshot.channel(row["discord_id"]) is None:
                c.execute("UPDATE discord_resources SET state='MISSING',revision=revision+1 WHERE id=?", (row["id"],))
                missing.append(row["resource_key"])
        if missing:
            c.execute("UPDATE guild_config SET setup_state='PARTIAL',revision=revision+1,updated_at=?", (utc_now(),))
            audit(c, None, "discord.resource_missing", "BLOCKED", details={"resource_keys": missing})


def save_resource(db, guild_id, spec, remote_id, status):
    with db.transaction() as c:
        parent = c.execute("SELECT id FROM discord_resources WHERE resource_key=?", (spec.parent,)).fetchone() if spec.parent else None
        row = c.execute("SELECT id FROM discord_resources WHERE resource_key=?", (spec.key,)).fetchone()
        identifier = row[0] if row else str(uuid4())
        c.execute("INSERT INTO discord_resources VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(resource_key,guild_id) DO UPDATE SET discord_id=excluded.discord_id,state=excluded.state,parent_resource_id=excluded.parent_resource_id,revision=discord_resources.revision+1",
                  (identifier, guild_id, spec.key, spec.kind, remote_id, parent[0] if parent else None, status))


def finish_configuration(db, guild_id, actor_id, roles, command_overrides, output_overrides, plan_id):
    with db.transaction() as c:
        resources = {r["resource_key"]: r["id"] for r in c.execute("SELECT * FROM discord_resources WHERE state='ACTIVE'")}
        # Preserve administrator changes; defaults fill only unconfigured keys.
        for key, resource in COMMAND_CHANNELS.items():
            c.execute("INSERT INTO command_channels VALUES (?,?,1) ON CONFLICT(command_key) DO NOTHING", (key, resources[resource]))
        for key, resource in OUTPUT_DESTINATIONS.items():
            c.execute("INSERT INTO output_destinations VALUES (?,?,1) ON CONFLICT(output_key) DO NOTHING", (key, resources[resource]))
        for table, key_column, overrides in (("command_channels", "command_key", command_overrides), ("output_destinations", "output_key", output_overrides)):
            for key, resource_key in overrides.items():
                c.execute(f"UPDATE {table} SET resource_id=?,revision=revision+1 WHERE {key_column}=?", (resources[resource_key], key))
        c.execute("DELETE FROM role_grants WHERE permission='OPERATOR'")
        c.executemany("INSERT INTO role_grants VALUES (?,?,'OPERATOR',?,?)", [(guild_id, role, actor_id, utc_now()) for role in roles])
        c.execute("UPDATE guild_config SET setup_state='READY',revision=revision+1,updated_at=? WHERE id='guild'", (utc_now(),))
        c.execute("UPDATE setup_plans SET state='COMPLETED' WHERE id=?", (plan_id,))
        audit(c, actor_id, "setup.complete", "SUCCESS")
