# Mi Boti — development handoff

Snapshot: 2026-11-14. Application-code baseline: `9633d4d` on `main`. Last tagged milestone: `v0.2.0`. Phase 3 changes are unreleased; package metadata still says 0.2.0. Check Git status/log and the latest acceptance entries before treating this snapshot as current.

This note onboards Codex, Antigravity and other owner-selected development tools. Using Antigravity to develop this repository does **not** approve it as Mi Boti's runtime AI provider. No runtime provider has passed L02; AI execution and hunting remain disabled.

## Start here

1. Read the local `AGENTS.md` owner brief. It intentionally stays outside Git; do not add or force-add it. If another checkout lacks it, obtain the owner's current instructions before implementation.
2. Read [README](README.md), then [requirements](docs/01-PRODUCT-REQUIREMENTS.md). Consult component contracts relevant to the assigned task rather than reading every numbered document each time.
3. For Phase 3, consult [architecture](docs/02-TECHNICAL-ARCHITECTURE.md), [schema](docs/04-DATABASE-SCHEMA.md), [discovery](docs/08-BUSINESS-DISCOVERY.md), [jobs](docs/17-BACKGROUND-JOBS.md) and [configuration](docs/23-IMPLEMENTATION-GUIDELINES.md).
4. Read the [roadmap](docs/21-DEVELOPMENT-ROADMAP.md) and **latest dated entries** in [acceptance](docs/22-ACCEPTANCE-CRITERIA.md). Earlier entries describe historical states and may be superseded.
5. Inspect `git status --short --branch`. Coordinate task/file ownership if another development tool is working in this checkout; preserve changes you did not make.

Authority: local AGENTS sections 1–22 > docs/01 > other numbered component contracts. This handoff summarizes progress; it does not override those contracts or authorize new features by itself.

## Implemented versus pending

| Component | Implemented and verified | Still pending |
|---|---|---|
| Phase 0 feasibility | CLI/source assessments, bounded source probes, and Geofabrik Philippines extract L03 verification recorded | No verified runtime AI provider (`D11`/`L02`); website research source policies (`D12` for Phase 4a) still pending |
| Phase 1 foundation | Python package, strict config, redacted logs, private storage, deployment lock, 41-table checksummed SQLite migration, artifacts and verified-copy backup/restore primitives | Later workflow-specific recovery/release validation |
| Phase 2 Discord | Guild-scoped commands, fresh authorization, ID-based restrictions, private setup preview/confirmation, setup journal, idempotent resources, four persistent panels, staged role/mapping edits | Full L01 acceptance remains incomplete |
| Phase 3 core | Offline normalization, transactional registry reservations/claims, ambiguity holds, duplicate provenance, open-review reuse, explicit branch distinctions, bounded query planner, Overpass JSON parser + SSRF-pinned `OverpassDiscoveryAdapter` with process-wide rate limiting, regional Geofabrik Philippines OSM PBF extract downloader/importer (`pyosmium==4.3.2`) + `PhilippinesExtractAdapter` (`L03`-verified) with durable cursor pagination, versioned non-AI campaigns (`/campaign`), query/coverage lifecycle with request budgets, bounded manual discovery worker (`/discover`) with non-blocking async execution, periodic lease heartbeats, fresh per-step authorization, startup recovery, and identity-review/hierarchy resolution | Discord identity-review resolution UI and live Discord `/campaign` + `/discover` operator walkthrough |
| Phase 4a research | Specified only | Safe website collection, policy/robots enforcement, evidence workflow and non-AI /research |
| Phase 4b / Phase 5 | Specified only | Provider adapters, findings/scoring and autonomous hunting, subject to their gates |
| Phase 6 CRM/outreach | Specified only; tables exist | Lead workflow, manual qualification, pipeline, notes, follow-ups and manual drafts |

A table, parser or slash-command registration is not an enabled end-to-end feature. Many registered commands deliberately return unavailable status. `/discover`, research, CRM, AI and hunting are not usable yet.

## Current Phase 3 behavior

