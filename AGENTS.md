# AGENTS.md — Mi Boti Development Instructions

## 1. Purpose

This document defines the mandatory development instructions, architectural constraints, implementation standards, and verification requirements for AI coding agents working on Mi Boti.

Mi Boti is a locally hosted, Discord-native AI lead intelligence and prospect management application.

The application discovers businesses through free public data sources, researches their operations, identifies potential custom software development opportunities, scores qualified prospects, and manages them through a Discord-based CRM.

**All implementation decisions must follow the project documentation.**

Do not assume familiarity with any other project, repository, application, or previous conversation.

## 2. Mandatory Development Rules

1. Read `README.md` and all relevant files inside `docs/` before implementing a feature.
2. Follow the documented architecture and technology stack.
3. Do not introduce unrelated frameworks, databases, cloud infrastructure, or frontend applications.
4. Do not implement undocumented product features without authorization.
5. Keep modules independently testable and responsibilities clearly separated.
6. Implement functionality in the order defined by the development roadmap.
7. Verify each implementation phase before proceeding.
8. Report incomplete features, assumptions, technical limitations, and failing tests.
9. Never report a feature as complete without appropriate verification.
10. Preserve existing functionality when modifying implemented modules.

## 3. Technology Constraints

The required application stack is:

| Layer | Technology |
|---|---|
| Runtime | Python |
| Discord framework | discord.py |
| Application database | SQLite |
| Local storage | Filesystem |
| HTTP requests | HTTPX |
| HTML parsing | BeautifulSoup |
| Optional browser automation | Playwright |
| Business discovery | OpenStreetMap, Overpass API, permitted public sources |
| AI execution | Locally installed, subscription-authenticated AI CLI tools |
| Deployment | Local machine or dedicated self-hosted computer |

Additional Python packages may be introduced when justified and documented.

Do not introduce PostgreSQL, Supabase, Firebase, Redis, Next.js, React, or a separate web dashboard unless the project requirements are explicitly revised.

## 4. Discord-First Architecture

Discord is Mi Boti's primary user interface.

The application must use native Discord capabilities, including:

- Slash commands.
- Embeds.
- Buttons.
- Select menus.
- Modals.
- Persistent interactive components.
- Channel-based dashboards.
- Private interaction responses.
- Notifications and activity logs.

Do not create a separate web-based administration interface.

Long-running operations must execute outside Discord interaction handlers. Interactions must be acknowledged within Discord's required response window.

## 5. Discord Server Setup

Mi Boti must provide an authorized `/setup` workflow.

The setup process must:

1. Verify the requesting user's authorization.
2. Verify the bot has sufficient Discord permissions.
3. Inspect existing Mi Boti categories and channels.
4. Present a preview of proposed changes.
5. Request confirmation.
6. Create missing categories and channels.
7. Configure command-channel restrictions.
8. Configure output destinations.
9. Publish initial control panels.
10. Persist Discord resource identifiers in SQLite.

Setup must be idempotent.

Running `/setup` repeatedly must not create duplicate resources.

Deleted channels must not be silently recreated without administrator approval.

The application must not modify unrelated Discord channels or categories.

## 6. Strict Command-Channel Restrictions

Every operational slash command must be associated with an authorized Discord channel.

Before executing a command, validate:

- Discord guild identifier.
- Discord channel identifier.
- User authorization.
- Command-specific permissions.
- Configuration completeness.

Command-channel mappings must be stored in SQLite using Discord snowflake identifiers.

Channel names must not be used as authoritative identifiers.

When a command is executed in the wrong channel:

1. Reject execution.
2. Return an ephemeral response.
3. Identify the correct channel when available.
4. Do not enqueue or execute the requested operation.

Unconfigured commands must fail closed.

The initial setup command may use a restricted bootstrap exception for authorized administrators.

## 7. Autonomous Hunting Rules

Hunting must never start automatically when the bot launches, reconnects, or restarts.

Only an authorized user may initiate hunting.

A hunting session must have a configured qualified-lead quota.

For example:

`/hunt start quota:25`

The quota represents the number of newly qualified, unique business prospects to record.

Previously discovered businesses must not count toward the quota.

A hunting session must support:

- Start.
- Pause.
- Resume.
- Stop.
- Status inspection.

