# Changelog

Versions use MAJOR.MINOR.PATCH with annotated v tags. Releases before 1.0 are development milestones, not production-readiness claims.

## Unreleased

### Guide maintenance and evidence reading

- Add administrator-only /guide refresh:true to edit the existing managed guide card without provisioning or creating messages.
- Add actor-bound saved-evidence selection and full-excerpt paging through /research action:evidence; preserve source metadata and immutable text without a new fetch.
- Disclose extraction caps explicitly, and verify real permitted website collection/refresh in isolated fixtures.

### Non-AI research workflow

- Connect /research to durable background jobs and immutable evidence cards, with explicit refresh, saved status, cancellation and restart interruption.
- Add administrator-confirmed seven-day exact-host website-access reviews and revocation with audit history. Recheck current authorization, leases and policy before each fetch and final commit; keep AI analysis disabled.
- Verify real HTTP collection against HTTPBin in a disposable SQLite fixture; real Discord/business-site acceptance remains pending.

### Staged research foundation

- Replace empty discovery addresses and raw limitation arrays with readable text.
- Add a provider-free website collection engine and immutable research/evidence repository with safety and provenance tests. The subsequent runtime integration is recorded above; real Discord/business-site validation remains pending.

### Discovery results browsing

- Add private paginated saved-observation cards and source-detail selection after discovery completion. Reopen historical results with /discover job_id without running another search. Recheck authorization on every component; identity mutations remain in lead-pipeline.

### Operator guide

- Add a private guide channel, persistent tool guide, dashboard link and /guide command. Document all command mappings, usage and availability; existing servers add it through a reviewed setup upgrade.

### Phase 3 core

- Add private `/lead` registry inspection and paginated identity-review queue, with source/match details, actor-bound decision confirmations, fresh authorization and optimistic target revision checks. CRM qualification and quota credit remain outside these actions.

- Add normalized public observations, transactional global identity reservations, ambiguity holds and cross-query review reuse with immutable origin ownership.
- Add a bounded fixture query planner and offline Overpass JSON parser; test separate-connection duplicate races, all dispositions, branch distinctions, provenance and stale-worker rejection.
- Add versioned non-AI PH campaign validation/storage (`/campaign create|list|edit` and `active_campaign_id` via `/config set`), durable query/attempt/coverage lifecycle (`FRESH`, `EXHAUSTED`, `PARTIAL`) with request budgets, bounded manual discovery job admission/leases/worker/recovery (`/discover`) with non-blocking async execution, periodic lease heartbeats and fresh per-step authorization, and identity-review/hierarchy resolution with cycle prevention.
- Implement `OverpassDiscoveryAdapter` with pinned-IP SSRF connections (preserving `Host` and TLS `sni_hostname`), mixed-DNS/IPv4-mapped IPv6 rejection, and process-wide rate limiting (`>=10s`, concurrency `1`, `Retry-After` enforcement). Reject `/api/0.6/map.json` per OSM editing API policy; keep live discovery (`D12`/`L03`) and AI/hunting (`D11`/`L02`) disabled until their gates pass.

### Verification tooling

- Add a read-only Phase 2 prerequisite checker with tests for missing databases, incomplete configuration and persisted mapping validation. Record owner-confirmed persistent-button recovery and remaining Phase 3 admission requirements.

### Documentation

- Redesign the README around a personal workspace identity, with the approved wide cat-and-laptop banner, plain typography, milestone overview and compact navigation.
- Move the installation and launch walkthrough to the local operations reference.

## 0.2.0 — 2026-11-14

### Added

- Guild-scoped Discord startup and 21 canonical command keys with owner/admin/operator and channel authorization.
- Private setup previews, explicit confirmation, durable provisioning journals, idempotent resources and four persistent panels.
- Staged role/channel mapping changes, conservative partial/uncertain recovery and restored component routing after restart.
- A Windows launcher template with account-bound encrypted token caching outside the repository and a ResetToken option.
- Discord policy, SQLite setup, interaction and SDK transport regression tests; versioned documentation and acceptance records.

### Fixed

- The SDK rate-window setting that could reject available requests in a 60-second reset window.
- Missing-permission and rate-limit diagnostics, SDK log redaction and Windows import-side-effect verification.
- README Markdown presentation and Git exclusions that omitted documentation and tests.

### Verification and limitations

- Automated suite: 337 tests pass on Windows / CPython 3.14.6; 16 upstream discord.py deprecation warnings remain.
- Owner-confirmed live setup/repeat setup, correct/wrong-channel usage status and command response after restart.
- Full L01 acceptance remains pending, including independent-role denial, managed-resource deletion/rename recovery and explicit post-restart component checks.
- Discovery, research, CRM, AI execution and autonomous hunting remain unavailable. No provider has passed the full allowance gate; discovery source approval/connectivity remains unresolved.
- Credentials, operator-specific launcher, runtime SQLite databases and logs are excluded from Git.

## 0.1.0 — Foundation baseline

Python packaging, strict configuration, redacted logging, private storage, deployment locking, checksummed SQLite migrations and verified backup/restore primitives. The foundation passed 66 automated tests. This historical version was recorded in package metadata; no previous release tag is asserted.
