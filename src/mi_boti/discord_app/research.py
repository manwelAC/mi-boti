"""Private research commands and named administrator access-review confirmation."""

import asyncio
import json
import time

import discord

from .identity import clean, record_id
from ..jobs import research as jobs
from ..jobs.discovery import request_job_cancellation
from ..repositories import research_access as access
from ..research.collector import WebsiteCollector, ResearchError
from ..domain.errors import AppError


def saved_results(db, *, business_id=None, job_id=None):
    if job_id:
        job = db.connection.execute("SELECT * FROM jobs WHERE id=? AND kind='RESEARCH'", (record_id(job_id),)).fetchone()
    else:
        job = db.connection.execute("SELECT * FROM jobs WHERE business_id=? AND kind='RESEARCH' ORDER BY created_at DESC,id DESC LIMIT 1", (record_id(business_id),)).fetchone()
    if not job: raise ResearchError("No research job was found. Use /research with business:<UUID> refresh:true to start one.")
    run = db.connection.execute("SELECT * FROM research_runs WHERE job_id=?", (job["id"],)).fetchone()
    evidence = [dict(row) for row in db.connection.execute("SELECT * FROM evidence WHERE research_run_id=? ORDER BY observed_at,id LIMIT 5", (run["id"],))] if run else []
    return dict(job), dict(run) if run else None, evidence


async def show_saved(client, interaction, *, business_id=None, job_id=None):
    await client._authorized(interaction, "research")
    job, run, observations = await client.database.call(lambda db: saved_results(db, business_id=business_id, job_id=job_id))
    embed = discord.Embed(title="Website research", description=f"Job `{job['id']}` · {job['state']}\nBusiness `{job['business_id']}`")
    if run:
        embed.add_field(name="Collection", value=f"{run['state']} · Run `{run['id']}`", inline=False)
        for row in observations:
            embed.add_field(name=f"Evidence {row['id']}", value=(
                clean(row["source_url"], 180) + "\nObserved: " + clean(row["observed_at"], 35)
                + "\n" + clean(row["extracted_fact"], 500) + "\nSource confidence: " + str(row["confidence"])
            ), inline=False)
        limitations = json.loads(run["limitations_json"])
        if limitations: embed.add_field(name="Limitations", value=clean("\n".join(limitations), 800), inline=False)
    else:
        embed.add_field(name="Progress", value="No evidence checkpoint yet. Reopen with /research action:status job_id:<UUID>.", inline=False)
    if job["error_code"]: embed.add_field(name="Stopped safely", value=clean(job["error_code"]) + ". Check access review, robots, website availability and current permissions before retrying.", inline=False)
    embed.set_footer(text="Literal public-page excerpts, not independent verification. No AI analysis, score, qualification or quota credit.")
    await client.reply(interaction, embed=embed)


class AccessConfirmation(discord.ui.View):
    def __init__(self, client, proposal):
        super().__init__(timeout=300)
        self.client, self.proposal = client, proposal
        self.expires, self.used = time.monotonic() + 300, False
        button = discord.ui.Button(label="Confirm reviewed website access", style=discord.ButtonStyle.primary)
        button.callback = self.confirm
        self.add_item(button)

    async def confirm(self, interaction):
        async def action():
            if str(interaction.user.id) != self.proposal["review"]["reviewer_id"]:
                raise ResearchError("This access-review preview belongs to another administrator.")
            actor, _ = await self.client._authorized(interaction, "research", admin=True)
            if self.used or time.monotonic() >= self.expires:
                raise ResearchError("Access-review preview expired or was already used. Request a new preview.")
            self.used = True
            await self.client.database.call(lambda db: access.save_access(db, self.proposal, actor.user_id))
            self.stop()
            await self.client.reply(interaction, "Website-access review saved. No website was fetched. Use /research business:" + self.proposal["business_id"] + " refresh:true to collect public evidence; robots and transport checks still apply.")
        await self.client._safe(interaction, action)