A session must terminate when:

- Its qualified-lead quota is reached.
- The operator explicitly stops it.
- The selected AI provider's allowance is exhausted.
- AI subscription allowance cannot be reliably verified.
- A configured execution safety limit is reached.
- A critical unrecoverable error occurs.

The system must not automatically switch AI providers when allowance is exhausted.

A hunt that cannot reach its quota must terminate with an accurate partial-result summary rather than recycle leads or continue indefinitely.

## 8. AI Provider Integration

Mi Boti must use a modular adapter architecture for locally installed AI command-line tools.

Candidate providers include:

- Codex CLI.
- Claude Code CLI.
- Antigravity CLI.
- OpenCode CLI.

Provider support is conditional on technical compatibility and successful verification.

Each adapter must define a consistent interface for:

- Detecting local installation.
- Determining authentication state.
- Retrieving available subscription allowance.
- Validating execution eligibility.
- Executing a permitted AI task.
- Handling failures and timeouts.
- Reporting usage information.
- Identifying unsupported functionality.

Do not assume that a CLI exposes reliable, machine-readable subscription usage information.

Authentication success must not be treated as proof of available allowance.

If remaining subscription allowance cannot be reliably verified, that provider must be unavailable for autonomous execution.

**Never silently fall back to paid, metered AI APIs.**

Do not bypass provider restrictions, automate prohibited authentication flows, or invent usage percentages.

Subscription allowance verification must be tested before autonomous AI execution is enabled.

## 9. Free Business Discovery

The initial implementation must use free, permitted business-discovery sources.

Primary sources include:

- OpenStreetMap.
- Overpass API, subject to public-instance usage policies.
- Official business websites.
- Public directories that permit the intended automated access.

Do not introduce paid business-discovery APIs.

Implement:

- Request rate limiting.
- Request timeouts.
- Bounded retries.
- Source-specific access rules.
- Attribution handling.
- Source provenance.
- Query-history tracking.
- Duplicate filtering.

Do not use public Nominatim for systematic business-list harvesting.

Respect applicable website access restrictions and data-use requirements.

## 10. Persistent Business Registry

Every discovered business must be checked against the persistent global registry.

The registry must include businesses that are:

- Qualified.
- Unqualified.
- Rejected.
- Pending investigation.
- Already contacted.
- Archived.

Do not limit duplicate detection to qualified leads.

Use multiple identification signals, including:

- Source identifiers.
- Normalized website domains.
- Business names.
- Physical addresses.
- Public contact details.
- Similarity matching.

Do not automatically merge ambiguous businesses.

Track parent companies and branches separately where appropriate.

Persist research history and previous discovery decisions.

Previously discovered businesses may be refreshed through an explicit operation, but refreshed records must not count as newly discovered leads.

## 11. Research Integrity

Research findings must be supported by identifiable public evidence.

Every meaningful business finding should preserve:

- Source URL or source identifier.
- Date and time of observation.
- Extracted factual information.
- Research confidence.
- Relevant limitations.

The AI must distinguish between:

1. Verified facts.
2. Evidence-supported inferences.
3. Unverified possibilities.

Do not claim that a business lacks software, booking systems, inventory systems, or other internal tools merely because those tools are not publicly visible.

Do not invent contact information, operational problems, business ownership, financial information, or software requirements.

## 12. Lead Scoring

Lead scoring must follow documented, explainable criteria.

Scoring should consider:

- Business relevance.
- Potential software-service fit.
- Publicly observable operational complexity.
- Evidence quality.
- Contactability.
- Opportunity confidence.

Every score must be accompanied by a rationale.

Missing information must not automatically be interpreted as a business weakness.

Scoring thresholds and weights must be configurable according to the documented scoring specification.

## 13. CRM and Outreach

Mi Boti must maintain persistent lead records and pipeline stages.

The system must support lead review, status updates, research history, notes, and follow-up tracking.

Outreach drafts may be generated using verified business research.

However:

**Mi Boti must never automatically send unsolicited outreach.**

External emails, messages, and other communications require explicit human review and manual sending.

Do not implement autonomous email campaigns or direct-message sending in the initial release.

## 14. SQLite and Storage Requirements