- [domain/registry.py](src/mi_boti/domain/registry.py) normalizes Unicode names, structured addresses, IDNA hostnames and published contacts. Website/phone/email signals are supporting, never globally unique claims. Missing data is not inferred.
- [repositories/registry.py](src/mi_boti/repositories/registry.py) requires an existing RUNNING query and current uncancelled DISCOVER lease. BEGIN IMMEDIATE serializes identity rechecks and reservations. Every disposition participates; origin job/hunt ownership stays immutable.
- Conflicting identities create review holds rather than automatic merges. Repeated unresolved observations across queries reference the existing open review while retaining their candidates. Registry calls create no research, leads, scores, AI executions or hunt credits.
- [discovery/planner.py](src/mi_boti/discovery/planner.py) uses fixed templates, finite boxes, cafe/restaurant tags and deterministic fingerprints. Planning grants no permission to execute a request.
- [discovery/overpass.py](src/mi_boti/discovery/overpass.py) translates bounded Overpass JSON, preserves node/way/relation identifiers and attribution, marks remarks/output-cap hits incomplete, and provides `OverpassDiscoveryAdapter` with pinned-IP SSRF connections (preserving `Host` and TLS `sni_hostname`), mixed-record/IPv4-mapped IPv6 rejection, bounded daemon-thread DNS resolution (`_resolve_public_host_bounded` / `active_resolver_worker_count` / `shutdown_resolver_workers`) that blocks further admission while an uncooperative DNS lookup is wedged, process-wide rate limiting (`>=10s`, concurrency `1`, `Retry-After` enforcement), and streaming size limits (`<=5 MiB`). It explicitly rejects `/api/0.6/map.json` because the OSM editing API policy prohibits read-only projects.
- [domain/campaigns.py](src/mi_boti/domain/campaigns.py) and [repositories/campaigns.py](src/mi_boti/repositories/campaigns.py) validate non-AI PH campaigns, rubric v1, versioned edits, archive transitions, `active_campaign_id`, query planning against fresh/exhausted coverage cells, and daily/job/attempt budget reservations.
- [jobs/discovery.py](src/mi_boti/jobs/discovery.py) implements idempotent manual discovery admission (`/discover`), atomic lease claims, periodic lease heartbeats during requests and rate-limit waits, fresh authorization revalidation before every dispatch/retry/commit, stricter timeout selection (`min(request_timeout_seconds, policy["timeout_seconds"])`), bounded tracked daemon-thread source execution (`active_discovery_worker_count` / `shutdown_discovery_workers` without `ThreadPoolExecutor` `atexit` hangs or untracked thread accumulation), responsive cancellation, startup interruption recovery (charging at most the reserved 30-second lease), and non-blocking async worker execution (`execute_manual_discovery_job_async`) outside the SQLite executor.
- `resolve_identity_review` and `link_parent_business` in [repositories/registry.py](src/mi_boti/repositories/registry.py) resolve open identity reviews (`LINK_EXISTING` / `CREATE_NEW`) and parent/branch hierarchy links with named actors, revision checks, cycle prevention, and zero retroactive quota credit.
- [discovery/philippines_extract.py](src/mi_boti/discovery/philippines_extract.py) implements the owner-approved Geofabrik Philippines OSM regional extract workflow ([docs/PHILIPPINES-EXTRACT-PLAN.md](docs/PHILIPPINES-EXTRACT-PLAN.md)): explicit CLI commands `import-ph-extract` and `verify-ph-extract`, pinned-IP HTTPS download with reviewed redirects (`<=3` hops on `download.geofabrik.de`), provider MD5 error-detection check + local SHA-256 verification, bounded child-subprocess PBF parsing (`_parse_pbf_in_isolated_subprocess`, `isolate_process=True`) via optional `osmium==4.3.2` (`[project.optional-dependencies] discovery`) with an enforced monotonic deadline on both download and `--pbf-file` imports, disk-backed SQLite coordinate scratch resolution under `tmp/`, approximate centroid labelling (`"approximate": True`), serialized publication (`datasets/philippines/publish.lock`) of immutable generation directories (`datasets/philippines/generations/<snapshot_id>/{snapshot.sqlite3, manifest.json}`) with a single atomic active-generation pointer switch (`datasets/philippines/active_generation.json`, with bounded Windows sharing-conflict recovery `_replace_file_with_sharing_retry` / `_read_text_with_sharing_retry`), read-only generation querying (`PhilippinesExtractAdapter`), and deferred cross-database cursor acknowledgement (`DiscoveryBatch.checkpoint_token` + `acknowledge_checkpoint()`) in `datasets/philippines/cursors.sqlite3` bound to `(snapshot_id, snapshot_sha256)` and coordinated under `publish.lock` that advances only after `mi_boti.sqlite3` candidate/registry/query commits succeed under valid authorization and lease ownership.
- [config.py](src/mi_boti/config.py) keeps `[sources.philippines_extract] enabled = false` in `config.example.toml` and rejects `enabled = true` on all sources and providers so production discovery, AI execution, and autonomous hunting remain disabled.
- Applied SQL/checksum manifests in `mi_boti.sqlite3` are immutable; use a new migration for schema changes.

