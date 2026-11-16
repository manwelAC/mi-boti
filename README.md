<p align="center">
  <img src="assets/mi-boti-banner.png" alt="Mi Boti — plain white lettering beside a wide-eyed tabby at a laptop" width="100%" />
</p>

<p align="center">
  Personal business research and prospect tracking, inside Discord.
</p>

<p align="center">
  <a href="CHANGELOG.md"><img alt="Version 0.2.0" src="https://img.shields.io/badge/version-0.2.0-88E2CF?style=flat-square&amp;labelColor=17252D" /></a>
  <img alt="Interface Discord" src="https://img.shields.io/badge/interface-Discord-9AA5FF?style=flat-square&amp;labelColor=17252D" />
  <img alt="Storage local SQLite" src="https://img.shields.io/badge/storage-local_SQLite-D7DDE5?style=flat-square&amp;labelColor=17252D" />
  <img alt="Status in development" src="https://img.shields.io/badge/status-in_development-F0C987?style=flat-square&amp;labelColor=17252D" />
</p>

<p align="center">
  <a href="#the-workspace">The workspace</a> &nbsp;·&nbsp;
  <a href="#current-status">Current status</a> &nbsp;·&nbsp;
  <a href="#documentation-index">Project notes</a> &nbsp;·&nbsp;
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

## The workspace

Mi Boti brings business discovery, source-backed research and prospect management into one personal Discord workspace. It is being built to find relevant businesses in the Philippines, understand what is publicly observable, and keep the context behind every prospect.

The goal is a durable working memory for custom software prospecting: who was discovered, what the evidence says, and what deserves a closer look. Records stay local. Outreach stays a human decision.

| Discover & remember | Research & understand | Review & connect |
| :--- | :--- | :--- |
| Find businesses through permitted public sources and keep a global registry across campaigns. | Preserve public evidence, its source and its limits before drawing conclusions. | Manage prospects, notes, follow-ups and drafts, with human review and manual sending. |

*These describe the target workflow. The discovery core is in progress; live discovery, research and CRM remain unavailable.*

## Current status

**v0.2.0 · Discord infrastructure milestone**

The foundation and Discord integration are implemented, including a private operator guide channel and `/guide` help. Live checks have confirmed setup, repeat setup, channel restrictions, command responses and the hunt-control button after restart. Full live acceptance is still in progress.

| Layer | Progress |
| :--- | :--- |
| Foundation | Implemented: configuration, private storage, logging, migrations and backup primitives |
| Discord workspace | Implemented: private channels, authorization, confirmed provisioning and persistent panels |
| Verification | **591 automated tests passed** on Windows / CPython 3.14.6; 361 upstream SDK warnings remain |
| Discovery & registry | Implemented & L03 verified: regional Geofabrik Philippines OSM extract importer (`pyosmium==4.3.2`) with subprocess-isolated parsing and immutable generation pointers, local SQLite snapshot adapter (`PhilippinesExtractAdapter`), transactional registry, versioned non-AI campaigns, deferred cross-database cursor acknowledgement, bounded worker & review resolution; manual local-source discovery can be explicitly enabled after snapshot preparation; public Overpass remains blocked |
| Research & CRM | Non-AI `/research` supports confirmed site-access reviews, bounded collection and saved evidence; live Discord/business-site acceptance pending. CRM remains unavailable |
| Identity review | Private `/lead` queue and registry inspection, with confirmed link/separate decisions; live Discord rendering pending |
| AI & autonomous hunting | Disabled until a provider passes real compatibility and allowance verification |