async def operation(client, interaction, *, business=None, refresh=False, analyze=False, action="collect", job_id=None,
                    url=None, permission_url=None, rationale=None):
    async def execute():
        actor, _ = await client._authorized(interaction, "research", admin=action in {"review", "revoke"})
        if analyze: raise ResearchError("AI analysis is disabled; retry with analyze:false. No provider was called.")
        business_id = record_id(business) if business else None
        if action in {"review", "revoke", "collect"} and not business_id:
            raise ResearchError("Provide a business UUID from discovery results.")
        if action == "review":
            proposal = await client.database.call(lambda db: access.prepare_access(db, business_id, actor.user_id, url, permission_url, rationale))
            embed = discord.Embed(title="Review website access", description="Confirm only after checking that the site's terms permit this public-page collection. Robots permission alone is insufficient.")
            for name, value in (("Business", business_id), ("Website", proposal["url"]), ("Permission reference", proposal["review"]["permission_url"]),
                                ("Your review rationale", proposal["rationale"]), ("Expires", proposal["review"]["expires_at"])):
                embed.add_field(name=name, value=clean(value, 700), inline=False)
            await client.reply(interaction, embed=embed, view=AccessConfirmation(client, proposal))
            return
        if action == "revoke":
            await client.database.call(lambda db: access.revoke_access(db, business_id, actor.user_id))
            await client.reply(interaction, "Website-access review revoked. Active collection will stop at its next safety check.")
            return
        if action == "status":
            if not business_id and not job_id: raise ResearchError("Provide business or job_id for saved research.")
            await show_saved(client, interaction, business_id=business_id, job_id=job_id)
            return
        if action == "cancel":
            job, _, _ = await client.database.call(lambda db: saved_results(db, business_id=business_id, job_id=job_id))
            await client.database.call(lambda db: request_job_cancellation(db, job["id"], actor.user_id))
            await client.reply(interaction, "Cancellation requested. Existing evidence is retained; no automatic restart will occur.")
            return
        if action != "collect": raise ResearchError("Unsupported research action.")
        if job_id or url or permission_url or rationale:
            raise ResearchError("Collection uses the saved website review. Use action:review to change access or action:status to view a job.")
        if client.research_collector is None:
            client.research_collector = WebsiteCollector(client.settings.values["research.user_agent"],
                interval=client.settings.values["research.host_interval_seconds"], limits=client.settings.values)
        job = await client.database.call(lambda db: jobs.enqueue(db, business_id=business_id, actor_id=actor.user_id,
            guild_id=actor.guild_id, channel_id=actor.channel_id, idempotency_key="research:" + str(interaction.id), refresh=refresh, analyze=analyze))
        await client.reply(interaction, f"Research job `{job['id']}` saved for `{business_id}`. Only reviewed public pages will be collected; no AI is involved.")
        async def run():
            claimed = await client.database.call(lambda db: jobs.claim(db, job["id"], lease_seconds=client.settings.values["jobs.lease_seconds"],
                max_concurrency=client.settings.values["jobs.max_concurrency"], max_age_seconds=client.settings.values["jobs.manual_max_age_seconds"]))
            if claimed:
                await jobs.execute(client.database, claimed, client.research_collector, client._fresh_job_authorized,
                    lease_seconds=client.settings.values["jobs.lease_seconds"], heartbeat_seconds=client.settings.values["jobs.heartbeat_seconds"],
                    max_pages=min(5, client.settings.values["research.max_pages"]), max_age_seconds=client.settings.values["jobs.manual_max_age_seconds"])
            try:
                await show_saved(client, interaction, job_id=job["id"])
            except discord.HTTPException:
                # Job/evidence are already durable; no automatic publication replay.
                pass
            except AppError:
                # Saved state remains available after fresh authorization is restored.
                pass
        task = asyncio.create_task(run(), name="mi-boti-research-" + job["id"])
        client.tasks.add(task)
        task.add_done_callback(client._setup_done)
    await client._safe(interaction, execute)
