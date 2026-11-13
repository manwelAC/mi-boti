# 00 — Project overview

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and authority

This document defines the project's scope and vocabulary. The [requirements](01-PRODUCT-REQUIREMENTS.md), [architecture](02-TECHNICAL-ARCHITECTURE.md), and [agent rules](../AGENTS.md) provide the related contracts. The package is self-contained. AGENTS.md sections 1–22 take precedence over docs/01, which takes precedence over the other numbered documents. Developers consult the numbered documents relevant to the component they are changing.

## Scope and responsibilities

Discord provides the entire user experience. Services enforce application policy, SQLite owns structured durable state, local storage holds bounded artifacts, workers execute long-running operations, and adapters isolate public sources and local CLI tools.

The non-AI MVP includes confirmed setup, command restrictions, campaigns for discovery, a global business registry with deduplication, safe non-AI website research and immutable evidence, CRM review, manual drafts, follow-ups, basic verified backups, and audit records. An operator may manually promote a registry business into CRM using documented public evidence; this action does not create an AI score or hunt credit. Phase 4a supplies safe website collection without any provider. Phase 4b research intelligence, automatic scoring, AI drafts, and autonomous hunting follow only after the required provider gates pass. The full target product retains all of those specifications.

If no provider passes L02, the owner-authorized release covers phases 1–3, Phase 4a and the non-AI part of phase 6. All AI features remain visibly disabled, and autonomous hunting remains unreleased. The roadmap identifies [post-MVP reliability work](21-DEVELOPMENT-ROADMAP.md) without removing its safety requirements.

The application excludes automatic outreach, paid discovery, metered AI fallback, cloud dependencies, unrelated frameworks, and a separate dashboard. [MCP](11-MCP-INTEGRATION.md) remains disabled. The deployment baseline permits one configured guild and one active, paused, or interrupted hunt per local database. The global registry covers all campaigns and sessions in that deployment. Sharing a database among multiple guilds requires a revised security design.

## Vocabulary

| Term | Exact meaning |
|---|---|
| Business | A durable entity in any qualification or CRM disposition |
| Branch | A separate business with a parent relationship; a shared domain does not collapse branches |
| Candidate | A source observation awaiting identity resolution |
| Campaign | A versioned targeting, geographic, scoring and provider configuration; non-AI discovery does not require a provider |
| Hunt | A manually initiated session with an immutable campaign snapshot and a new-qualified-lead quota |
| New | A business first inserted by that hunt's discovery job and absent from the global registry before that insertion |
| Qualified | A business whose validated evidence and deterministic score satisfy automatic gates, or whose explicit manual review is recorded separately |
| Lead | A qualified business in CRM, with its manual or automatic qualification origin recorded; there is at most one lead per business globally |
| Refresh | Explicit research on an existing business that never earns quota credit |
| Evidence | A timestamped factual observation with provenance and limitations |
| Allowance | Reliably verified remaining subscription capacity, distinct from authentication |
| Unknown | Absent or unverified information that never proves business weakness |

## Workflows

For the MVP, an administrator previews and confirms setup. An operator creates a discovery campaign and runs a bounded discovery job. The registry resolves identities before creating records and holds ambiguous matches for review. The operator explicitly runs `/research business:<id> refresh:true` to collect permitted website observations into the evidence store without AI. The operator reviews those source-linked observations alongside discovery evidence, manually qualifies a business into CRM if warranted, and prepares a manual draft. A named human approves the draft and manually sends it outside Mi Boti.

For a later AI-enabled hunt, the operator selects a campaign with an eligible provider and manually starts `/hunt start quota:25`. Admission validates permissions, configuration, limits and live allowance. A worker queries an approved source, records coverage, resolves identity and reserves new candidates before research. Public research supplies evidence, a gated CLI task supplies structured findings, and a deterministic scorer evaluates qualification. One transaction creates the lead and quota credit, after which a durable publication job delivers the result.

A pause prevents new dispatch and settles in-flight work before entering PAUSED. Resuming requires an explicit authorized action and fresh eligibility checks. Active-time accounting stops during PAUSED and INTERRUPTED, while the seven-day absolute-age ceiling continues. Stopping preserves partial results. Restart marks unfinished hunts INTERRUPTED and never resumes them automatically. An exhausted search plan produces an accurate partial summary.

## Failures and acceptance

Unknown allowance disables AI execution. An ambiguous identity remains held for review without automatic research or credit. A failed Discord delivery never repeats qualification; uncertain sends are held for operator inspection in the MVP and receive marker-based reconciliation post-MVP. Incomplete configuration fails closed before a job is enqueued.

A reviewer must be able to explain these terms and trace each requirement through [22](22-ACCEPTANCE-CRITERIA.md). Documentation review must distinguish design contracts, the non-AI release scope, and verified runtime capabilities. It does not establish application readiness.