[Release notes](CHANGELOG.md#020--2026-11-14) · [Verification record](docs/22-ACCEPTANCE-CRITERIA.md#version-020-release-checkpoint--2026-11-14) · [Development roadmap](docs/21-DEVELOPMENT-ROADMAP.md)

## Built with intention

**Discord is the interface. SQLite is the memory. Public evidence is the starting point.**

| Foundation | Role |
| :--- | :--- |
| Python + discord.py | Commands, private responses and persistent controls |
| SQLite + local filesystem | Durable records, evidence artifacts and operational history |
| HTTPX + BeautifulSoup | Planned bounded public-site collection and extraction |
| OpenStreetMap / Overpass | Planned discovery through reviewed, permitted sources |
| Local AI CLIs | Conditional future analysis; installation and authentication alone never establish eligibility |

## Operating safeguards

- **Evidence before inference.** Findings must preserve their sources, observation times, confidence and limitations. Missing public information is never proof of an internal problem.
- **One business, lasting context.** The registry must remember every disposition, including rejected and archived records. Refreshes and duplicates never earn new-lead quota credit.
- **Explicit control.** Commands are restricted by guild, user and channel ID. Hunting never starts or resumes automatically.
- **Verified allowance.** AI execution fails closed when subscription capacity cannot be verified. Providers never switch automatically, and paid metered APIs are never a fallback.
- **Human outreach.** Drafts require review. External messages are always sent manually.

The first MVP follows **Discord workspace → discovery & registry → non-AI research → CRM & manual drafts**. If no provider passes L02, the approved release remains phases **1–3, 4a and non-AI phase 6**, with AI and hunting visibly disabled.

## Documentation index

The numbered specifications describe the full target product; they do not imply that every component is implemented. The Markdown documents are the current source of truth.

| Reference | Purpose |
| :--- | :--- |
| [Development handoff](DEVELOPMENT-HANDOFF.md) | Implementation snapshot and onboarding for development tools |
| [Overview](docs/00-PROJECT-OVERVIEW.md) | Product scope and vocabulary |
| [Roadmap](docs/21-DEVELOPMENT-ROADMAP.md) | Milestones, dependencies and release gates |
| [Acceptance ledger](docs/22-ACCEPTANCE-CRITERIA.md) | Executed checks, live evidence and limitations |
| [Local operations](docs/LOCAL-OPERATIONS.md) | Private deployment workflow and maintenance reference |
| [Changelog](CHANGELOG.md) | Version history and integration notes |

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

## Authority

`AGENTS.md` is a local development instruction file and is intentionally excluded from this repository. Its mandatory owner brief remains the highest authority during development.

The authority order is:

1. **`AGENTS.md`** — the owner brief and mandatory constraints.
2. **[Doc 01: product requirements](docs/01-PRODUCT-REQUIREMENTS.md)** — the normative requirement inventory.
3. **Other numbered documents** — reference contracts consulted for the component being changed.

Read the agent instructions and relevant component contracts before implementation; reading every numbered document before every task is unnecessary. Resolve contradictions using this order, follow the roadmap and verify each applicable phase gate. The current implementation covers the foundation and Phase 2 Discord infrastructure, with the real-server gate partially verified. Production source policies, deployment IDs/permissions, and any enabled provider still require the documented configuration and verification.

## Decisions

The decision log is the central record of mandatory choices, technical recommendations, and unresolved inputs.

| Status | Meaning |
| :--- | :--- |
| **FINAL** | An owner decision or mandatory constraint |
| **PROPOSED** | A consistent technical baseline awaiting owner revision or approval; not a verified third-party capability |
| **OPEN** | Deployment-owner input or feasibility evidence is still required before enabling the affected feature |

The remaining OPEN inputs are **D11: verified AI provider**, **D12: website research policies (Phase 4a)** — while the Philippines OSM regional extract discovery source direction is owner-approved (`FINAL` per [docs/PHILIPPINES-EXTRACT-PLAN.md](docs/PHILIPPINES-EXTRACT-PLAN.md)) and verified under `L03` — and **D13: Discord deployment identity and credentials**. D00 covers unspecified implementation details rather than repeating disclaimers in every document.

<details>
<summary><strong>Read the complete decision log · D00–D15</strong></summary>

| ID | Decision | Status | Owner | Doc reference |
|---|---|---|---|---|
| D00 | Detailed schemas, interfaces, arguments, roles, retention, numerical defaults and module boundaries form the technical baseline unless a more specific row applies | PROPOSED | Project owner; technical recommendation | [Architecture](docs/02-TECHNICAL-ARCHITECTURE.md), [configuration](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D01 | Discord-native/local stack; free permitted discovery; fail-closed subscription checks; no automatic provider switch, metered fallback or external sending | FINAL | Project owner | `AGENTS.md`, [requirements](docs/01-PRODUCT-REQUIREMENTS.md) |
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
| D12 | Regional Philippines OSM extract (`philippines-latest.osm.pbf` from Geofabrik) is owner-approved (`FINAL`) and `L03`-verified as the Phase 3 discovery source ([plan](docs/PHILIPPINES-EXTRACT-PLAN.md)); website research policies and Overpass/directory sources remain `OPEN` | FINAL (PH extract) / OPEN (other sources) | Project owner / Deployment owner | [Extract plan](docs/PHILIPPINES-EXTRACT-PLAN.md), [Discovery](docs/08-BUSINESS-DISCOVERY.md), [source settings](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D13 | Supply allowed guild/owner IDs, operator roles, private channel policy and bot credentials locally | OPEN | Deployment owner | [Setup](docs/06-DISCORD-SERVER-ARCHITECTURE.md), [configuration](docs/23-IMPLEMENTATION-GUIDELINES.md) |
| D14 | Marker-based publication reconciliation/UNCERTAIN delivery, future MCP interface, and expanded backup manifests follow the working MVP; basic safety remains mandatory | FINAL | Project owner | [Post-MVP work](docs/21-DEVELOPMENT-ROADMAP.md) |
| D15 | The initial target market is the Philippines (country code PH); any sample city/category used for feasibility is a test fixture, not a campaign decision | FINAL | Project owner | [Discovery scope and probe](docs/08-BUSINESS-DISCOVERY.md) |

</details>

## Versioning and changes

Versions follow `MAJOR.MINOR.PATCH`, with annotated `v` tags. Before 1.0, minor versions mark development milestones and may change contracts; patch versions contain compatible fixes. Commits use Conventional Commits with a component scope when useful. Version 0.2.0 is the Discord infrastructure milestone, not a full MVP or production-readiness claim.
