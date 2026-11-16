"""Read-only, policy-checked pages of persisted discovery observations."""

import json
import time

import discord

from .identity import clean, record_id
from ..domain.registry import RegistryError


def read_results(db, job_id, page=1):
    job_id = record_id(job_id)
    if type(page) is not int or page < 1:
        raise RegistryError("Page must be a positive integer.")
    job = db.connection.execute("SELECT state FROM jobs WHERE id=? AND kind='DISCOVER'", (job_id,)).fetchone()
    if not job:
        raise RegistryError("Discovery job not found in this deployment.")
    total = db.connection.execute(
        "SELECT count(*) FROM candidates c JOIN discovery_queries q ON q.id=c.query_id WHERE q.job_id=?", (job_id,),
    ).fetchone()[0]
    rows = db.connection.execute(
        "SELECT c.id,c.state,c.business_id,c.observation_json FROM candidates c "
        "JOIN discovery_queries q ON q.id=c.query_id WHERE q.job_id=? ORDER BY c.created_at,c.id LIMIT 10 OFFSET ?",
        (job_id, (page - 1) * 10),
    ).fetchall()
    return {"job_id": job_id, "state": job[0], "page": page, "total": total, "rows": [dict(r) for r in rows]}


def results_card(data):
    embed = discord.Embed(title="Discovered businesses", description=f"Job `{data['job_id']}` · {data['state']}")
    for row in data["rows"]:
        obs = json.loads(row["observation_json"])
        embed.add_field(name=clean(obs.get("name", "Unnamed observation"), 120), value=(
            f"{row['state']} · Business: `{row['business_id'] or 'unresolved'}`\n"
            f"Source: {clean(obs.get('source_namespace', 'unknown'), 25)}:{clean(obs.get('source_id', 'unknown'), 70)}\n"
            f"Observed: {clean(obs.get('observed_at', 'unknown'), 35)}"
        ), inline=False)
    if not data["rows"]:
        embed.add_field(name="Results", value="No saved observations on this page.")
    embed.set_footer(text=f"Page {data['page']} · {data['total']} saved observations · Discovery is not qualification or live website research.")
    return embed


class ResultsView(discord.ui.View):
    def __init__(self, client, actor_id, data):
        super().__init__(timeout=600)
        self.client, self.actor_id, self.data = client, str(actor_id), data
        self.expires = time.monotonic() + 600
        for label, page in (("Previous", data["page"] - 1), ("Next", data["page"] + 1)):
            button = discord.ui.Button(label=label, disabled=page < 1 or (page - 1) * 10 >= data["total"])
            async def callback(interaction, selected_page=page):
                await show_results(client, interaction, data["job_id"], selected_page, actor_id=self.actor_id, expires=self.expires)
            button.callback = callback
            self.add_item(button)
        if data["rows"]:
            select = discord.ui.Select(placeholder="Inspect a saved observation", options=[
                discord.SelectOption(label=str(json.loads(row["observation_json"]).get("name", "Unnamed"))[:100] or "Unnamed", value=row["id"])
                for row in data["rows"]
            ])
            async def inspect(interaction):
                async def action():
                    if str(interaction.user.id) != self.actor_id or time.monotonic() >= self.expires:
                        raise RegistryError("Open your own results with /discover job_id:<UUID>.")
                    await client._authorized(interaction, "discover")
                    current = await client.database.call(lambda db: read_results(db, data["job_id"], data["page"]))
                    row = next((r for r in current["rows"] if r["id"] == select.values[0]), None)
                    if row is None:
                        raise RegistryError("Observation is not on this results page. Reopen results.")
                    obs = json.loads(row["observation_json"])
                    embed = discord.Embed(title=clean(obs.get("name", "Unnamed"), 150), description=f"{row['state']} · Business `{row['business_id'] or 'unresolved'}`")
                    for name, value in (("Source reference (untrusted)", obs.get("source_url", "Not supplied")),
                                        ("Observed", obs.get("observed_at", "Unknown")),
                                        ("Address", json.dumps(obs.get("address", {}), ensure_ascii=False)),
                                        ("Attribution", obs.get("attribution", "Not supplied")),
                                        ("Limitations", json.dumps(obs.get("limitations", []), ensure_ascii=False))):
                        embed.add_field(name=name, value=clean(value, 900) or "Not supplied", inline=False)
                    embed.set_footer(text="Source assertions only. For identity review, use /lead in lead-pipeline. No qualification or quota credit.")
                    await client.reply(interaction, embed=embed)
                await client._safe(interaction, action)
            select.callback = inspect
            self.add_item(select)


async def show_results(client, interaction, job_id, page=1, *, actor_id=None, expires=None):
    async def action():
        if (actor_id is not None and str(interaction.user.id) != str(actor_id)) or (expires is not None and time.monotonic() >= expires):
            raise RegistryError("Open your own results with /discover job_id:<UUID>.")
        actor, _ = await client._authorized(interaction, "discover")
        data = await client.database.call(lambda db: read_results(db, job_id, page))
        await client.reply(interaction, embed=results_card(data), view=ResultsView(client, actor.user_id, data))
    await client._safe(interaction, action)