## Live evidence and owner decisions

The owner verified setup, repeat setup, wrong-channel rejection, mapped-channel status, commands after restart, persistent hunt-control buttons after restart and a button response after renaming its channel. The solo-server owner deferred the second-user live authorization test: **NOT PERFORMED**, not passed. Automated authorization tests remain mandatory. Deletion/recovery, permission-loss paths and measured interaction timing still need complete live evidence. Do not label full P2 accepted.

The owner authorized staged offline Phase 3 work despite those remaining L01 cases. The first fixture is **Quezon City, Philippines, restaurants and cafes**. This is a small test target, not a permanent city/category restriction; remote software delivery does not constrain prospect geography.

The earlier `https://overpass-api.de/api/interpreter` probe timed out because the public Overpass server was at capacity (`HTTP 502 Bad Gateway: This Overpass API server is currently at capacity`). Although a diagnostic query to `https://api.openstreetmap.org/api/0.6/map.json` returned HTTP 200 in 2.19 seconds, the OSM editing API usage policy prohibits read-only projects, so `map.json` is rejected in code and does **not** resolve **D12** or pass **L03**. Live discovery remains disabled in configuration (`enabled = false` enforced), and **D11**, **D12**, and **L03** remain **OPEN**.

## Verification baseline

Last full suite executed at the application-code baseline:

```text
.venv\Scripts\python.exe -m pytest -q
486 passed, 37 warnings in 34.31s
```

Warnings are upstream discord.py Python 3.14 deprecations. This recorded result does not replace rerunning relevant tests after changes. Verified environment: Windows / CPython 3.14.6. Metadata permits Python 3.11–3.14; other environments are not established as tested.

```powershell
# Synthetic tests; no live Discord, source or AI-account calls.
.venv\Scripts\python.exe -m pytest -q

# Existing local database only; read-only, no credentials or network.
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
```

Last local checkpoint: READY; 16 resources, 21 command mappings, nine output mappings, four panels, zero jobs/hunts and no integrity/FK errors. The checker deliberately does not claim live acceptance. Do not reset the real database or insert synthetic observations into it.

Tests: [Philippines extract integration](tests/integration/test_philippines_extract.py), [registry integration](tests/integration/test_registry.py), [normalization](tests/unit/test_registry_normalization.py), [query planner](tests/unit/test_discovery_planner.py), [parser](tests/unit/test_overpass_parser.py), [setup](tests/integration/test_discord_setup.py), [transport](tests/integration/test_discord_transport.py) and [policy](tests/unit/test_discord_policy.py).

## Next work, when assigned

Continue Phase 3 rather than later AI/CRM features. Useful separable tasks are:

