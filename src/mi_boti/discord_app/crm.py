"""Isolated native Discord CRM screens. Intentionally not registered in the bot."""

import json
import logging
import time

import discord

from .identity import clean
from ..domain.crm import CrmError
from ..services.crm import ManualCrmService

logger = logging.getLogger("mi_boti.crm")


def address(value):
    parts = json.loads(value or "{}")
    return ", ".join(f"{key.replace('_', ' ')}: {item}" for key, item in parts.items() if item) or "Not provided by the source"


def service(client, interaction):
    async def authorize(command):
        actor, _ = await client._authorized(interaction, command)
        return actor
    return ManualCrmService(client.database, authorize, guild_id=client.settings.guild_id, owner_ids=client.settings.owner_ids)


def lead_card(data):
    embed = discord.Embed(title="Lead · " + clean(data["business"]["name"], 120),
                          description=f"`{data['id']}` · {data['stage']} · revision {data['revision']}")
    embed.add_field(name="Qualification", value=data["qualification_kind"] + (" · No AI score" if data["current_score_id"] is None else f" · Score reference `{data['current_score_id']}`"), inline=False)
    embed.add_field(name="Business", value=f"`{data['business_id']}` · {data['business']['disposition']}", inline=False)
    for contact in data["contacts"]:
        embed.add_field(name="Recorded " + contact["kind"].lower(), value=clean(contact["value"], 160) + f"\nEvidence `{contact['evidence_id']}`\nObserved: {contact['observed_at']}", inline=False)
    embed.set_footer(text="Human review is recorded as a decision, not proof of software need. No automatic outreach.")
    return embed


class CrmConfirmation(discord.ui.View):
    def __init__(self, client, actor_id, kind, target_id, options):
        super().__init__(timeout=300)
        if kind not in {"contact", "qualification", "transition"}: raise CrmError("Unsupported CRM confirmation.")
        self.client, self.actor_id, self.kind, self.target_id = client, str(actor_id), kind, target_id
        self.options = json.loads(json.dumps(options))
        self.expires, self.used = time.monotonic() + 300, False
        confirm = discord.ui.Button(label="Confirm " + {"contact": "public contact", "qualification": "manual qualification", "transition": "stage change"}[kind], style=discord.ButtonStyle.primary)
        confirm.callback = self.confirm
        self.add_item(confirm)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self.cancel
        self.add_item(cancel)
        if any(self.options.get(key) for key in ("value", "rationale", "note", "attestation")):
            read = discord.ui.Button(label="Read full review text", style=discord.ButtonStyle.secondary)
            read.callback = self.read_full
            self.add_item(read)

    def _validate(self, interaction):
        if self.used or time.monotonic() >= self.expires or str(interaction.user.id) != self.actor_id:
            raise CrmError("This CRM preview expired, was used, or belongs to another operator. Reopen the preview.")

    async def confirm(self, interaction):
        async def action():
            self._validate(interaction)
            # Consume before yielding: concurrent clicks cannot execute twice.
            self.used = True
            api = service(self.client, interaction)
            if self.kind == "contact":
                result = await api.record_contact(self.target_id, confirmed=True, **self.options)
                receipt = f"Saved public contact `{result['id']}` with evidence `{result['evidence_id']}`. No outreach was sent."
            elif self.kind == "qualification":
                result = await api.qualify_manual(self.target_id, confirmed=True, **self.options)
                receipt = f"Saved MANUAL lead `{result['id']}` in NEW, revision {result['revision']}. No AI score or quota credit."
            else:
                result = await api.transition(self.target_id, confirmed=True, **self.options)
                receipt = f"Saved lead `{result['id']}` in {result['stage']}, revision {result['revision']}. No external message was sent."
            self.stop()
            try:
                await self.client.reply(interaction, receipt)
            except discord.HTTPException:
                logger.warning("CRM change committed; private receipt unavailable. Reopen the saved record; do not replay mutation.")
        await self.client._safe(interaction, action)

    async def cancel(self, interaction):
        async def action():
            self._validate(interaction)
            await self.client._authorized(interaction, "pipeline" if self.kind == "transition" else "lead")
            self._validate(interaction)
            self.used = True
            self.stop()
            await self.client.reply(interaction, "CRM preview cancelled. No record was changed.")
        await self.client._safe(interaction, action)

    async def read_full(self, interaction):
        async def action():
            self._validate(interaction)
            await self.client._authorized(interaction, "pipeline" if self.kind == "transition" else "lead")
            self._validate(interaction)
            for key in ("value", "rationale", "note", "attestation"):
                if self.options.get(key):
                    embed = discord.Embed(title="Full review text · " + key, description=clean(self.options[key], 4000))
                    embed.set_footer(text="Read-only preview. Confirmation is still required to save the proposal.")
                    await self.client.reply(interaction, embed=embed)
        await self.client._safe(interaction, action)


