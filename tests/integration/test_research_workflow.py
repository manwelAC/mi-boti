import asyncio
from dataclasses import replace
import hashlib
from types import SimpleNamespace

import pytest

from conftest import business as make_business
from test_discord_transport import initialized, Interaction
from mi_boti.discord_app.research import operation, saved_results
from mi_boti.domain.values import utc_now
from mi_boti.jobs import research as jobs
from mi_boti.jobs.discovery import recover_interrupted_work
from mi_boti.repositories import discord as repository
from mi_boti.repositories import research_access as access
from mi_boti.research.collector import Collection, PageObservation


class Collector:
    def __init__(self, *, slow=False):
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not slow: self.release.set()
    async def collect(self, url, review, *, max_pages, authorize):
        await authorize()
        self.calls += 1
        self.started.set()
        await self.release.wait()
        text = "Publicly advertised booking service."
        page = PageObservation(url, url, utc_now(), text, hashlib.sha256(text.encode()).hexdigest(), review.policy_version, ("Source assertion only.",))
        return Collection("SUCCEEDED", (page,), 2, ())


@pytest.mark.parametrize("case", ["success", "refresh", "cancel", "revoke", "policy-change", "permission-loss", "shutdown", "ai", "missing-review", "wrong-channel"])
def test_non_ai_research_lifecycle(database, configured, case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Non-AI research must not launch a CLI or make a paid API request.")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("httpx.AsyncClient", forbidden)
    business = make_business(database.connection)
    async def run():
        db, port, client, actor = await initialized(database, configured)
        client.settings = replace(client.settings, values={**client.settings.values, "jobs.heartbeat_seconds": 1})
        try:
            current = await db.call(repository.state)
            actor = replace(actor, channel_id=current["mappings"]["research"])
            collector = Collector(slow=case in {"cancel", "revoke", "policy-change", "permission-loss", "shutdown"})
            client.research_collector = collector
            if case != "missing-review":
                ix = Interaction(actor)
                await operation(client, ix, action="review", business=business, url="https://public.example/",
                                permission_url="https://public.example/terms", rationale="Reviewed published automated-access permission.")
                assert collector.calls == 0
                await ix.sent[-1]["view"].confirm(Interaction(actor))
            ix = Interaction(replace(actor, channel_id="900") if case == "wrong-channel" else actor)
            ix.id = 123456
            await operation(client, ix, business=business, refresh=True, analyze=case == "ai")
            if case in {"ai", "missing-review", "wrong-channel"}:
                assert not client.tasks and collector.calls == 0
                assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM jobs WHERE kind='RESEARCH'").fetchone()[0]) == 0
                return
            tasks = tuple(client.tasks)
            await asyncio.wait_for(collector.started.wait(), 2)
            job_id = await db.call(lambda d: d.connection.execute("SELECT id FROM jobs WHERE kind='RESEARCH'").fetchone()[0])
            if case == "cancel": await operation(client, Interaction(actor), action="cancel", job_id=job_id)
            if case == "revoke": await operation(client, Interaction(actor), action="revoke", business=business)
            if case == "policy-change":
                proposal = await db.call(lambda d: access.prepare_access(d, business, actor.user_id, "https://public.example/new", "https://public.example/terms", "Updated access review."))
                await db.call(lambda d: access.save_access(d, proposal, actor.user_id))
            if case == "permission-loss": port.members.pop(actor.user_id)
            if case == "shutdown": tasks[0].cancel()
            if case in {"success", "refresh"}: collector.release.set()
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
            job, research, observations = await db.call(lambda d: saved_results(d, job_id=job_id))
            if case in {"success", "refresh"}:
                assert job["state"] == "SUCCEEDED" and research["state"] == "SUCCEEDED"
                assert len(observations) == 1
                calls = collector.calls
                replay = Interaction(actor); replay.id = 123456
                await operation(client, replay, business=business, refresh=True)
                await asyncio.gather(*tuple(client.tasks))
                assert collector.calls == calls
                if case == "refresh":
                    original = dict(observations[0])
                    another = Interaction(actor); another.id = 987654
                    await operation(client, another, business=business, refresh=True)
                    await asyncio.gather(*tuple(client.tasks))
                    assert await db.call(lambda d: dict(d.connection.execute("SELECT * FROM evidence WHERE id=?", (original["id"],)).fetchone())) == original
                    assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM research_runs").fetchone()[0]) == 2
                status = Interaction(actor)
                await operation(client, status, action="status", job_id=job_id)
                assert len(status.sent[-1]["embed"]) <= 6000
            else:
                assert job["state"] == {"cancel": "CANCELLED", "shutdown": "INTERRUPTED"}.get(case, "FAILED")
                assert not observations
            for table in ("findings", "scores", "leads", "hunt_credits"):
                assert await db.call(lambda d: d.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]) == 0
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


@pytest.mark.parametrize("state", ["QUEUED", "RUNNING"])
def test_restart_interrupts_research_without_requeue(database, state):
    business = make_business(database.connection)
    # Recovery also covers queued manual RESEARCH work, which must not run later.
    from test_research_evidence import research_job
    job, token = research_job(database, business)
    from mi_boti.repositories.research import begin_run
    run = begin_run(database, job, token) if state == "RUNNING" else None
    if state == "QUEUED": database.connection.execute("UPDATE jobs SET state='QUEUED',lease_token=NULL,lease_expires_at=NULL WHERE id=?", (job,))
    recover_interrupted_work(database)
    if run: assert database.connection.execute("SELECT state FROM research_runs WHERE id=?", (run,)).fetchone()[0] == "INTERRUPTED"
    assert database.connection.execute("SELECT state FROM jobs WHERE id=?", (job,)).fetchone()[0] == "INTERRUPTED"
    assert jobs.claim(database, job) is None


@pytest.mark.parametrize("case", ["other-actor", "expired", "stale", "ordinary-member"])
def test_access_review_confirmation_fails_closed(database, configured, case):
    business = make_business(database.connection)
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            actor = replace(actor, channel_id=current["mappings"]["research"])
            if case == "ordinary-member":
                actor = replace(actor, user_id="999", administrator=False, role_ids=frozenset())
                port.members[actor.user_id] = actor
            ix = Interaction(actor)
            await operation(client, ix, action="review", business=business, url="https://public.example/",
                            permission_url="https://public.example/terms", rationale="Reviewed access policy.")
            if case == "ordinary-member":
                assert "view" not in ix.sent[-1]
            else:
                view = ix.sent[-1]["view"]
                if case == "expired": view.expires = 0
                if case == "stale": await db.call(lambda d: d.connection.execute("UPDATE guild_config SET revision=revision+1"))
                if case == "other-actor": actor = replace(actor, user_id="999")
                await view.confirm(Interaction(actor))
            with pytest.raises(Exception, match="No website-access review"):
                await db.call(lambda d: access.get_access(d, business))
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())