SQLite is the authoritative application database.

Use migrations for schema changes.

Enforce appropriate:

- Foreign keys.
- Unique constraints.
- Indexes.
- Transactions.
- Referential integrity.
- Data validation.

Store structured application records in SQLite.

Use the local filesystem for suitable logs, exports, backups, and research artifacts.

Avoid storing credentials or authentication secrets in ordinary application records.

Protect against concurrent writes and duplicate job execution.

## 15. Security Requirements

The application must enforce:

- Owner and administrator authorization.
- Guild authorization.
- Command-level permission checks.
- Channel restrictions.
- Secure credential handling.
- Safe subprocess execution.
- URL validation and SSRF protections.
- Request and execution timeouts.
- Bounded background jobs.
- Audit logging.
- Sensitive-data redaction.

Never execute arbitrary shell commands generated by research content or AI responses.

Treat web pages, directory descriptions, and AI-generated output as untrusted data.

Never expose authentication tokens, local credentials, or private configuration values in Discord messages or logs.

## 16. Background Jobs

Long-running operations must use a controlled background-job system.

The job system must support:

- Persistent job records.
- Explicit job states.
- Bounded concurrency.
- Cancellation.
- Retry limits.
- Progress tracking.
- Failure reporting.
- Safe recovery after interruption.

Application restart must not automatically resume autonomous hunting without an authorized user action.

The system must prevent overlapping hunting sessions from incorrectly counting the same business as a new lead.

## 17. Error Handling

Every external dependency must have defined failure behavior.

Handle at least:

- Discord permission failures.
- Discord API rate limits.
- Database errors.
- Missing AI CLI installations.
- Expired AI authentication.
- Unverifiable AI allowance.
- AI execution failures.
- Discovery-source outages.
- Website request failures.
- Invalid or incomplete business information.
- Duplicate records.
- Interrupted hunting sessions.

Errors must be logged with sufficient context for diagnosis without exposing secrets.

User-facing messages must explain the failure and any required corrective action.

## 18. Testing Requirements

Implement automated tests for critical behavior.

Required test coverage includes:

- Command-channel authorization.
- Initial Discord setup.
- Idempotent channel provisioning.
- SQLite migrations.
- Business deduplication.
- Concurrent duplicate prevention.
- Hunting quota enforcement.
- Hunting pause, resume, and stop.
- AI provider eligibility checks.
- Provider exhaustion handling.
- No paid API fallback.
- Research evidence validation.
- CRM persistence.
- Outreach approval restrictions.
- Application restart recovery.

Mock external services where appropriate.

Integration tests must separately validate real Discord and AI CLI behavior.

A mocked provider response does not prove actual subscription-allowance compatibility.

## 19. Development Phases

Follow this implementation sequence:

### Phase 0 — Technical Feasibility

Verify AI CLI compatibility, subscription-allowance visibility, and free discovery-source suitability.

Do not enable autonomous AI execution until the selected provider passes verification.

### Phase 1 — Application Foundation

Establish the Python project, configuration system, logging, database migrations, and test infrastructure.

### Phase 2 — Discord Infrastructure

Implement bot initialization, authorization, setup, channel provisioning, command restrictions, and persistent controls.

### Phase 3 — Business Registry and Discovery

Implement free-source discovery, business normalization, persistent deduplication, and search-history tracking.

### Phase 4 — Research and AI Intelligence

Implement website research, evidence preservation, AI adapters, qualification, and explainable scoring.

### Phase 5 — Autonomous Hunting

Implement hunting orchestration, quotas, lifecycle controls, safety limits, and Discord progress reporting.

### Phase 6 — CRM and Outreach

Implement lead management, research review, pipeline tracking, outreach drafting, and follow-up workflows.

### Phase 7 — Reliability and Release Validation

Complete integration testing, security review, recovery testing, backup validation, and operational documentation.

## 20. Definition of Done

A feature is complete only when:

1. Its implementation matches the documented requirements.
2. Its authorization and failure paths are handled.
3. Its persistent state behaves correctly.
4. Appropriate automated tests pass.
5. Relevant integration behavior is verified.
6. No known critical security issue remains.
7. Documentation is updated where necessary.
8. Remaining limitations are explicitly reported.

