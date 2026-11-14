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
| Phase 0 feasibility | CLI/source assessments and bounded source probes recorded | No fully verified runtime AI provider or production discovery source |
| Phase 1 foundation | Python package, strict config, redacted logs, private storage, deployment lock, 41-table checksummed SQLite migration, artifacts and verified-copy backup/restore primitives | Later workflow-specific recovery/release validation |
| Phase 2 Discord | Guild-scoped commands, fresh authorization, ID-based restrictions, private setup preview/confirmation, setup journal, idempotent resources, four persistent panels, staged role/mapping edits | Full L01 acceptance remains incomplete |
| Phase 3 core | Offline normalization, transactional registry reservations/claims, ambiguity holds, duplicate provenance, open-review reuse, explicit branch distinctions, bounded query planner and Overpass JSON parser | Live source transport, campaigns, worker wiring, query/coverage lifecycle, review-resolution UI and parent-link management |
| Phase 4a research | Specified only | Safe website collection, policy/robots enforcement, evidence workflow and non-AI /research |
| Phase 4b / Phase 5 | Specified only | Provider adapters, findings/scoring and autonomous hunting, subject to their gates |
| Phase 6 CRM/outreach | Specified only; tables exist | Lead workflow, manual qualification, pipeline, notes, follow-ups and manual drafts |

A table, parser or slash-command registration is not an enabled end-to-end feature. Many registered commands deliberately return unavailable status. `/discover`, research, CRM, AI and hunting are not usable yet.

## Current Phase 3 behavior

- [domain/registry.py](src/mi_boti/domain/registry.py) normalizes Unicode names, structured addresses, IDNA hostnames and published contacts. Website/phone/email signals are supporting, never globally unique claims. Missing data is not inferred.
- [repositories/registry.py](src/mi_boti/repositories/registry.py) requires an existing RUNNING query and current uncancelled DISCOVER lease. BEGIN IMMEDIATE serializes identity rechecks and reservations. Every disposition participates; origin job/hunt ownership stays immutable.
- Conflicting identities create review holds rather than automatic merges. Repeated unresolved observations across queries reference the existing open review while retaining their candidates. Registry calls create no research, leads, scores, AI executions or hunt credits.
- [discovery/planner.py](src/mi_boti/discovery/planner.py) uses fixed templates, finite boxes, cafe/restaurant tags and deterministic fingerprints. Planning grants no permission to execute a request.
- [discovery/overpass.py](src/mi_boti/discovery/overpass.py) translates bounded JSON offline, preserves node/way/relation identifiers and attribution, and marks remarks/output-cap hits incomplete. It contains no live HTTP client.
- No dependency or migration changed for this increment. Applied SQL/checksum manifests are immutable; use a new migration for schema changes.

## Live evidence and owner decisions

The owner verified setup, repeat setup, wrong-channel rejection, mapped-channel status, commands after restart, persistent hunt-control buttons after restart and a button response after renaming its channel. The solo-server owner deferred the second-user live authorization test: **NOT PERFORMED**, not passed. Automated authorization tests remain mandatory. Deletion/recovery, permission-loss paths and measured interaction timing still need complete live evidence. Do not label full P2 accepted.

The owner authorized staged offline Phase 3 work despite those remaining L01 cases. The first fixture is **Quezon City, Philippines, restaurants and cafes**. This is a small test target, not a permanent city/category restriction; remote software delivery does not constrain prospect geography.

The latest source probe made one direct HTTPS request to `https://overpass-api.de/api/interpreter`, using a small box `(14.648,121.047,14.657,121.061)`, five output elements and a 20-second total deadline. It raised ReadTimeout after 18.70 seconds. There was no successful business response, production import or endpoint rotation. This is not an empty-market result; the reason for the delay is unknown.

Public Overpass policy warns against sustained general-application backend use. A successful manual probe would not approve production access. D12 remains OPEN. A local Philippines OSM extract was discussed, but was **not selected, downloaded or implemented**. Do not silently switch endpoints or add an importer/dependency. D11 runtime provider selection/verification also remains OPEN.

## Verification baseline

Last full suite executed at the application-code baseline:

```text
.venv\Scripts\python.exe -m pytest -q
404 passed, 16 warnings in 10.67s
```

Warnings are upstream discord.py Python 3.14 deprecations. This recorded result does not replace rerunning relevant tests after changes. Verified environment: Windows / CPython 3.14.6. Metadata permits Python 3.11–3.14; other environments are not established as tested.

```powershell
# Synthetic tests; no live Discord, source or AI-account calls.
.venv\Scripts\python.exe -m pytest -q

# Existing local database only; read-only, no credentials or network.
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
```

Last local checkpoint: READY; 16 resources, 21 command mappings, nine output mappings, four panels, zero jobs/hunts and no integrity/FK errors. The checker deliberately does not claim live acceptance. Do not reset the real database or insert synthetic observations into it.

Tests: [registry integration](tests/integration/test_registry.py), [normalization](tests/unit/test_registry_normalization.py), [query planner](tests/unit/test_discovery_planner.py), [parser](tests/unit/test_overpass_parser.py), [setup](tests/integration/test_discord_setup.py), [transport](tests/integration/test_discord_transport.py) and [policy](tests/unit/test_discord_policy.py).

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
