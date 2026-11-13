# 21 — Development roadmap

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and phase discipline

Follow the owner's phase contracts and the explicitly authorized non-AI MVP sequence; this document scopes deliverables and verification against [22](22-ACCEPTANCE-CRITERIA.md). Read [agent instructions](../AGENTS.md) and [implementation guidelines](23-IMPLEMENTATION-GUIDELINES.md). The owner has authorized Phase 0 assessment and Phase 1 foundation development; subsequent phases retain their documented gates.

## Phase 0 — Technical feasibility

Inventory candidate CLI products, versions, official distributions, subscription/billing mode, automation terms, authentication status mechanisms, allowance reporting and task isolation/cancellation. Use [10](10-AI-PROVIDER-INTEGRATION.md) procedure and L02; record VERIFIED/BLOCKED independently per adapter. Review approved Overpass/site policies and verify a small bounded source request (L03). Record OS/process-tree and SSRF-transport feasibility. Produce a compatibility matrix, sanitized evidence manifests and blockers; no autonomous hunting enabled.

Gate P0: real compatibility findings and source permission evidence exist; at least one provider must pass before AI execution can be enabled. If no provider passes L02, the release scope is phases 1–3, 4a and 6 (setup, discovery, registry, safe website research/evidence, CRM, manual drafts) with all AI features visibly disabled. Autonomous hunting remains unreleased until a provider passes. This fallback is already an owner decision, so it does not require another approval request. Complete the Phase 0 findings, deliver phases 1–3 and non-AI Phase 4a, and then deliver non-AI phase 6 while leaving Phase 4b and Phase 5 unreleased. This is not a waiver of the provider gate. Never assume a fallback API or relax the allowance requirement.

## Minimum viable slice — no AI

The MVP consists of confirmed/idempotent setup, strict command restrictions, permitted discovery, the persistent global business registry with deduplication and identity review, safe website fetching and stored evidence through `/research`, CRM with evidence-backed manual qualification, and manual draft creation/review/manual-send recording. It includes the storage, authorization, bounded-job, cancellation, error reporting, secret redaction and basic verified-backup controls needed for those features. Campaigns may omit provider selection; CRM leads may have a MANUAL qualification origin and no AI score. AI commands must visibly explain that their L02/feature gate has not passed.

The delivery sequence is Phase 0 assessment, phases 1–3, Phase 4a, and the non-AI portion of phase 6. Phase numbers continue to identify their full contracts; this owner-authorized sequence does not renumber them or claim skipped AI work passed. Validate the applicable Phase 7 security/recovery checks before releasing the MVP. If a provider later passes L02, complete Phase 4b, Phase 5 and the AI additions to phase 6 before claiming autonomous release.

### Post-MVP work retained in the specifications