Do not describe untested functionality as production-ready.

## 21. Coding Agent Reporting

After each development phase, provide a concise implementation report containing:

- Features implemented.
- Files created or modified.
- Verification performed.
- Test results.
- Unresolved issues.
- Required manual configuration.
- Recommended next development phase.

Do not claim tests passed unless they were actually executed.

Do not silently skip requirements because an external dependency is unavailable.

If a mandatory requirement cannot be implemented, stop the affected work, explain the blocker, and request an explicit decision before changing the requirement.

## 22. Final Instruction

Build Mi Boti as a reliable, locally hosted, Discord-native lead intelligence system.

Prioritize correctness, security, persistence, explainability, and predictable autonomous behavior over unnecessary complexity.

**Never sacrifice subscription safeguards, duplicate prevention, research integrity, or user authorization to make a feature appear functional.**

## 23. Authoritative Documentation Package

This file defines coding-agent responsibilities; [README.md](README.md) indexes the complete implementation specification. Read the [requirements](docs/01-PRODUCT-REQUIREMENTS.md), [architecture](docs/02-TECHNICAL-ARCHITECTURE.md), [database contract](docs/04-DATABASE-SCHEMA.md), [canonical command registry](docs/07-DISCORD-COMMANDS-AND-INTERACTIONS.md), [provider gate](docs/10-AI-PROVIDER-INTEGRATION.md), and [job lifecycle](docs/17-BACKGROUND-JOBS.md) before changing those components. Use [configuration guidelines](docs/23-IMPLEMENTATION-GUIDELINES.md) for exact settings and [traceability/acceptance](docs/22-ACCEPTANCE-CRITERIA.md) for verification.

Decision status is centralized in the [README decisions table](README.md#decisions). This package is self-contained; the authority order is sections 1–22 above, then docs/01 requirements, then the other numbered component contracts. Consult numbered contracts for the affected components rather than reading all documents before every task. The owner has authorized Phase 0 assessment, Phase 1 foundation and Phase 2 Discord infrastructure implementation; later components remain subject to their phase gates. No candidate CLI is supported merely because it appears in the documentation.

The deployment baseline is one configured guild and one active/paused/interrupted hunt per database. Global duplicate memory covers all campaigns and sessions. Only a business first registered by that hunt, automatically qualified with valid evidence while RUNNING, may receive one globally unique quota credit. Existing records, refreshes, ambiguous identity resolutions and manual qualification never count. Persist all dispositions and query/research decisions. Never use Discord output counts as quota truth.

Follow the exact state transitions and checkpoint rules in the job specification. Startup marks unfinished autonomous work INTERRUPTED; no discovery/research/qualification/draft job resumes automatically. Explicit resume repeats current authorization, resource, allowance, active-time, absolute-age and budget checks. Safe non-AI publication/reminder recovery is separately constrained. Persistent components enforce the same command-channel policy as slash commands; dashboard controls navigate to assigned channels rather than bypassing restrictions.

Phase acceptance requires the test IDs and live evidence in [testing strategy](docs/20-TESTING-STRATEGY.md) and the [roadmap](docs/21-DEVELOPMENT-ROADMAP.md). Report created/modified files, checks actually executed, pass/fail/skip results, unresolved blockers, manual configuration and next phase. A mocked allowance response cannot satisfy real provider compatibility; if no provider passes, affected AI execution remains blocked. The owner-authorized fallback release covers phases 1–3, Phase 4a and the non-AI portion of phase 6 (setup, discovery, registry, safe website research/evidence, CRM and manual drafts), with all AI features visibly disabled. Autonomous hunting remains unreleased until a provider passes L02. Phase 4 remains the owner brief's research/intelligence phase: its 4a collection part is provider-free and belongs to the MVP, while its 4b AI analysis/scoring part remains gated by L02. The default `/research` collects and stores evidence without AI; only explicit analyze:true requests use the provider gate. This sequencing decision preserves the mandatory safeguards above.

Acceptance of documentation requires all 26 files, resolving relative links, coherent command/channel mappings, schema references, state machines, configuration and scoring arithmetic, and a requirement-to-test matrix. Acceptance of application features additionally requires implemented behavior and executed automated/real integration verification; documentation review alone never establishes production readiness.
