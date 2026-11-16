"""Private, short-lived identity review controls; no autonomous work."""

import json
import time
from uuid import UUID

import discord

from ..domain.registry import RegistryError
from ..domain.campaigns import validate_rationale
from ..repositories.registry import resolve_identity_review


def record_id(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise RegistryError("Use a valid record UUID.") from None


def read_record(db, identifier=None, page=1):
    if type(page) is not int or page < 1:
        raise RegistryError("Page must be a positive integer.")
    c = db.connection
    if identifier is None:
        rows = c.execute(
            "SELECT r.id,c.observation_json FROM identity_reviews r JOIN candidates c ON c.id=r.candidate_id "
            "WHERE r.state='OPEN' ORDER BY c.created_at,r.id LIMIT 10 OFFSET ?", ((page - 1) * 10,),
        ).fetchall()
        return {"kind": "queue", "page": page, "rows": [dict(row) for row in rows]}
    identifier = record_id(identifier)
    review = c.execute(
        "SELECT r.*,c.observation_json FROM identity_reviews r JOIN candidates c ON c.id=r.candidate_id WHERE r.id=?",
        (identifier,),
    ).fetchone()
    if review:
        result = dict(review)
        result["kind"] = "review"
        result["matches"] = [dict(row) for match in json.loads(review["matches_json"])
                             for row in c.execute("SELECT id,name,revision FROM businesses WHERE id=?", (match,))]
        return result
    business = c.execute(
        "SELECT b.* FROM businesses b WHERE b.id=? OR b.id=(SELECT business_id FROM leads WHERE id=?)",
        (identifier, identifier),
    ).fetchone()
    if not business:
        raise RegistryError("Record not found in this deployment.")
    reviews = c.execute(
        "SELECT r.id FROM identity_reviews r,json_each(r.matches_json) m WHERE r.state='OPEN' AND m.value=? ORDER BY r.id LIMIT 10",
        (business["id"],),
    ).fetchall()
    return {"kind": "business", **dict(business), "reviews": [row[0] for row in reviews]}


def clean(value, limit=240):
    return discord.utils.escape_mentions(discord.utils.escape_markdown(str(value)))[:limit]


def card(record):
    embed = discord.Embed(title="Identity review" if record["kind"] != "business" else "Business registry")
    if record["kind"] == "queue":
        embed.description = "\n".join(
            f"`{row['id']}` · {clean(json.loads(row['observation_json']).get('name', 'Unnamed'), 100)}"
            for row in record["rows"]
        ) or "No open reviews on this page."
        embed.set_footer(text=f"Page {record['page']} · Open a review with /lead id:<UUID>.")
    elif record["kind"] == "review":
        obs = json.loads(record["observation_json"])
        embed.description = f"`{record['id']}` · {record['state']}\n{clean(obs.get('name', 'Unnamed'))}"
        embed.add_field(name="Observed source", value=clean(f"{obs.get('source_namespace')}:{obs.get('source_id')} · {obs.get('observed_at')}"), inline=False)
        embed.add_field(name="Source reference (untrusted)", value=clean(obs.get("source_url", "Not supplied"), 500), inline=False)
        embed.add_field(name="Address (source assertion)", value=clean(json.dumps(obs.get('address', {}), ensure_ascii=False), 1000) or "Not supplied", inline=False)
        embed.add_field(name="Possible matches", value="\n".join(
            f"`{match['id']}` · revision {match['revision']} · {clean(match['name'], 90)}" for match in record["matches"][:10]
        ) or "No current matches.", inline=False)
        embed.add_field(name="Decision", value="Inspect the source and matches. Use /lead with action:link and target:<business UUID>, or action:separate, and a rationale. Both require confirmation.", inline=False)
        embed.set_footer(text="Discovery assertions are not verified research. No qualification or quota credit.")
    else:
        embed.description = f"{clean(record['name'])}\n`{record['id']}` · revision {record['revision']}\n{record['disposition']} · {record['entity_kind']}"
        embed.add_field(name="Address", value=clean(record["address_json"], 1000) or "Not supplied", inline=False)
        embed.add_field(name="Open identity reviews (up to 10)", value="\n".join(f"`{item}`" for item in record["reviews"]) or "None", inline=False)
        embed.set_footer(text="Registry identity only. Research, CRM notes and manual qualification remain unavailable.")
    return embed


class IdentityConfirmation(discord.ui.View):
    def __init__(self, client, actor_id, review_id, action, rationale, target=None, revision=None):
        super().__init__(timeout=300)
        self.client, self.actor_id = client, str(actor_id)
        self.review_id, self.action, self.rationale = review_id, action, validate_rationale(rationale)
        self.target, self.revision = target, revision
        self.expires = time.monotonic() + 300
        self.used = False
        button = discord.ui.Button(label="Confirm identity decision", style=discord.ButtonStyle.primary)
        button.callback = self.confirm
        self.add_item(button)

    async def confirm(self, interaction):
        async def action():
            if str(interaction.user.id) != self.actor_id or time.monotonic() >= self.expires or self.used:
                raise RegistryError("This confirmation is expired, already used, or belongs to another operator. Reopen /lead.")
            actor, _ = await self.client._authorized(interaction, "lead")
            if self.used or time.monotonic() >= self.expires:
                raise RegistryError("This confirmation is expired or already used. Reopen /lead.")
            # No await between consuming this actor-bound confirmation and queueing its transaction.
            self.used = True
            result = await self.client.database.call(lambda db: resolve_identity_review(
                db, self.review_id, str(actor.user_id), action=self.action, rationale=self.rationale,
                target_business_id=self.target, expected_business_revision=self.revision,
            ))
            self.stop()
            await self.client.reply(interaction, f"Identity resolved: `{result.business_id}` ({result.state}). No lead, AI task or quota credit was created.")
        await self.client._safe(interaction, action)


async def lead(client, interaction, *, identifier=None, page=1, action="inspect", target=None, rationale=None):
    async def execute():
        selected_target = target
        actor, _ = await client._authorized(interaction, "lead")
        record = await client.database.call(lambda db: read_record(db, identifier, page))
        if action == "inspect":
            await client.reply(interaction, embed=card(record))
            return
        if action not in {"link", "separate"} or record["kind"] != "review" or record["state"] != "OPEN":
            raise RegistryError("Choose an OPEN review UUID and action link or separate.")
        rationale_clean = validate_rationale(rationale)
        revision = None
        if action == "link":
            selected_target = record_id(target)
            business = await client.database.call(lambda db: read_record(db, selected_target))
            if business["kind"] != "business" or business["id"] != selected_target:
                raise RegistryError("Target must be a business UUID.")
            revision = business["revision"]
        elif target is not None:
            raise RegistryError("Separate does not accept a target.")
        view = IdentityConfirmation(client, actor.user_id, record["id"],
                                    "LINK_EXISTING" if action == "link" else "CREATE_NEW",
                                    rationale_clean, selected_target, revision)
        embed = card(record)
        if selected_target:
            embed.add_field(name="Selected business", value=clean(business["name"], 120) + "\n" + clean(business["address_json"], 500), inline=False)
        embed.add_field(name="Confirm proposed decision", value=(
            f"Link to `{selected_target}` at revision {revision}." if selected_target else "Create a separate PENDING business."
        ) + "\nRationale: " + clean(rationale_clean, 700), inline=False)
        await client.reply(interaction, embed=embed, view=view)
    await client._safe(interaction, execute)