1. Versioned non-AI campaigns and targeting/geography validation against the existing schema and command contracts.
2. Durable query/attempt history and conservative coverage, including empty, duplicate-only and partial outcomes with persisted budgets.
3. Bounded worker admission, leases, cancellation, interruption recovery and fresh authorization, using fake sources until the real source gate passes.
4. Identity-review resolution and parent/branch validation with named actors, revision checks and no retroactive credit.
5. Source feasibility under a separately explicit bounded test. Real transport requires source approval, tested network restrictions, attribution, rate limits and L03 evidence.

Use the [configuration](docs/23-IMPLEMENTATION-GUIDELINES.md), [command](docs/07-DISCORD-COMMANDS-AND-INTERACTIONS.md) and [job](docs/17-BACKGROUND-JOBS.md) contracts. Obtain an owner decision before changing a blocked mandatory requirement. Keep absent functionality visibly unavailable.

## Local operations and collaboration

- The owner-approved cat banner and plain README identity are intentional. Operating instructions live in [local operations](docs/LOCAL-OPERATIONS.md).
- `run-local.ps1`, `config.toml`, `.env`, runtime databases/logs and local `AGENTS.md` are ignored. Only [run-local.example.ps1](run-local.example.ps1) is tracked. The token cache uses Windows account-bound encryption outside the repository; never put credentials in handoffs, logs, fixtures or Git.
- Do not start a second bot against the same data directory, change live channels, confirm provisioning, run source probes or execute provider tasks merely to onboard. Use synthetic tests/read-only checks and the assigned scope.
- Do not overwrite or commit another tool's unfinished work. Use focused Conventional Commit messages and retain milestone tags. Repository: `manwelAC/mi-boti`.
- After substantive work, update acceptance and this snapshot as appropriate. Report behavior, changed files, actual checks, limitations and manual inputs. Offline test success does not complete Phase 3.

## Latest source-direction decision and live L03 verification — 2026-11-14

The owner approved the local Geofabrik Philippines OSM extract direction ([docs/PHILIPPINES-EXTRACT-PLAN.md](docs/PHILIPPINES-EXTRACT-PLAN.md)). Optional `osmium==4.3.2` (PyOsmium) has been installed and verified on Windows / CPython 3.14.6, the bounded downloader/importer and `PhilippinesExtractAdapter` have been implemented and covered by synthetic tests (`tests/integration/test_philippines_extract.py`, including failure-injection recovery tests for immutable snapshot generation pointers, deferred cross-database cursor acknowledgement, and subprocess-isolated PBF parsing), and live `L03` verification passed against the actual 613,918,681-byte `philippines-latest.osm.pbf` (`sha256: aaf01a39336ff80a049935c66199f3786f2ece65a2f056e9ebf350f60ec191c7`, provider MD5 `690772965227a78819ee413182ee38ba`, snapshot time `2026-11-13T21:22:20.000000Z`) in a disposable SQLite workspace without touching the production database. Production discovery remains disabled in configuration (`enabled = false` enforced in `config.py`). AI execution, scoring, and autonomous hunting remain disabled.

## Latest Codex follow-up — 2026-11-14

The owner asked Codex to apply the final checkpoint-lock and DNS-test fixes to the shared uncommitted implementation. Checkpoint acknowledgement now actually acquires publish.lock before active-generation validation/cursor writes. A native OS-lock contention regression proves it cannot write while another owner holds that lock and can acknowledge after release. The stalled-DNS regression explicitly establishes a blocked resolver before exercising admission/retries, uses a unique limiter key and cleans up its own threads, removing the 100 ms startup scheduling race. Its production timeout rules remain unchanged.

Verification: the two focused regressions passed; the DNS regression passed five consecutive separate invocations; the full suite passed 487 tests with 37 existing discord.py warnings in 31.14 seconds. See the latest doc 22 record for exact results. No application version, source enablement, runtime data or Discord resources changed. The Phase 3 changes are still uncommitted; coordinate before committing or starting further work.

## Saved checkpoint — 2026-11-15

