# 03 — Project structure

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

This layout implements [02](02-TECHNICAL-ARCHITECTURE.md). Phase 1 configuration/defaults, domain errors/values, database, migrations, runtime, logging and storage files now exist. The other component directories below remain the future layout. [23](23-IMPLEMENTATION-GUIDELINES.md) defines configuration and startup.

```text
mi-boti/
  README.md, AGENTS.md, docs/
  pyproject.toml                 # dependencies and test tooling
  config.example.toml            # nonsecret defaults
  src/mi_boti/
    __main__.py                  # composition root
    config.py, defaults.py       # typed validation and documented defaults
    runtime.py, logging.py       # offline initialization and redacted logs
    domain/                      # types, enums, scoring, transitions
    discord_app/
      bot.py, checks.py          # lifecycle, ActorContext and policy
      commands/                  # setup, campaign, hunt, discovery, research, CRM
      views/                     # persistent controls, modals, pagination
      rendering.py               # safe embeds and attachments
    services/                    # setup, registry, hunt, research, CRM, outreach
    repositories/                # SQLite queries and transaction boundaries
    migrations/                  # numbered immutable SQL
    jobs/                        # scheduler, leases, handlers, cancellation
    discovery/                   # source interface, Overpass, planner
    research/                    # policies, safe fetch, parsing, evidence
    providers/                   # contracts, gate, registry, individual adapters
    mcp/                         # disabled optional boundary
    storage/                     # artifacts, exports, backup validation
    security/                    # subprocess, paths, redaction
  tests/
    unit/                        # pure rules and validation
    integration/                 # real SQLite, fake external transports
    live/                        # opt-in Discord, provider and source probes
    fixtures/                    # synthetic evidence and CLI outputs
  data/                          # ignored runtime root
```

## Dependencies and contracts

Domain imports no Discord, HTTPX, subprocess or SQLite. Services use typed ports for repositories, clock, filesystem, source, provider and transport. Repositories use domain types and SQLite; adapters translate external formats. Discord modules call services, never SQL or allowance parsers. Composition root binds implementations and limits once.

Domain types include `BusinessObservation`, `IdentityDecision`, `Evidence`, `Finding`, `AllowanceSnapshot`, `TaskRequest`, `TaskResult`, `CampaignSnapshot`, `HuntState`, `JobState`, and `ScoreResult`, defined in [04](04-DATABASE-SCHEMA.md), [10](10-AI-PROVIDER-INTEGRATION.md) and [12](12-AI-LEAD-INTELLIGENCE.md). Transport objects never enter durable payloads.

Each CLI has an independent adapter/verification record. Shared process helpers do not imply shared allowance formats. Optional Playwright/MCP load only when enabled and verified. No external outreach sender module is permitted.

Fixtures contain no real secrets or contacts. Sanitized live transcripts stay outside source control with version/date manifests. Applied SQL migrations are immutable and checksummed.

## Failure behavior and acceptance

Startup rejects unsupported Python, missing required dependencies, conflicting guild binding, unwritable data root, and newer schema before workers run. Imports perform no network, job, or database side effects. Missing optional dependencies disable only their feature with guidance.

Acceptance: import smoke tests start no work; services instantiate without Discord credentials; dependency tests prevent domain-to-transport imports; path tests confine runtime files under data root. See T14/T16 in [20](20-TESTING-STRATEGY.md).