class CrmInteractions:
    """Testable adapter methods only; no slash commands/startup hooks here."""
    def __init__(self, client):
        self.client = client

    async def preview_contact(self, interaction, business_id, *, kind, value, evidence_id, rationale):
        async def action():
            plan = await service(self.client, interaction).preview_contact(business_id, kind=kind, value=value, evidence_id=evidence_id, rationale=rationale)
            embed = discord.Embed(title="Review public contact", description=clean(plan["business_name"], 150) + f"\nBusiness `{plan['business_id']}` · revision {plan['expected_revision']}")
            if plan["source_url"]: embed.url = plan["source_url"]
            embed.add_field(name="Recorded address preview", value=clean(address(plan["address_json"]), 150), inline=False)
            for name, item in (("Route preview", kind + ": " + plan["value"]), ("Evidence", plan["evidence_id"]),
                               ("Source preview", plan["source_url"] or plan["source_identifier"]), ("Observed", plan["observed_at"]), ("Attribution rationale preview", plan["rationale"])):
                embed.add_field(name=name, value=clean(item, 400), inline=False)
            embed.set_footer(text="Confirm that this published route belongs to this business. No guessed contacts or external sending.")
            options = {key: plan[key] for key in ("kind", "value", "evidence_id", "rationale", "expected_revision")}
            await self.client.reply(interaction, embed=embed, view=CrmConfirmation(self.client, interaction.user.id, "contact", plan["business_id"], options))
        await self.client._safe(interaction, action)

    async def preview_qualification(self, interaction, business_id, *, evidence_ids, rationale):
        async def action():
            plan = await service(self.client, interaction).preview_qualification(business_id, evidence_ids=evidence_ids, rationale=rationale)
            embed = discord.Embed(title="Review manual qualification", description=clean(plan["business_name"], 150) + f"\nBusiness `{plan['business_id']}` · revision {plan['expected_revision']}" + "\nProposed: MANUAL lead · NEW · No AI score · No quota credit")
            embed.add_field(name="Registry decision", value=plan["disposition"] + " → QUALIFIED by your manual review", inline=False)
            embed.add_field(name="Recorded address preview", value=clean(address(plan["address_json"]), 150), inline=False)
            embed.add_field(name="Rationale preview · full text button below", value=clean(plan["rationale"], 400), inline=False)
            for index, source in enumerate(plan["sources"]):
                embed.add_field(name=f"Evidence {index + 1} · source preview", value=f"`{source['id']}`\n{clean(source['source_url'] or source['source_identifier'], 120)}\nObserved: {source['observed_at']} · Confidence: {source['confidence']}", inline=False)
            embed.set_footer(text="This records your evidence review and judgment. It does not prove internal software is absent.")
            options = {key: plan[key] for key in ("evidence_ids", "rationale", "expected_revision")}
            await self.client.reply(interaction, embed=embed, view=CrmConfirmation(self.client, interaction.user.id, "qualification", plan["business_id"], options))
        await self.client._safe(interaction, action)

    async def preview_transition(self, interaction, lead_id, **options):
        async def action():
            plan = await service(self.client, interaction).preview_transition(lead_id, **options)
            proposal = plan["proposal"]
            embed = discord.Embed(title="Review pipeline change", description=clean(plan["business_name"], 150) + f"\n{proposal['from']} → {proposal['to']} · expected revision {plan['expected_revision']}")
            embed.add_field(name="Business and address preview", value=f"`{plan['business_id']}`\n" + clean(address(plan["address_json"]), 150), inline=False)
            for label, key in (("Note / outcome / reopening reason", "note"), ("Manual-contact attestation", "manual_contact_attestation"), ("Follow-up due (UTC)", "due_at")):
                if proposal.get(key): embed.add_field(name=label + " (preview)", value=clean(proposal[key], 400), inline=False)
            if plan["contact"]:
                contact = plan["contact"]
                embed.add_field(name="Published contact route", value=clean(contact["kind"] + ": " + contact["value"], 400) + f"\nEvidence `{contact['evidence_id']}`\nObserved: {contact['observed_at']}", inline=False)
            if proposal.get("evidence_ids"):
                embed.add_field(name="Reviewed evidence", value="\n".join(f"`{identifier}`" for identifier in proposal["evidence_ids"]), inline=False)
            embed.set_footer(text="Only the proposed stage and due record change. No outreach or reminder is dispatched.")
            await self.client.reply(interaction, embed=embed, view=CrmConfirmation(self.client, interaction.user.id, "transition", plan["lead_id"], options))
        await self.client._safe(interaction, action)

    async def list_leads(self, interaction, *, stage=None, page=1):
        async def action():
            data = await service(self.client, interaction).list_leads(stage=stage, page=page)
            embed = discord.Embed(title="CRM leads", description="\n".join(f"{clean(row['business_name'], 100)} · {row['stage']} · revision {row['revision']}\n`{row['id']}`" for row in data["records"]) or "No leads on this page.")
            embed.set_footer(text=f"Page {page} · {data['total']} records · Discovered businesses are not automatically leads.")
            await self.client.reply(interaction, embed=embed)
        await self.client._safe(interaction, action)

    async def detail(self, interaction, lead_id):
        async def action():
            data = await service(self.client, interaction).get_lead(lead_id)
            await self.client.reply(interaction, embed=lead_card(data))
        await self.client._safe(interaction, action)

    async def notes(self, interaction, lead_id, *, page=1):
        async def action():
            data = await service(self.client, interaction).history(lead_id, notes=True, page=page)
            embed = discord.Embed(title="Lead notes", description="Append-only observations; corrections retain their originals.")
            for row in data["records"]:
                embed.add_field(name=row["id"], value=clean(row["body"], 180) + f"\nBy {row['actor_id']} · {row['created_at']}" + (f"\nCorrects `{row['supersedes_id']}`" if row["supersedes_id"] else ""), inline=False)
            embed.set_footer(text=f"Page {page} · {data['total']} notes · Full note text remains stored.")
            await self.client.reply(interaction, embed=embed)
        await self.client._safe(interaction, action)

    async def add_note(self, interaction, lead_id, *, expected_revision, body, supersedes_id=None):
        async def action():
            note = await service(self.client, interaction).add_note(lead_id, expected_revision=expected_revision, body=body, supersedes_id=supersedes_id)
            await self.client.reply(interaction, f"Saved note `{note['id']}`. Previous notes were retained.")
        await self.client._safe(interaction, action)

    async def show_note(self, interaction, lead_id, note_id):
        async def action():
            note = await service(self.client, interaction).get_note(lead_id, note_id)
            embed = discord.Embed(title="Saved lead note", description=clean(note["body"], 4000))
            embed.add_field(name="Provenance", value=f"`{note['id']}`\nBy {note['actor_id']} · {note['created_at']}", inline=False)
            if note["supersedes_id"]: embed.add_field(name="Corrects", value=f"`{note['supersedes_id']}`")
            embed.set_footer(text="Original note text is retained; no external communication was sent.")
            await self.client.reply(interaction, embed=embed)
        await self.client._safe(interaction, action)