The owner requested committing and pushing the current combined Phase 3 implementation before stopping work for the day. The latest executed full suite passed 487 tests with 37 existing SDK warnings (31.14s); no application code changed after that verification. Checkpoint acknowledgement acquires the publication lock, and the synchronized stalled-DNS regression passed five additional runs. Next session: finish the Discord identity-review resolution UI and the live /campaign to /discover operator walkthrough, then assess full Phase 3 acceptance. Production discovery, AI and hunting remain disabled. v0.2.0 remains the last tagged release; this checkpoint is unreleased Phase 3 work, not a completed-phase release.

## Tool guide addition — 2026-11-16

The owner requested a channel to learn every tool. Added the guide resource/panel, /guide canonical mapping, dashboard link and a complete operator help catalog. It explains current availability, example usage, assigned channels and result meanings; planned workflows remain visibly unavailable. The manifest is now 17 resources, 22 canonical commands, nine output destinations and five panels. Existing server setup must be explicitly upgraded through /setup preview and confirmation after restart; startup creates nothing automatically. Automated verification: 502 full-suite tests pass; the final focused guide/Discord rerun passed 23 tests. There are 39 upstream SDK warnings. Live guide rendering is pending owner confirmation; no Discord resources or production data were changed by development. Continue with the remaining Phase 3 UI/live checks after the guide upgrade.

## Identity-review UI checkpoint — 2026-11-16

Added private /lead open-review queue and review/business inspection. action:link target:<business UUID> rationale:<reason> or action:separate rationale:<reason> presents an actor-bound five-minute confirmation. Fresh authorization, target revision checks and the existing audited repository transaction protect decisions. No CRM qualification, scores or quota credits are created. The operator guide now describes this implemented subset. Full suite: 512 passed, 108 existing SDK deprecation warnings in 24.75s; compileall and pip check passed. AGENTS remains ignored/untracked. Production discovery and AI/hunting remain disabled; live Discord rendering and campaign/discovery walkthrough are next. Restart the bot to synchronize /lead arguments; any missing guide resources still require explicit /setup preview and confirmation.

## Prepared production snapshot — 2026-11-16

The current local data root lacked a dataset; explicitly downloaded/imported the official Geofabrik Philippines extract and independently verified it. Snapshot c89257a5-e373-426f-9b2b-d86640775829 has observation time 2026-11-15T21:22:28Z, 22,484 nodes / 3,562 ways / 48 relations, one incomplete geometry and conservative PARTIAL coverage. See doc 22 for hashes and actual output. Ignored config.toml now enables only the approved local source; code accepts its reviewed policy while rejecting public Overpass/unknown sources/AI. No production business/job records were inserted. Full tests: 518 passed, 108 SDK warnings in 22.61s; compileall/pip check passed. Status replies now reflect actual configuration. Owner must restart the existing bot and run /discover campaign_id:20b231bc-f9f5-48b3-b6d5-27030fda56c8 limit:10 in lead-discovery. Finish live Phase 3 checks before Phase 4a website fetching. Website fetching remains planned; do not describe snapshot searches as live research.

## Saved discovery result browser — 2026-11-16

Owner verified the first live discovery job 70ac3fe6-5d59-41e8-ab0e-bf7201d0ba72 succeeded with ten new observations and no duplicates/ambiguities. Added private ten-item pages and source-detail dropdowns after completion, plus /discover job_id:<UUID> page:<int> for existing results without a new search. Fresh discover authorization and actor/expiry binding apply to components; no identity actions cross channel boundaries. Full suite: 525 passed, 174 existing SDK warnings in 21.22s; compilation and pip check pass. Restart then reopen that saved job in lead-discovery to verify rendering. No live Discord interaction or production-data mutation was performed during this code change. Phase 3 full acceptance and Phase 4a remain separate pending work.

## Staged Phase 4a foundation — 2026-11-16

