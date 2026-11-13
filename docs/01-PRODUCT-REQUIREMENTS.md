# 01 — Product requirements

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

This normative inventory links product behavior to the [traceability matrix](22-ACCEPTANCE-CRITERIA.md). [00](00-PROJECT-OVERVIEW.md) defines terms; component documents supply implementable contracts.

## Actors

Owner: configured user ID within the configured guild. Administrator: live guild member with administrator permission. Both may configure setup, mappings, grants, and backups. Operator: owner, administrator, or member of an explicitly configured operator role; may operate campaigns, hunts, discovery, research, CRM, drafts, and follow-ups. Ordinary members are denied privately. Recheck membership and roles on every command and component. Owner-only deployment settings remain local; no role grants bypass guild checks.

## Mandatory requirements

| ID | Behavior |
|---|---|
| R01 | Python/discord.py, Discord-only interface, local hosting and SQLite authority |
| R02 | Authorized setup preview/confirmation, idempotent provisioning, persisted IDs, preserved unrelated resources, approved deleted-resource recovery |
| R03 | Guild/user/action/channel/config checks before operational work; wrong-channel ephemeral denial; no job enqueued |
| R04 | Free permitted discovery, source policies, attribution/provenance, throttling, timeouts, bounded retries, query/coverage history |
| R05 | Global persistent registry of all dispositions; multiple identity signals, separate branches, no ambiguous auto-merge |
| R06 | Public source evidence, UTC observations, confidence and limitations; separate facts, inferences and unknowns |
| R07 | Configurable explainable scoring and evidence gates; missing data is not a weakness |
| R08 | Local subscription CLI adapters; real compatibility and allowance verification; unknown/exhausted fails closed |
| R09 | No automatic provider switching, metered API fallback, fabricated usage or prohibited authentication automation |
| R10 | Authorized manual hunt start/resume; new unique qualified quota; pause/stop/status; accurate partial summaries |
| R11 | Bounded persistent jobs, retries, requests, candidates, duration, concurrency and cancellation; no startup/reconnect hunting |
| R12 | Atomic identity and quota credit; no concurrent duplicate credit or notification-driven counting |
| R13 | Persistent CRM, notes, stages, history, public contacts, follow-ups and draft review |
| R14 | Human-reviewed manually sent outreach only; no external sending capability |
| R15 | Authorization, safe URLs/SSRF defense, safe subprocesses, redaction, audit and explicit failure handling |
| R16 | Migrations, constraints, transactions, backups, artifact integrity, recovery and real integration verification |

## Workflows

Setup: `/setup` → authorized preview → actor-bound expiring confirmation → provision/persist each resource → publish controls → complete or partial summary. A changed plan requires new confirmation.

Hunt: select active campaign → `/hunt start quota:25` → snapshot/eligibility → reserve session slot → bounded worker loop → reason and counters. Pause/resume/stop are concurrency-safe and idempotent. Provider changes require terminating the hunt and starting another. Hunt admission snapshots quota-scaled resource and active-time budgets. The base hunt.max_active_seconds is 3600 seconds per quota block; only RUNNING/PAUSING/STOPPING consume active time. PAUSED/INTERRUPTED consume none. hunt.max_age_seconds is a separate 604800-second absolute ceiling. Resume rechecks both without resetting counters; doc 17 defines the exact formulas.

Manual discovery: `/discover campaign:<id>` performs discovery and registration only, with no AI or qualification. Its businesses are existing in future hunts and cannot count as new. `/research business:<id> refresh:true` explicitly collects and stores permitted public website evidence without AI or quota credit. Its analyze option defaults to false; analyze:true is a separate Phase 4b feature gated by provider verification and allowance.

CRM: `/qualified` or `/leads` → `/lead` → evidence review → notes/stage → generate draft → named human approval → operator manually sends elsewhere → records sending and follow-up. Approval never sends.

## Invariants and edge cases

Only committed qualification creates quota credit, never source counts or AI claims. Existing unqualified businesses later qualified may create leads but no new credit. Refresh is explicit even for rejected records. Archiving/contacting never erases identity memory. Ambiguous candidates remain durably remembered and blocked from automatic research.

If no provider passes L02, the owner-authorized release is phases 1–3, Phase 4a and non-AI phase 6: setup, command restrictions, discovery, registry/dedup, safe website research/evidence, CRM and manual drafts. All AI features are visibly disabled and autonomous hunting remains unreleased. Operators can manually qualify registry businesses using public evidence and create manual drafts without a CLI or artificial score; neither operation earns quota credit. AI-dependent operations fail with guidance. Disabled MCP cannot block core operation. Lost authorization during a job stops new privileged work and safely interrupts it.

## Acceptance

Every R ID maps to a specification, test, phase and observable gate in [22](22-ACCEPTANCE-CRITERIA.md). Negative cases include wrong guild/channel, unknown allowance, duplicates, unresolved identities, restarts, deleted channels, unsupported CLI and attempted sending. Mocks cannot prove real subscription compatibility.
