"""Read complete saved excerpts without fetching again or changing evidence."""

import math
import time
import json

import discord

from .identity import clean, record_id
from ..research.collector import ResearchError, safe_url


def read_page(db, evidence_id, page=1):
    evidence_id = record_id(evidence_id)
    row = db.connection.execute(
        "SELECT e.*,b.name FROM evidence e JOIN businesses b ON b.id=e.business_id WHERE e.id=? AND e.research_run_id IS NOT NULL",
        (evidence_id,),
    ).fetchone()
    if not row: raise ResearchError("Saved research evidence was not found in this deployment.")
    pages = max(1, math.ceil(len(row["extracted_fact"]) / 1200))
    if type(page) is not int or not 1 <= page <= pages:
        raise ResearchError("Evidence page is outside the saved excerpt's page range.")
    data = dict(row)
    data.update(page=page, pages=pages, text=row["extracted_fact"][(page - 1) * 1200:page * 1200])
    return data


def evidence_card(data):
    embed = discord.Embed(title="Saved evidence · " + clean(data["name"], 100), description=clean(data["text"], 2400))
    if data["source_url"]:
        safe_url(data["source_url"])
        embed.url = data["source_url"]
    embed.add_field(name="Evidence", value=f"`{data['id']}`\nBusiness `{data['business_id']}`", inline=False)
    embed.add_field(name="Observed · source confidence", value=f"{data['observed_at']} · {data['confidence']}", inline=False)
    embed.add_field(name="Access policy version", value=clean(data["policy_version"], 200), inline=False)
    source_note = "\nFull source URL: use the card title link." if data["source_url"] else "\nSource identifier only; no URL recorded."
    embed.add_field(name="Source", value=clean(data["source_url"] or data["source_identifier"], 900) + source_note, inline=False)
    embed.add_field(name="Limitations", value=clean("\n".join(json.loads(data["limitations_json"])), 900) or "No additional limitations recorded.", inline=False)
    embed.set_footer(text=f"Page {data['page']}/{data['pages']} · Complete saved excerpt, not a complete website. No new fetch, AI analysis or qualification.")
    return embed


class EvidencePages(discord.ui.View):
    def __init__(self, client, actor_id, data):
        super().__init__(timeout=600)
        self.expires = time.monotonic() + 600
        for label, page in (("Previous", data["page"] - 1), ("Next", data["page"] + 1)):
            button = discord.ui.Button(label=label, disabled=not 1 <= page <= data["pages"])
            async def callback(interaction, selected=page):
                await show_evidence(client, interaction, data["id"], selected, actor_id=actor_id, expires=self.expires)
            button.callback = callback
            self.add_item(button)


class EvidencePicker(discord.ui.View):
    def __init__(self, client, actor_id, observations):
        super().__init__(timeout=600)
        self.expires = time.monotonic() + 600
        ids = tuple(row["id"] for row in observations)
        select = discord.ui.Select(placeholder="Read a complete saved excerpt", options=[
            discord.SelectOption(label=f"Evidence {index + 1} · {row['observed_at'][:10]}", value=row["id"])
            for index, row in enumerate(observations)
        ])
        async def callback(interaction):
            selected = select.values[0] if select.values else None
            if selected not in ids:
                async def reject(): raise ResearchError("Evidence selection is not part of this saved result.")
                await client._safe(interaction, reject)
                return
            await show_evidence(client, interaction, selected, actor_id=actor_id, expires=self.expires)
        select.callback = callback
        self.add_item(select)


async def show_evidence(client, interaction, evidence_id, page=1, *, actor_id=None, expires=None):
    async def action():
        if ((actor_id is not None and str(interaction.user.id) != str(actor_id))
                or (expires is not None and time.monotonic() >= expires)):
            raise ResearchError("This evidence control expired or belongs to another operator. Reopen /research action:evidence evidence_id:<UUID>.")
        actor, _ = await client._authorized(interaction, "research")
        data = await client.database.call(lambda db: read_page(db, evidence_id, page))
        await client.reply(interaction, embed=evidence_card(data), view=EvidencePages(client, actor.user_id, data))
    await client._safe(interaction, action)