Owner verified discovery cards/dropdown through screenshots. Fixed empty address/JSON-limitations presentation. Added research/collector.py and repositories/research.py: reviewed exact-host policy input, robots checks, public-IP pinning/SNI, bounded asynchronous collection and immutable lease-guarded evidence checkpoints. Automated total: 553 passed, 174 SDK warnings in 38.90s; focused collector 26 passed; compileall/pip check pass. No live website calls, credentials or runtime registry changes. /research remains unavailable pending persistent reviewed-site policy/admission, durable worker/cancellation/restart wiring, configuration-driven limits, research UI and real integration checks. Use one shared collector for runtime host/DNS admission; do not create one per job. Conservative initial collector rejects compression and unsupported robots syntax; no browser or provider fallback. Evidence is literal source assertion, never proof of absent internal software. See docs09/22 for explicit limitations; do not mark Phase4a complete.

## Phase 4a command/worker integration — 2026-11-16

Implemented /research collect/status/cancel/review/revoke in business-research. Review/revoke require administrator; confirmation is actor-bound, five-minute and config-revision checked. Active seven-day exact-host policies/rationale are persisted in guild_config.settings_json.research_access (64-record cap), with audit history. No migration/new dependency. Collector is shared per application loop; configured limits remain within conservative hard caps. Worker checks fresh permissions/policy before each dispatch and commit, polls cancellation/policy once per second, renews owned lease, aborts before settlement, and commits evidence/run/job success atomically. Restart interrupts queued/running RESEARCH jobs and runs; no automatic restart. analyze:true fails before enqueue; AI, scoring, CRM qualification and hunting remain disabled.

Final full suite: 572 passed, 261 existing SDK warnings in 48.82s; compileall/pip check/diff check pass. Native DNS is bounded daemon work with cancellation admission retained until completion. Live HTTPBin collector and disposable full worker/evidence probes succeeded (two requests, one page/run/evidence, zero findings/scores/leads/credits). Real Discord auth was simulated in that fixture; no live business-site or Discord research acceptance is claimed. First fixture setup lacked guild_config and failed before fetching, then was corrected; missing setup is now a safe error. See doc22 for exact output, hash and fixture path. Production business data unchanged; ignored local research.user_agent uses the descriptive repository contact. No production access review was approved by development.

Next: restart the owner's existing bot to sync /research arguments, choose an official business URL (none of the first ten observations supplied one), inspect permitted access and confirm /research action:review, then run refresh:true and verify the saved card/reopen flow. An optional question asking which business/website to check was sent; no answer is assumed. Full Phase4a and remaining Phase3 live gates stay unaccepted. v0.2.0 remains last tagged release.

Owner response: no sample site available. Agent identified https://maxschicken.com/ as the official brand-site candidate through read-only web lookup. Branch identity and automated-access permission remain unverified; browsing could not establish robots access. No business-site policy or production collection was approved. Do not ask the owner to supply a sample as if development cannot proceed; use the completed technical fixture for current transport evidence and validate an eligible real site before business research acceptance.

## Live permitted source and continued evidence/guide development — 2026-11-16

Owner authorized autonomous testing and continued work; do not keep asking them to supply sample data. Official https://www.scrapethissite.com/faq/ explicitly permits automated access under robots/user-agent/one-request-per-second rules. Live countries sandbox collection succeeded; Books to Scrape stopped after robots/policy failure. A full isolated training-service homepage collect+refresh succeeded twice, with a shared robots cache, two immutable evidence snapshots, original row unchanged, and zero findings/scores/leads/credits. This is source validation, not a Philippine lead or owner production approval. Production data was untouched and Discord authorization was simulated. Report: .pytest_cache/live-research/c5518c2d3276499780bbbcaec1f6aff9/LIVE-RESEARCH-REPORT.md; country-page viewer report in sibling fa329e6ff4b44ebf9c643ed1b28d0725 fixture shows 16 saved-text pages. See doc22 for actual timestamps/hash/output.