| Deferred capability | Contract retained | Safety required in MVP |
|---|---|---|
| Marker-based publication reconciliation and UNCERTAIN delivery state | [02](02-TECHNICAL-ARCHITECTURE.md), [04](04-DATABASE-SCHEMA.md), [19](19-ERROR-HANDLING.md) | Persist output jobs and known message IDs; hold unknown sends FAILED/DELIVERY_REVIEW_REQUIRED and require operator inspection before any resend; never replay qualification. Setup resource ownership reconciliation is not deferred. |
| Future MCP extension interface | [11 Future extension](11-MCP-INTEGRATION.md#future-extension-interface--post-mvp-conditional-on-authorization) | Keep MCP disabled, reject enablement and prevent inherited unreviewed CLI tools. Any later extension still needs explicit authorization and security verification. |
| Backup verification manifests beyond a basic verified copy | [05](05-LOCAL-STORAGE.md), [04](04-DATABASE-SCHEMA.md) | Use consistent online backup, reopen/hash/integrity/FK/schema checks, protected retention and a restore exercise. Required data must already be covered; expanded per-artifact manifests follow before artifact-rich release. |

These are sequencing changes, not removal of safety requirements. Use scoped test records from [20](20-TESTING-STRATEGY.md) and distinguish MVP acceptance from full autonomous acceptance.

## Phase 1 — Application foundation

Create Python package/tooling, typed config, secret redaction, data root/lock, migration runner, schema, repository ports, fake clocks/transports and test harness. Pin justified dependencies and document target Python/OS compatibility. Implement backup/artifact primitives needed for later data safety.

Gate P1: T04, configuration/redaction portions of T14, and base T16 pass. Invalid config/newer schema/unwritable data root stops startup; imports start no jobs. No production credentials required for ordinary tests.

## Phase 2 — Discord infrastructure

Initialize discord.py, register command registry/check pipeline, setup preview/confirmation/journal, permission policies, persistent IDs/mappings, output destinations and panels. Implement fail-closed handlers for not-yet-built features, not fake success.

Gate P2: T01–T03 and L01 infrastructure subset pass, including repeated setup/deletion recovery and no wrong-channel enqueue. Missing sandbox access is explicitly reported and blocks claiming real Discord completion.

## Phase 3 — Business registry and discovery

Implement approved source adapter, query planner/history, coverage, normalization, identity claims/reviews, branch representation, concurrency constraints and discovery-only operation. All dispositions remain globally discoverable for matching.

Gate P3: T05/T06 and L03 discovery subset pass; duplicate-only plans terminate; no paid source/Nominatim harvesting; ambiguous candidates held. No AI/hunts yet.

## Phase 4 — Research and AI intelligence

This phase has two independently gated parts. Phase 4a is part of the non-AI MVP. Phase 4b remains blocked for any provider that has not passed L02. Splitting delivery does not weaken website access, evidence, or subscription safeguards.

### Phase 4a — Non-AI website research and evidence

Implement safe HTTP/DNS transport with validated IP pinning, source permission and robots checks, per-host rate limits, bounded requests/extraction, immutable evidence and explicit refresh. `/research business:<id> refresh:true` collects and stores public observations without invoking any provider. Its default analyze option is false; no installed/authenticated CLI or allowance check is required for collection. Show source/final URL, observation time, extracted facts, confidence and limitations to the operator, and make the evidence available to manual CRM qualification and drafts.

Collection must not create AI findings, infer software opportunities, calculate lead scores, automatically qualify leads or award hunt credit. It must reject unresolved identity, forbidden access and unsafe URLs before fetching. If transport or policy checks cannot be verified, fail the affected research capability closed; the MVP research gate is not satisfied by a manual browser workaround. A blocked AI provider alone must not disable this non-AI path. Store mandatory facts/provenance in SQLite; apply the MVP's basic verified-backup rules to any required artifacts.

Gate P4a: T10 and the non-AI T11 provenance/identity/immutability/conflict cases pass, along with relevant T01/T03/T13/T14/T16 and L01 `/research`/L03 research checks. Prove with a provider spy that successful collection and every collection failure make zero CLI, allowance, AI-scoring or quota-credit calls. Phase 4a may pass while L02 remains BLOCKED.

### Phase 4b — AI analysis, qualification and scoring

Implement provider adapters/eligibility gates, structured findings, evidence-backed qualification and deterministic scoring using the evidence collected in Phase 4a. Enable only adapters supported by real Phase 0/L02 evidence; show unsupported candidates as blocked. An explicit `/research ... analyze:true` may request this additional analysis after collection, but it requires current provider eligibility and a fresh allowance gate before each AI task. It never makes an existing business eligible for new-lead quota credit.

Gate P4b: T08/T09, AI-specific T11, T15 and relevant T14 pass; L02 passes for every enabled provider; and P4a remains satisfied. Unsupported allowance, billing, execution isolation or output validation blocks the AI part without disabling safe evidence collection. Mock success is insufficient.

## Phase 5 — Autonomous hunting

Implement job claims, leases, lifecycle, cancellation, dual active/absolute-age clocks, quota-derived persisted budgets, manual admission, immutable snapshots, atomic credit, progress, partial summaries, stop conditions and restart checkpoints. Measure actual candidate/hour throughput and qualification yield against doc 17's estimate; validate quota 25 without weakening gates. Verify source exhaustion, unknown allowance, pause/resume/stop and concurrent quota boundaries.

Gate P5: T07/T09/T13/T18 and live sandbox lifecycle/recovery exercises pass; no automatic hunting or provider switching. Quota equals credits and never exceeds target.

## Phase 6 — CRM and outreach

For the MVP, implement lead/detail/history, evidence-backed manual qualification, stage transitions, notes, identity review UI, manual drafts, approval invalidation, manual-send attestation, reminders and sanitized exports. No external sender or AI provider is required. Add gated AI draft generation only after Phase 4b/provider acceptance, and keep it visibly disabled otherwise.

Gate P6: the applicable manual T12/T17 cases, export/security portions of T14 and L01 CRM subset pass for the non-AI release; AI-specific cases must separately pass before AI drafting is enabled; reminders and approval cause no external sends; changes survive restart.

## Phase 7 — Reliability and release validation

Run complete automated suite, real integration gates for enabled features, security review, backup/restore drill, interruption recovery and operational documentation. Validate current source/provider policy/version records, disk limits, output outage and full-disk behavior. Resolve all critical gaps.

Gate P7: all tests applicable to the declared release scope pass with evidence; unsupported providers are clearly disabled and no known critical security issue remains. The owner-authorized non-AI release uses the MVP test subset in doc 20 and must explicitly state that AI/hunting and post-MVP improvements remain unreleased. Full autonomous release still requires all applicable T01–T18 and L01–L04, enabled-provider L02 evidence, later phase gates and the retained post-MVP reliability checks. The approved fallback does not authorize calling the full autonomous product complete.

## Required phase report

After each phase, provide implemented features; exact created/modified files; commands/checks actually run; pass/fail/skip totals; live evidence; unresolved issues; required manual configuration; next recommended phase. Distinguish code complete, automated verified and real integrated. On blocked mandatory behavior, stop affected work and request a decision before changing requirements. Use [22](22-ACCEPTANCE-CRITERIA.md) gate IDs, not vague readiness claims.

## Current Phase 2 checkpoint — 2026-11-14

Phase 2 implementation is owner-authorized. Its offline infrastructure tests pass. The owner has verified real setup, repeat setup, channel enforcement, disabled-provider status and post-restart command response; the remaining L01 cases are tracked in doc 22. Do not claim P2 complete or advance to Phase 3 until the required live infrastructure checks are recorded.
