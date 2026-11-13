# Mi Boti

**Discord-native lead intelligence. Locally hosted. Built for the Philippines.**

Discover businesses, preserve public evidence, and manage prospects for custom software development—all through Discord. Mi Boti uses SQLite and local storage, with human review and manual sending for every external outreach message.

[Project status](#current-status) · [Quick start](#quick-start) · [Documentation](#documentation-index) · [Decisions](#decisions)

---

## Current status

> [!IMPORTANT]
> **Phase 1 foundation is implemented and locally verified.** The full Discord application is still in development. AI execution and autonomous hunting are disabled.

| Component | Status | Details |
| :--- | :--- | :--- |
| Application foundation | **Implemented** | Configuration, redacted logs, private storage, deployment locking, 41 SQLite tables, checksummed migrations, artifacts, and verified backup/restore primitives |
| Automated verification | **66 tests passed** | Last verified on Windows / CPython 3.14.6; other supported Python versions and operating systems remain untested |
| Discord infrastructure | **Next: Phase 2** | Bot initialization, authorization, confirmed setup, channel restrictions, and persistent controls |
| Discovery, research, and CRM | **Not implemented** | Planned through the non-AI MVP; the latest Philippines discovery connectivity probe failed |
| AI providers and hunting | **Blocked** | No provider has passed the full compatibility and subscription-allowance gate |

The owner authorized Phase 0 assessment and Phase 1 development on **2026-11-14**. See the [implementation report and executed checks](docs/22-ACCEPTANCE-CRITERIA.md#phase-0-assessment-and-phase-1-implementation--2026-11-14) for the file inventory, results, limitations, and remaining work. Local tests do not establish production readiness or live integration compatibility.

## What Mi Boti is being built to do

- **Discover:** find businesses through free, permitted sources, initially targeting the Philippines.
- **Remember:** keep a global registry across campaigns, including rejected, unqualified, pending, and archived businesses.
- **Research:** collect source-linked public evidence without requiring AI, separating observations from inferences and unknowns.
- **Manage:** review leads, track pipeline stages and follow-ups, and prepare human-reviewed outreach drafts.
- **Hunt:** run manually initiated, bounded sessions only after a provider passes real compatibility and allowance verification.

The first MVP prioritizes **setup → discovery → registry → non-AI website research → CRM → manual drafts**. If no provider passes L02, the approved release remains phases **1–3, 4a, and non-AI phase 6**. All AI features stay visibly disabled, and autonomous hunting remains unreleased. See the [development roadmap](docs/21-DEVELOPMENT-ROADMAP.md).

### Technology

| Layer | Choice |
| :--- | :--- |
| Runtime and Discord | Python · discord.py |
| Structured data and artifacts | SQLite · local filesystem |
| Public website research | HTTPX · BeautifulSoup; Playwright is optional and currently disabled |
| Business discovery | OpenStreetMap / Overpass and other explicitly permitted sources; no discovery adapter is enabled yet |
| AI execution | Local, subscription-authenticated CLI adapters, conditional on verification |
| Interface and hosting | Native Discord interactions · local or dedicated self-hosted machine |

There is no separate website or administrative frontend, paid discovery dependency, automatic provider switching, metered AI fallback, or autonomous external outreach.

## Quick start

These commands are for **local foundation development**, not launching a working Discord bot. Run them from the repository folder using the verified Windows / CPython 3.14 environment.

### 1. Create the environment

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Package metadata permits Python **3.11–3.14**; only **3.14.6 on Windows** has been verified. Direct pins are discord.py 2.7.1, HTTPX 0.28.1, BeautifulSoup 4.15.0, and pytest 9.2.0 for development.

<details>
<summary><strong>Use the exact verified Windows / Python 3.14 dependency set</strong></summary>

Install the resolved dependencies before installing the editable project:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-py314-windows.txt
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The lock file is specific to the verified environment. Other Python versions and operating systems require their own verification.

</details>

### 2. Check configuration without credentials

```powershell
$env:MI_BOTI_CONFIG_FILE = (Resolve-Path config.example.toml).Path
.venv\Scripts\python.exe -m mi_boti check-config
```

This reports configuration status without creating runtime data, connecting Discord, starting workers, or running AI. Copy `config.example.toml` to ignored `config.toml` when preparing local settings; the complete configuration contract is in [doc 23](docs/23-IMPLEMENTATION-GUIDELINES.md).

### 3. Run the tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests use synthetic guild/owner IDs and fresh confined directories under ignored `.pytest_cache`. They do not contact Discord, public websites, or an AI account.

<details>
<summary><strong>Initialize a real local database</strong></summary>

Before initialization, supply the intended `MI_BOTI_GUILD_ID` and `MI_BOTI_OWNER_IDS` locally. Then run:

```powershell
.venv\Scripts\python.exe -m mi_boti init-db
```

Initialization validates identity, holds the deployment lock, applies migrations, and binds the database to the configured guild. It does not connect Discord or execute jobs. Repeating initialization is safe; changing the guild binding is rejected. Use a dedicated data directory because startup refuses unrelated contents and applies private permissions.

The future Discord connection additionally requires `MI_BOTI_DISCORD_TOKEN`. Keep the token in the local environment—never in TOML, documentation, source control, or chat.

</details>

## Operating safeguards

Administrator setup uses `/setup` with a preview and explicit confirmation. Operational commands validate the guild, user, permission, configuration, and persisted channel ID before creating work. Channel names are not authorization identifiers.

A future `/hunt start quota:25` counts only **new, unique, qualified businesses** registered by that hunt. Existing businesses, explicit refreshes, ambiguous identity resolutions, and duplicates never count. Hunting never starts or resumes automatically on startup or reconnect.

A hunt stops at quota, operator stop, source exhaustion, safety limits, critical failure, or exhausted/unverifiable subscription allowance. Authentication alone does not establish allowance. The application must never switch providers automatically or fall back to a paid metered API. External outreach always requires human review and manual sending.

## Documentation index

Start with [AGENTS.md](AGENTS.md), [product requirements](docs/01-PRODUCT-REQUIREMENTS.md), and the component contract relevant to your task. The package is self-contained; access to earlier conversations is unnecessary.

<details>
<summary><strong>Browse all 24 implementation specifications</strong></summary>

| Specification | Responsibility |
|---|---|
| [00 Overview](docs/00-PROJECT-OVERVIEW.md) | Scope, vocabulary, authority |
| [01 Requirements](docs/01-PRODUCT-REQUIREMENTS.md) | Requirement IDs and workflows |
| [02 Architecture](docs/02-TECHNICAL-ARCHITECTURE.md) | Boundaries, service contracts, transactions |
| [03 Structure](docs/03-PROJECT-STRUCTURE.md) | Future modules and dependencies |
| [04 Database](docs/04-DATABASE-SCHEMA.md) | Tables, integrity, atomic operations |
| [05 Storage](docs/05-LOCAL-STORAGE.md) | Artifacts, exports, logs, backups |
| [06 Discord server](docs/06-DISCORD-SERVER-ARCHITECTURE.md) | Provisioning and permissions |
| [07 Commands](docs/07-DISCORD-COMMANDS-AND-INTERACTIONS.md) | Canonical command/channel contract |
| [08 Discovery](docs/08-BUSINESS-DISCOVERY.md) | Sources, identity, coverage history |
| [09 Research](docs/09-WEB-RESEARCH-ENGINE.md) | Safe fetching and evidence |
| [10 Providers](docs/10-AI-PROVIDER-INTEGRATION.md) | CLI contract and allowance gate |
| [11 MCP](docs/11-MCP-INTEGRATION.md) | Optional disabled integration boundary |
| [12 Intelligence](docs/12-AI-LEAD-INTELLIGENCE.md) | Findings and qualification |
| [13 Scoring](docs/13-LEAD-SCORING.md) | Versioned explainable rubric |
| [14 CRM](docs/14-CRM-AND-PIPELINE.md) | Stages, notes, history |
| [15 Outreach](docs/15-OUTREACH-MANAGEMENT.md) | Review and manual-send recording |
| [16 Discord UX](docs/16-DISCORD-UI-UX.md) | Panels and persistent controls |
| [17 Jobs](docs/17-BACKGROUND-JOBS.md) | Lifecycle, budgets, recovery |
| [18 Security](docs/18-SECURITY-AND-PRIVACY.md) | Authorization and threat boundaries |
| [19 Errors](docs/19-ERROR-HANDLING.md) | Failure taxonomy and recovery |
| [20 Testing](docs/20-TESTING-STRATEGY.md) | Automated and real verification |
| [21 Roadmap](docs/21-DEVELOPMENT-ROADMAP.md) | Ordered phases and gates |
| [22 Acceptance](docs/22-ACCEPTANCE-CRITERIA.md) | Traceability and release gates |
| [23 Guidelines](docs/23-IMPLEMENTATION-GUIDELINES.md) | Configuration and startup |

</details>

The numbered documents cover the full target product, including future components. Their presence does not mean those features have been implemented. The existing `docs.zip` is a historical artifact and has not been regenerated; use the Markdown files in `docs/` as the current specifications.

## Authority

The authority order is:

1. **[AGENTS.md sections 1–22](AGENTS.md)** — the owner brief and mandatory constraints.
2. **[Doc 01: product requirements](docs/01-PRODUCT-REQUIREMENTS.md)** — the normative requirement inventory.
3. **Other numbered documents** — reference contracts consulted for the component being changed.

Read the agent instructions and relevant component contracts before implementation; reading every numbered document before every task is unnecessary. Resolve contradictions using this order, follow the roadmap and verify each applicable phase gate. The current implementation scope is the Phase 1 foundation. Production source policies, deployment IDs/permissions, and any enabled provider still require the documented configuration and verification.

## Decisions

The decision log is the central record of mandatory choices, technical recommendations, and unresolved inputs.

| Status | Meaning |
| :--- | :--- |
| **FINAL** | An owner decision or mandatory constraint |
| **PROPOSED** | A consistent technical baseline awaiting owner revision or approval; not a verified third-party capability |
| **OPEN** | Deployment-owner input or feasibility evidence is still required before enabling the affected feature |

The remaining OPEN inputs are **D11: verified AI provider**, **D12: approved discovery sources**, and **D13: Discord deployment identity and credentials**. D00 covers unspecified implementation details rather than repeating disclaimers in every document.

<details>
<summary><strong>Read the complete decision log · D00–D15</strong></summary>

| ID | Decision | Status | Owner | Doc reference |
|---|---|---|---|---|
| D00 | Detailed schemas, interfaces, arguments, roles, retention, numerical defaults and module boundaries form the technical baseline unless a more specific row applies | PROPOSED | Project owner; technical recommendation | [Architecture](docs/02-TECHNICAL-ARCHITECTURE.md), [configuration](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D01 | Discord-native/local stack; free permitted discovery; fail-closed subscription checks; no automatic provider switch, metered fallback or external sending | FINAL | Project owner | [AGENTS sections 1–22](AGENTS.md), [requirements](docs/01-PRODUCT-REQUIREMENTS.md) |
| D02 | One guild and one active/paused/interrupted hunt per database | PROPOSED | Project owner; technical recommendation | [Overview](docs/00-PROJECT-OVERVIEW.md), [schema](docs/04-DATABASE-SCHEMA.md) |
| D03 | Base active budget is 3,600 seconds, counting only RUNNING/PAUSING/STOPPING; absolute age ceiling is 604,800 seconds (seven days) | FINAL | Project owner | [Hunt clocks](docs/17-BACKGROUND-JOBS.md), [keys](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D04 | Effective active and request/candidate/AI budgets scale with quota under hard caps; quota 25 receives 18,000 active seconds, 500 candidates and 500 AI tasks | PROPOSED | Project owner; validate in Phase 5 | [Budget formulas and throughput](docs/17-BACKGROUND-JOBS.md) |
| D05 | Scoring v1 weights 20/25/15/20/10/10, threshold 70, coverage 0.80 and documented evidence gates | PROPOSED | Project owner; technical recommendation | [Scoring](docs/13-LEAD-SCORING.md) |
| D06 | A named operator may approve their own draft; editing invalidates approval; sending remains manual | PROPOSED | Project owner; technical recommendation | [Outreach](docs/15-OUTREACH-MANAGEMENT.md) |
| D07 | Display timezone defaults to Asia/Singapore; persisted timestamps are UTC | PROPOSED | Deployment owner | [Configuration](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D08 | Provider verification expires after seven days and immediately on relevant tuple changes; allowance age <=30 seconds | PROPOSED | Project owner; technical recommendation | [Providers](docs/10-AI-PROVIDER-INTEGRATION.md) |
| D09 | MVP is setup, command restrictions, discovery, global registry/dedup, non-AI website research/evidence (4a), CRM and manual drafts | FINAL | Project owner | [MVP sequence](docs/21-DEVELOPMENT-ROADMAP.md) |
| D10 | If no provider passes L02, release phases 1–3, 4a and non-AI phase 6; all AI features visibly disabled; Phase 4b and hunting unreleased | FINAL | Project owner | [Phase 0 gate](docs/21-DEVELOPMENT-ROADMAP.md) |
| D11 | Select a subscription CLI/backend/model only after its real L02 gate passes; none currently verified | OPEN | Deployment owner with Phase 0 evidence | [Provider procedure](docs/10-AI-PROVIDER-INTEGRATION.md) |
| D12 | Select permitted discovery endpoints/directories and approve their current policies, daily budgets and attribution | OPEN | Deployment owner | [Discovery](docs/08-BUSINESS-DISCOVERY.md), [source settings](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D13 | Supply allowed guild/owner IDs, operator roles, private channel policy and bot credentials locally | OPEN | Deployment owner | [Setup](docs/06-DISCORD-SERVER-ARCHITECTURE.md), [configuration](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D14 | Marker-based publication reconciliation/UNCERTAIN delivery, future MCP interface, and expanded backup manifests follow the working MVP; basic safety remains mandatory | FINAL | Project owner | [Post-MVP work](docs/21-DEVELOPMENT-ROADMAP.md) |
| D15 | The initial target market is the Philippines (country code PH); any sample city/category used for feasibility is a test fixture, not a campaign decision | FINAL | Project owner | [Discovery scope and probe](docs/08-BUSINESS-DISCOVERY.md) |

</details>