Then implemented administrator-only /guide refresh:true (edit existing managed bot-authored card only; no creation/startup republish), result-card evidence dropdowns and /research action:evidence evidence_id:<UUID> page:<int> for complete saved-text pages. Evidence controls are actor/expiry/policy checked, show source/time/policy/confidence/limits and never fetch/modify data. Extraction flags text caps explicitly. Full suite: 584 passed, 341 SDK warnings in 51.03s; after final card-label refinement, focused reader/transport/guide rerun: 35 passed, 143 warnings in 5.03s. Compileall/pip check pass. Real successful research delivery and refreshed-guide rendering in Discord remain pending; do not claim P4a/full Phase3 acceptance or production readiness. Existing real bot must restart for new options, then owner/admin can refresh its saved guide once. AI/hunting remain disabled and v0.2.0 remains last tag.

## Research recovery and readiness checkpoint — 2026-11-16

Added research_integrity verifier (same-business run/evidence, RESEARCH job ownership, retained evidence for successful runs and literal excerpt hash integrity) to basic verified backup checks. Added a credential/network-free read-only scripts/check_research_prerequisites.py. It checks migrations/schema/FK/research integrity and local counts but always full_phase4a_accepted:false. Production checkpoint passes locally with zero research/evidence/reviews/active research jobs; no synthetic test records were added.

Actual abrupt-process-exit/backup/restore/initialize drill exposed temporary .partial-wal/.partial-shm leftovers that made a restored root fail normal startup confinement. Fixed by sealing private output copies in DELETE mode and cleaning exact generated companions. Active source stays WAL. Corrected drill at .pytest_cache/research-recovery/f7616972fed74d26aff63fb1d42789a2 passed: two evidence rows and one access review unchanged, crashed job/run INTERRUPTED, zero running jobs, zero partial sidecars, no network/provider calls or production changes. Report: RECOVERY-REPORT.md/result.json. Full tests: 591 passed, 361 existing SDK warnings in 51.66s; final focused recovery/storage/checkpoint run 23 passed in 1.86s; compilation/pip check pass.

Computer-use inspection found an open Discord session, but navigation/input recovery failed with coordinate input geometry is unavailable then user input was detected in this window. Stopped without submitting slash commands or modifying server content. Existing owner-reported refusal paths passed; real successful research/evidence delivery remains the outstanding L01 check. Do not mark P4a accepted or begin Phase6 implementation on the strength of local backup tests. No sample data is required from the owner for local tests; retain the live permitted-source fixtures. v0.2.0 remains last tag, AI/hunting disabled.

## Owner-authorized isolated CRM increment — 2026-11-16

Owner explicitly approved Begin isolated CRM development while P4a successful live-Discord research delivery remains open. FINAL README decision D16 and roadmap exception record this; local AGENTS adds §25 after unchanged mandatory prefix (SHA256 3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259). This supersedes earlier instructions to wait before any Phase6 code only for isolated unreleased development; it does not accept either phase, enable CRM commands or waive safety.

Added domain/crm.py, repositories/crm.py and services/crm.py plus integration/test_manual_crm.py. Core supports confirmed manual qualification with same-business public evidence/rationale and revision/identity guards, the full stage graph with READY contacts/manual-contact attestation/outcome/reopen requirements, atomic pending follow-ups, append-only note corrections and bounded named reads. Service injects fresh async authorization and rechecks persisted guild/channel/role policy inside transactions. Literal evidence hash validation is shared with research_integrity. No score/credit/provider/outreach writes or runtime data changes; no migration/dependency/bot registration. Full suite 680 passed, 361 existing SDK warnings in 59.57s; focused CRM/recovery 94 passed; compileall/pip check pass. Tests cover 64 independent graph pairs, invalid prerequisites, concurrency, immutable notes and backup/restore persistence.

Next isolated work: reviewed contact capture, CRM confirmation/detail/list/notes UI adapters, then manual drafts/follow-up delivery/exports under existing specs. Contact rows can be validated/selected by the current READY guard but a production contact-entry workflow is not implemented. Confirmed service flags are not a substitute for actor-bound real Discord previews. Keep CRM guide entries/commands unavailable until wired and accepted. P4a successful live-Discord delivery remains open; no sample/secret input is needed for offline core work. v0.2.0 remains last tag; AGENTS stays local.
