# Mi Boti

Mi Boti is a locally hosted, Discord-native lead intelligence and prospect management system for custom software development prospecting. It discovers businesses from free permitted public sources, preserves evidence, evaluates opportunities, and manages a persistent CRM. Humans review and manually send all external outreach.

**Status: Phase 1 foundation implemented and locally verified.** The owner authorized Phase 0 assessment and Phase 1 development on 2026-11-14. Configuration, redacted logging, checksummed migrations, private storage, deployment locking and verified-copy primitives are implemented; 66 automated tests pass on Windows/CPython 3.14.6. Discord workflows, discovery adapters, research, CRM and AI execution are not implemented. No provider is VERIFIED; hunting remains disabled.

## Authority

This package is self-contained. The authority order is **AGENTS.md sections 1–22 (owner brief) > docs/01 product requirements > the other numbered documents**. The numbered documents are reference contracts to consult for the component being changed; they are not mandatory reading before every task. Read AGENTS.md and the relevant component contracts before implementation, and resolve contradictions using this order. Current implementation scope is the Phase 1 foundation; later components remain subject to their phase gates.

## Local development

The verified environment is Windows with CPython 3.14.6. Package metadata allows Python 3.11–3.14, but other Python versions/operating systems have not yet been tested. Direct runtime dependencies are discord.py 2.7.1, HTTPX 0.28.1 and BeautifulSoup 4.15.0; pytest 9.2.0 is the development test dependency. The exact Windows/Python 3.14 dependency set is recorded in requirements-py314-windows.txt. No cloud, frontend or additional database was added.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

For reproducibility on the verified Windows/Python version, install requirements-py314-windows.txt before the editable package. Tests use fresh confined directories under ignored .pytest_cache and synthetic guild/owner IDs. They do not contact Discord, public websites or an AI account.

To check settings without credentials or creating runtime data:

```powershell
$env:MI_BOTI_CONFIG_FILE = (Resolve-Path config.example.toml).Path
.venv\Scripts\python.exe -m mi_boti check-config
```

Copy config.example.toml to ignored config.toml for local configuration. Keep the future bot token only in MI_BOTI_DISCORD_TOKEN, never TOML or this chat. Database initialization requires real MI_BOTI_GUILD_ID and MI_BOTI_OWNER_IDS; `.venv\Scripts\python.exe -m mi_boti init-db` validates them, holds the deployment lock, applies migrations and binds the database to the guild. It does not connect Discord, start workers or run a hunt. Repeating initialization is safe; a changed guild binding is rejected. Use a dedicated data directory because startup refuses unrelated contents and applies private permissions.

The [current phase report](docs/22-ACCEPTANCE-CRITERIA.md#phase-0-assessment-and-phase-1-implementation--2026-11-14) records verification, limitations and the next phase. The old docs.zip is historical and has not been regenerated.

## Decisions

FINAL records an owner decision or mandatory constraint. PROPOSED records a technical baseline awaiting owner revision or approval; it is not a verified third-party capability. OPEN requires deployment-owner input or a feasibility result before the affected feature can be enabled. Unspecified implementation detail is covered by D00 rather than repeated disclaimers in each document.

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

Required stack: Python, discord.py, SQLite, local filesystem, HTTPX, BeautifulSoup, optional Playwright, and verified local subscription-authenticated AI CLI adapters. No website, paid discovery dependency, automatic provider switching, metered AI fallback, or autonomous external outreach.

## Operating contract

An administrator runs `/setup`, reviews its preview, and confirms provisioning. Every operational command checks guild, user, permission, persistent channel ID, and configuration before enqueueing work. An operator manually starts `/hunt start quota:25`. Only newly registered, unique businesses qualified by that hunt count. Existing businesses, refreshes, ambiguous identities, and duplicates never count.

Hunts stop at quota, operator stop, exhausted/unverifiable allowance, safety limits, source exhaustion, or critical failure. Startup and reconnect never start or resume hunting. Authentication does not prove allowance. If no CLI passes real allowance verification, autonomous AI stays disabled; the non-AI release scope below remains available.

## Documentation index

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

Consult agent instructions and the numbered reference contracts relevant to each task. Follow the roadmap, including its owner-authorized non-AI MVP sequence, and verify each applicable gate. Future configuration uses environment variables for secrets and local TOML for nonsecret settings; SQLite owns mutable application state. The owner supplies token, guild and owner IDs, approved source policies, and, only for later AI features, a verified provider installation. See [configuration](docs/23-IMPLEMENTATION-GUIDELINES.md).

## Feasibility and acceptance

Codex CLI, Claude Code CLI, Antigravity CLI, and OpenCode CLI are candidates, not verified supported providers. Phase 0 must establish actual subscription allowance visibility, billing mode, safe noninteractive execution, and cancellation. Public-source policies and live Discord permissions also need deployment-specific validation.

If no provider passes L02, the release scope is phases 1–3, 4a and 6 (setup, discovery, registry, safe website research/evidence, CRM, manual drafts) with all AI features visibly disabled. Autonomous hunting remains unreleased until a provider passes. This owner-authorized fallback does not relax any subscription safeguard or claim that the full autonomous product is complete.

Documentation acceptance requires all 26 files, working internal links, and consistent commands, schema, states, quota rules, and provider safeguards. Documentation checks do not prove runtime readiness. Real integrations must be verified separately from mocks.
#   m i - b o t i  
 