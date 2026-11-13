# 22 — Acceptance criteria and traceability

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

This is the acceptance ledger for [requirements](01-PRODUCT-REQUIREMENTS.md), [roadmap](21-DEVELOPMENT-ROADMAP.md), and [testing](20-TESTING-STRATEGY.md). Passing documentation review does not imply application or integration tests passed. Technical decision status is recorded centrally; finalized constraints cannot be waived silently.

## Requirements traceability matrix

| Requirement | Architecture / implementation specifications | Tests | Phase | Observable acceptance |
|---|---|---|---|---|
| R01 Discord/local stack | [02](02-TECHNICAL-ARCHITECTURE.md), [03](03-PROJECT-STRUCTURE.md), [23](23-IMPLEMENTATION-GUIDELINES.md) | T03,T04,T14; L01 | P1–P2 | Local Python bot, SQLite truth, native UI; no separate frontend/cloud dependency |
| R02 Safe setup | [06](06-DISCORD-SERVER-ARCHITECTURE.md), [04](04-DATABASE-SCHEMA.md) | T02; L01 | P2 | Confirmed preview only; repeated setup no duplicates; unrelated resources preserved; deletion requires approval |
| R03 Command restrictions | [07](07-DISCORD-COMMANDS-AND-INTERACTIONS.md), [16](16-DISCORD-UI-UX.md), [18](18-SECURITY-AND-PRIVACY.md) | T01,T03; L01 | P2 | Every command/component checks guild/member/action/exact ID/config; denial creates no job |
| R04 Free source policy | [08](08-BUSINESS-DISCOVERY.md), [09](09-WEB-RESEARCH-ENGINE.md) | T05,T10; L03 | P0,P3,P4a | Policy-approved bounded requests, attribution/provenance/coverage, no paid dependencies |
| R05 Global identity | [08](08-BUSINESS-DISCOVERY.md), [04](04-DATABASE-SCHEMA.md), [14](14-CRM-AND-PIPELINE.md) | T06,T12 | P3 | Rejected/unqualified/archive matched; branches distinct; ambiguous hold; one strong identity owner |
| R06 Evidence integrity | [09](09-WEB-RESEARCH-ENGINE.md), [12](12-AI-LEAD-INTELLIGENCE.md) | T10,T11 | P4a/P4b | Source/time/confidence/limitations persisted; unsupported facts and absence claims rejected |
| R07 Explainable scoring | [13](13-LEAD-SCORING.md), [12](12-AI-LEAD-INTELLIGENCE.md) | T15,T11 | P4b | Versioned formula/coverage/rationale/gates agree; unknowns never scored as weakness |
| R08 Verified CLI allowance | [10](10-AI-PROVIDER-INTEGRATION.md) | T08; L02 | P0,P4b | Real mechanism proves subscription capacity and task eligibility; unavailable evidence blocks execution |
| R09 No fallback | [10](10-AI-PROVIDER-INTEGRATION.md), [11](11-MCP-INTEGRATION.md), [18](18-SECURITY-AND-PRIVACY.md) | T09,T14; L02 | P0,P4b–P5 | Zero automatic provider switch, metered route or inherited unreviewed tools |
| R10 Manual quota hunting | [17](17-BACKGROUND-JOBS.md), [07](07-DISCORD-COMMANDS-AND-INTERACTIONS.md) | T07,T13; L01,L04 | P5 | Explicit start/resume; lifecycle works; exact new-qualified count; honest partial terminal summaries |
| R11 Bounded/recoverable jobs | [17](17-BACKGROUND-JOBS.md), [19](19-ERROR-HANDLING.md) | T05,T13,T18; L04 | P5,P7 | Persistent budgets/leases/cancellation; restart/reconnect creates no hunt/AI work |
| R12 Atomic quota/dedupe | [04](04-DATABASE-SCHEMA.md), [02](02-TECHNICAL-ARCHITECTURE.md) | T06,T07,T13 | P3,P5 | Competing writes cannot duplicate business/credit; late/existing/refresh results cannot count |
| R13 Persistent CRM | [14](14-CRM-AND-PIPELINE.md), [16](16-DISCORD-UI-UX.md) | T12; L01 | P6 | Stages/notes/history/contacts/follow-ups persist; stale revisions rejected |
| R14 Human/manual outreach | [15](15-OUTREACH-MANAGEMENT.md), [14](14-CRM-AND-PIPELINE.md) | T17,T09 | P6 | Named approval, edit invalidation, manual attestation; no sending interface or transmissions |
| R15 Security and errors | [18](18-SECURITY-AND-PRIVACY.md), [19](19-ERROR-HANDLING.md), [09](09-WEB-RESEARCH-ENGINE.md) | T01,T10,T14,T18 | All | Safe network/subprocess/path boundaries, redacted diagnostics, actionable failures |
| R16 Storage/release verification | [04](04-DATABASE-SCHEMA.md), [05](05-LOCAL-STORAGE.md), [20](20-TESTING-STRATEGY.md) | T04,T16; L01–L04 | P1,P7 | Migration/backup/restore integrity, retained registry, separate real integration evidence |

## Phase acceptance ledger

| Gate | Required deliverable and verification | Blocks progression when missing |
|---|---|---|
| P0 | Provider compatibility matrix with real findings, including BLOCKED; approved-source policy probe; OS cancellation/URL transport assessment | AI enablement requires L02; the approved non-AI fallback proceeds through P1–P3, P4a and manual P6 |
| P1 | Typed config/redaction/data root/lock, migrations and storage harness; T04 and foundation T14/T16 | Dependent persistence work |
| P2 | Bot/checks/setup/IDs/panels; T01–T03 and L01 infrastructure | Claiming verified Discord infrastructure |
| P3 | Registry/identity/discovery/history; T05/T06 and L03 discovery | Research/hunt discovery dependency |
| P4a | Safe HTTP/DNS, permission/robots checks, bounded extraction, immutable evidence and provider-free `/research`; T10/non-AI T11, relevant T01/T03/T13/T14/T16, L01 research/L03 | MVP website research; L02 is not a prerequisite |
| P4b | Eligible adapters, structured AI findings, qualification/rubric; T08/T09/AI T11/T15, L02 for enabled providers and a passing P4a | AI analysis/scoring/drafting and autonomous hunting |
| P5 | Lifecycle/leases/dual clocks/quota-scaled limits/credits/progress; T07/T09/T13/T18, measured throughput and live lifecycle | Autonomous hunting release |
| P6 | Manual CRM/drafts/approval/follow-ups/exports; applicable T12/T17 and T14/L01, plus separate AI tests before generation | Manual scope follows P3/P4a; AI generation remains gated |
| P7 | Scope-specific suite, security review, basic verified-copy restore and operator guide for MVP; retained full suite/post-MVP reliability for autonomous release | Readiness claims are limited to the actually verified release scope |

Partial results or disabled unsupported providers must be listed in reports. A skipped live test is an unresolved verification gap. An implemented adapter with only mocked allowance data remains BLOCKED. No phase gate can be satisfied by a screenshot or success message without the stated persistence/failure assertions.

## MVP and fallback acceptance

The owner has authorized the non-AI MVP and fallback scope in README D09/D10. A BLOCKED L02 result prevents AI execution, not the setup/discovery/registry/non-AI-research/manual-CRM/manual-draft release. Gate evidence must name its scope. MVP acceptance includes exact command restrictions, all-disposition deduplication, safe provider-free website research with stored immutable evidence, manual qualification with a named actor and cited public evidence, null rather than fabricated AI scores, draft approval/manual sending, bounded jobs and verified-copy restore. It must show all AI features visibly disabled.

Marker-based publication reconciliation/UNCERTAIN delivery, the future MCP interface and expanded backup manifests are post-MVP. Manual inspection holds for uncertain sends, disabled-MCP isolation, and basic backup integrity/restore remain mandatory. The later full release must satisfy the retained contracts before claiming them complete.

## Documentation package acceptance

Exactly README, AGENTS, and 24 numbered docs exist with required filenames. Every document states purpose/relations, responsibility, concrete contracts/workflows, validation/failure edges and testable criteria. All internal relative links resolve, including anchors where present. The command registry is canonical; schema identifiers and enums match their consumers; provider gates match lifecycle; identity and credit rules agree; configuration keys/defaults have one source in [23](23-IMPLEMENTATION-GUIDELINES.md).

Documentation audit must enumerate file count, unresolved links, command/channel coverage, table names, lifecycle transitions, scoring arithmetic, configuration references, phase/test mapping and third-party blockers. This is a specification audit, not application test execution. Future drift requires updating the canonical spec and dependent cross-references together.

## Documentation audit record — 2026-11-13T21:55:26+08:00 (revision 3: research split)

The following is actual output from the transient Python documentation-audit script. It checks document/link/anchor resolution, command mappings, table FK targets, configuration references, documented state contracts, quota/scoring arithmetic, requirements and phase gates, Git ignore behavior, protected AGENTS sections, and the new Phase 4a/4b research boundary. The research assertions inspect the specification and its required tests; they do not claim those runtime tests have been implemented or passed.

```json
{
  "audit_timestamp_singapore": "2026-11-13T21:55:26+08:00",
  "markdown_files": 26,
  "relative_links_checked": 247,
  "parent_relative_links_checked": 27,
  "anchor_links_checked": 26,
  "broken_links": 0,
  "command_keys_matching_owner_channels": 21,
  "schema_tables": 41,
  "distinct_fk_targets": 17,
  "undefined_fk_targets": [],
  "config_keys_declared": 88,
  "config_keys_referenced": 88,
  "undefined_config_keys": [],
  "environment_variables_defined": 5,
  "db_column_references_classified": [
    "jobs.progress_json"
  ],
  "hunt_state_graph_matches": true,
  "clock_and_job_consistency_assertions_pass": true,
  "quota_25_effective_limits": {
    "active_seconds": 18000,
    "age_seconds": 604800,
    "discovery_requests": 50,
    "candidates": 500,
    "http_requests": 4000,
    "ai_tasks": 500
  },
  "scoring_example": {
    "full": 73.0,
    "unknown_contact": 74.44
  },
  "requirements_traced": 16,
  "phase_gates": [
    "P0",
    "P1",
    "P2",
    "P3",
    "P4a",
    "P4b",
    "P5",
    "P6",
    "P7"
  ],
  "agents_sections_1_22_byte_identical": true,
  "agents_protected_sha256": "3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259",
  "git_repository_initialized": true,
  "git_ignore_positive_cases": 9,
  "documentation_paths_not_ignored": 27,
  "changed_scope_files": [
    "AGENTS.md",
    "README.md",
    "docs/00-PROJECT-OVERVIEW.md",
    "docs/01-PRODUCT-REQUIREMENTS.md",
    "docs/02-TECHNICAL-ARCHITECTURE.md",
    "docs/05-LOCAL-STORAGE.md",
    "docs/07-DISCORD-COMMANDS-AND-INTERACTIONS.md",
    "docs/09-WEB-RESEARCH-ENGINE.md",
    "docs/14-CRM-AND-PIPELINE.md",
    "docs/16-DISCORD-UI-UX.md",
    "docs/17-BACKGROUND-JOBS.md",
    "docs/20-TESTING-STRATEGY.md",
    "docs/21-DEVELOPMENT-ROADMAP.md",
    "docs/22-ACCEPTANCE-CRITERIA.md",
    "docs/23-IMPLEMENTATION-GUIDELINES.md"
  ],
  "research_split_assertions": {
    "phase_4a_and_4b_gates": true,
    "mvp_sequence_includes_4a": true,
    "d09_includes_research": true,
    "d10_includes_4a": true,
    "research_default_is_non_ai": true,
    "ai_option_denied_before_enqueue_in_mvp": true,
    "mvp_tests_include_t10_non_ai_t11": true,
    "mvp_live_research_covered": true,
    "collected_evidence_survives_analysis_failure": true,
    "provider_spy_zero_calls": true,
    "no_collection_credit": true
  },
  "errors": []
}
```

The script classifies command keys and documented database columns separately from process configuration and verifies all static/template configuration references against doc 23. Parent-relative links and heading anchors are included in the totals. P4a and P4b are independently checked, so the ledger now contains nine gates under the original phases 0–7. The original clock, quota and scoring checks still pass. AGENTS.md sections 1–22 are byte-identical to the saved pre-revision brief; only appendix 23 changed.

`git status --short` was also executed directly. Its output was:

```text
?? .gitignore
?? AGENTS.md
?? README.md
?? docs.zip
?? docs/
```

This confirms an initialized repository with untracked files and no commit; it does not mean files are already tracked. The requested runtime/secret exclusions were inspected, nine synthetic ignored paths were checked without creating secret files, and all 27 documentation/ignore-rule paths were confirmed not ignored. The existing docs.zip was left untouched and is not the revised documentation deliverable.

At the time of this historical documentation-only audit, manual review aligned D09/D10, the fallback/MVP sequence, provider-free RESEARCH jobs, stored evidence for manual CRM/drafts, evidence preservation if optional analysis fails, and basic backup coverage for required website evidence. No application code, migrations, application tests or live integrations had yet been created or executed. Safe HTTP/SSRF behavior, robots/source policies and L01/L03 research must be verified during Phase 4a implementation. An L02 blocker alone does not disable collection; it continues to block Phase 4b, AI drafting and hunting.

OPEN owner inputs remain D11 (verified provider/backend/model), D12 (permitted discovery and website sources, policies, budgets and attribution), and D13 (guild/owner IDs, roles, private-channel policy and locally supplied credentials). No secret values belong in this document. The revised package is a specification for Phase 0 onward, not evidence that any implementation phase has passed.

## Definition of done for implementation

A feature matches requirements, handles authorization/failure paths, persists valid state, passes appropriate executed automated tests and relevant real integrations, has no known critical security defect, updates documentation and explicitly reports limitations/manual configuration. Full autonomous product completion additionally requires verified provider support, all later phase gates and retained post-MVP reliability verification. The owner-authorized non-AI release is a valid narrower scope when its applicable gates pass. Label that scope explicitly, and never claim autonomous readiness from documentation alone.

## Phase 0 assessment and Phase 1 implementation — 2026-11-14

This is the current implementation report. Earlier documentation-audit JSON above is a historical snapshot, not a claim that the repository still contains only documentation. The owner authorized continued Phase 0 assessment and Phase 1 foundation work. AGENTS.md sections 1–22 remain unchanged; its appendix records the updated implementation scope.

### Phase 0 assessment: recorded with blockers

The latest bounded AGY usage probe returned exit 0/SUCCESS, zero model turns and tokens, and five expected quota bucket identifiers with fractions/reset fields. No generative test was admitted because billing isolation, provenance/version, quota freshness/failure semantics, task reserves and safe execution remain unverified. L02 is BLOCKED, not passed. No provider/API fallback occurred. A separate single-attempt Philippines/Makati Overpass GET probe timed out after 18.46 seconds; L03 discovery connectivity remains FAILED. No records or qualified leads were obtained. Geofabrik Philippines regional OSM metadata was reviewed as a possible local source, without downloading the dataset, implementing an importer or selecting it for production. D11/D12 remain OPEN; the independent Phase 1 work proceeds under the approved non-AI scope, not a waiver of live gates.

### Phase 1 features and files

Implemented offline configuration checking, strict typed TOML/environment parsing, frozen settings, secret-safe summaries, quota-budget calculation, redacted rotating logs, private dedicated data roots, confinement and Windows junction rejection, OS-held deployment locking, a checksummed migration runner, singleton guild binding, transactional database access, atomic artifact storage/integrity/orphan cleanup, and consistent verified SQLite copy/restore primitives. No Discord client, background scheduler, discovery adapter, website fetcher, provider execution adapter, CRM workflow or external sender exists yet.

Files created:

- pyproject.toml, config.example.toml, requirements-py314-windows.txt.
- src/mi_boti/__init__.py, __main__.py, config.py, defaults.py, runtime.py, logging.py.
- src/mi_boti/domain/__init__.py, errors.py, values.py.
- src/mi_boti/repositories/__init__.py, database.py.
- src/mi_boti/migrations/0001_initial.sql and manifest.json.
- src/mi_boti/storage/__init__.py, paths.py, lock.py, backup.py, artifacts.py.
- tests/conftest.py; tests/unit/test_config.py and test_redaction.py; tests/integration/test_database.py, test_startup.py and test_storage.py.

Files modified for status, scope, operations or verification: .gitignore, README.md, AGENTS.md appendix 23, and docs 03, 04, 08, 10, 20, 21, 22 and 23. The virtual environment, test data, wheel-check installs and build outputs are ignored. Existing docs.zip remains untouched. No files were committed or published.

### Executed verification

Verified platform: Windows / CPython 3.14.6, SQLite supplied by that Python installation, pytest 9.2.0. Direct runtime dependency pins are discord.py 2.7.1, HTTPX 0.28.1 and BeautifulSoup 4.15.0. The 25 resolved development/runtime packages are pinned for Windows/Python 3.14 in requirements-py314-windows.txt. Other supported-by-metadata Python versions and POSIX behavior have not been tested.

```text
.venv\Scripts\python.exe -m pytest -q --tb=short
66 passed in 5.01s

.venv\Scripts\python.exe -m pip check
No broken requirements found.

.venv\Scripts\python.exe -m compileall -q src tests
Exit code 0; no output.
```

The isolated wheel check built and installed the wheel into a separate target and imported it from outside the checkout under Python isolated mode. It found both packaged migration resources, migrated all 41 tables, bound a synthetic guild, produced a verified copy and confirmed zero hunts. This separately checks packaging rather than relying only on the editable source installation. The final rebuilt-wheel check returned the actual output below.

```json
{
  "installed_wheel_import": true,
  "packaged_migration": true,
  "tables": 41,
  "verified_backup": true,
  "hunt_count": 0
}
```

Offline command smoke checks: check-config succeeded with the example configuration and no identity/token, reported every execution feature false and created no data directory. init-db without guild/owner IDs returned exit 2 with a safe CONFIG_INVALID message before creating runtime storage. Importing all modules under database/network/process spies started no work.

Coverage is scoped to T04, the relevant foundation portions of T14/T16, strict configuration and offline startup/import behavior. Tests exercised a valid schema upgrade preserving records; pre-upgrade copying; rollback of partial migration DDL; altered file/applied checksum and newer/unknown schema rejection; FK/NULL/enum/JSON constraints; strong-claim and single-hunt uniqueness across connections; null manual scores and immutable origins; transaction rollback; real Windows cross-process lock release after process death; real junction rejection; disk-floor failures; redaction through tracebacks and rotated logs; missing/corrupt artifacts; interrupted artifact publication and aged orphan cleanup; consistent WAL snapshots excluding uncommitted writes; hash/guild/schema/no-overwrite restore checks; and failed-backup preservation of the previous verified copy. No test skip is counted as success.

The initial full test invocation encountered 51 fixture errors because the pre-existing machine-wide pytest temporary root was inaccessible; eight non-temp tests passed. The harness now uses a fresh confined UUID directory under ignored .pytest_cache rather than modifying the unrelated machine directory. Subsequent implementation failures exposed nullable-JSON and Windows read-only-flush bugs, both corrected before the final 66/66 pass. A malformed newline test fixture was also corrected to represent an actual TOML-escaped newline.

### Limitations, configuration and next phase

The P1 foundation gate is satisfied for this tested environment. This does not satisfy full deduplication, quota, lifecycle/restart reconciliation, evidence, CRM, outreach, Discord or provider integration gates. Pending job rows are never executed by the current initializer; Phase 5's transition/recovery service is not yet implemented. Backup code is a local primitive, not the future authorized Discord backup flow; expanded manifests, retention scheduling and artifact-rich release coverage remain later work. Safe URL transport/process-tree execution, live L01/L02/L03, and later-phase workflow tests are not claimed complete.

No Discord credentials were required for these tests. The operator can check config.example.toml without secrets. Initializing real persistent state requires the intended guild and owner IDs; a real Discord connection later requires MI_BOTI_DISCORD_TOKEN stored locally. Never paste a token into documentation or chat. Source/provider enablement is rejected in this phase, even if an installation is detected.

Recommended next phase: Phase 2 Discord infrastructure, using a dedicated test guild and owner/admin identity. Implement authorization, idempotent confirmed setup and persistent controls, then verify the real sandbox-guild paths separately. Do not enable discovery/AI merely to make Phase 2 controls appear functional. D11 (verified provider), D12 (sustainable approved source) and D13 (Discord deployment identity/credentials) remain explicit inputs/gates.

### Phase 1 specification audit

The following is actual output from the post-implementation transient audit. It created a disposable database from the packaged migration, compared every table and column to doc 04, checked static settings against doc 23, resolved file/parent/anchor links, counted canonical command keys, and compared the protected AGENTS prefix hash. This is additional contract validation, not a replacement for the 66 executed behavioral tests.

```json
{
  "markdown_files": 26,
  "relative_links_checked": 249,
  "parent_relative_links": 27,
  "anchors_checked": 27,
  "broken_links_or_contracts": [],
  "sql_tables_match_spec": 41,
  "sql_columns_match_spec": true,
  "foreign_key_targets_defined": true,
  "static_config_keys_match_spec": 66,
  "command_keys": 21,
  "protected_agents_sha256": "3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259",
  "errors": 0
}
```

## Phase 2 Discord infrastructure — 2026-11-14

Implemented guild-scoped bot startup, 21 canonical command keys, fresh authorization and exact channel checks, private setup previews, actor-bound confirmation, durable setup steps, idempotent resource provisioning, four persistent panels, staged mapping/role edits and fail-closed placeholders for later phases. Restart restores routing and marks unfinished setup partial; it does not provision channels or resume autonomous work. Uncertain mutations require manual inspection and a new explicit recovery preview.

Changed application files: __main__.py, config.py, logging.py, runtime.py; new domain/discord.py, repositories/async_database.py, repositories/discord.py, services/setup.py and discord_app modules. Added the generic run-local.example.ps1 launcher and ignored operator launcher. Updated README, AGENTS appendix and component docs 06, 07, 17, 20, 21, 23 plus this ledger. Added Discord policy/setup/transport tests, extended logging tests and corrected the Windows import-side-effect test spy. No new dependencies or schema migration were required.

Executed on Windows / CPython 3.14.6:

```text
.venv\Scripts\python.exe -m pytest -q
336 passed, 16 warnings in 8.63s
.venv\Scripts\python.exe -m pip check
No broken requirements found.
.venv\Scripts\python.exe -m compileall -q src tests
Exit 0 (no output)
```

The 16 warnings originate in discord.py utils.py:1010 under Python 3.14 (positional re.sub count). They do not represent failed tests. Setup tests use real SQLite and fake Discord transport; interaction tests exercise native SDK command/view objects. No real Discord connection, channel creation, message publication, discovery request or AI task was executed in this phase. L01 and P2 completion remain pending. The replacement token is not configured in the agent environment.

The documentation audit below checks file targets including ../ links, environment-key documentation, table FK targets and the protected AGENTS byte prefix. It does not repeat the earlier scoring/state-machine audit or validate every anchor/config reference. Canonical command mappings are covered by the executed policy tests.

```json
{
  "markdown_files": 26,
  "relative_file_links_checked": 257,
  "parent_relative_links": 27,
  "broken_file_links": [],
  "command_keys": 21,
  "environment_keys": 6,
  "undocumented_environment_keys": [],
  "sqlite_tables": 41,
  "undefined_foreign_key_tables": [],
  "protected_agents_sha256": "3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259"
}
```

Local source-control limitation: the existing .gitignore also excludes AGENTS.md, docs/ and tests/. These user settings were preserved; the updated documentation and tests exist locally but will not be included by an ordinary git add. The operator launcher remains deliberately ignored and contains no stored token.

Live gate procedure: invite the dedicated bot with bot/applications.commands scopes and the documented permissions; run the ignored local launcher with a regenerated token; inspect and confirm /setup; repeat setup, exercise wrong-channel and unauthorized calls, rename/delete a managed resource, explicitly recover it, restart and inspect persistent controls. Record real permissions, private error delivery, resource/message IDs and defer timing before claiming P2 completion or proceeding to Phase 3.

### Live setup diagnostic follow-up — 2026-11-14

The local log confirms a real gateway connection and a RateLimited exception during the setup read at 2026-11-13T18:58:40Z. This proves neither successful provisioning nor P2 completion. The transport now exposes Discord's retry_after duration rather than a generic outage message, without raw HTTP content. Executed the focused transport suite after this change: 16 passed, 16 upstream SDK warnings in 2.33s. The previous launcher improvement was verified with PowerShell syntax checks and a synthetic Windows encrypted-credential export/import round trip; no real token was read by the agent.

### Rate-limit root-cause correction — 2026-11-14

Further inspection found the configured SDK max_ratelimit_timeout=30 can preemptively reject an available request whenever its bucket reset is more than 30 seconds away, even with remaining capacity. A regression using the installed SDK Ratelimit reproduces that rejection with five requests remaining and a 60-second window, then proves the corrected client admits the request. The client now uses the SDK default max_ratelimit_timeout=None; independent 15-second REST, 60-second sync and 180-second setup bounds remain. Actual Discord limits are still respected. The earlier RateLimited log alone did not prove exhausted capacity. Executed focused suite: 17 passed, 16 upstream warnings in 2.92s. Live setup confirmation remains pending after restart.

## Version 0.2.0 release checkpoint — 2026-11-14

The owner authorized committing, versioning and pushing the Phase 2 integration before Phase 3 development. Package metadata and __version__ now agree on 0.2.0; CHANGELOG.md defines release scope and README defines pre-1.0 versioning and commit conventions. The prior docs/tests/AGENTS Git exclusions were removed, superseding the earlier source-control limitation. Runtime data, secrets and the operator launcher remain ignored. Mandatory AGENTS sections 1–22 remain byte-identical to their earlier protected prefix.

Owner-provided live evidence confirms successful setup, a second successful setup, disabled-provider status in the mapped channel, wrong-channel rejection with the correct destination, and a command response after stopping/restarting the bot. The journal previously recorded a first-step HTTP 403/50013 permission failure, followed by owner-confirmed successful setup after correcting permissions. These observations establish partial L01 evidence, not every L01 case. Independent operator/unauthorized-role testing, managed resource deletion/rename/recovery, explicit post-restart component handling and measured defer timing remain unverified. P2 is not marked fully accepted and Phase 3 implementation has not started.

Executed full-suite release verification:

```text
.venv\Scripts\python.exe -m pytest -q
337 passed, 16 warnings in 7.85s
```

The warnings remain upstream discord.py Python 3.14 deprecations. No new live Discord mutations or source/AI execution were performed for release packaging. D11 provider selection/verification and D12 sustainable discovery-source approval remain open. Deployment IDs and the encrypted credential have been configured locally; secrets are not included in this release.

Release staging audit: 54 changed/new files; 259 relative file links checked with zero broken file targets; no token-shaped strings or private/runtime files found in staged content. The protected AGENTS prefix SHA-256 remains 3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259. git diff --cached --check exited 0. These checks do not constitute a full historical secret scan or anchor audit.

## Phase 3 admission prerequisites — 2026-11-14

The owner requested prerequisite verification before Phase 3 implementation. The owner confirmed that the existing Refresh status button in bot-control, clicked after the earlier restart, returned: Hunting is disabled and no hunt worker is running. Discovery, research, scoring and CRM workflows are not implemented yet. This is user-observed live persistent-control evidence; it is not an agent measurement of defer timing. A renamed-channel button check has been requested and remains pending a result.

Added scripts/check_phase2_prerequisites.py and tests/integration/test_prerequisite_check.py. The script opens an existing SQLite database in URI read-only mode with query_only enabled, closes it explicitly, never reads credentials and makes no network calls. Tests prove missing files are not created, incomplete configuration fails, persisted setup passes without changing its dump, missing command mappings fail, and local success never claims complete live acceptance.

Executed checks:

```text
.venv\Scripts\python.exe -m pytest -q
340 passed, 16 warnings in 8.73s
.venv\Scripts\python.exe -m pytest -q tests/integration/test_prerequisite_check.py
3 passed in 0.80s
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
Exit 0
sqlite_quick_check: true
foreign_keys: true
setup_ready: true
managed_resources: true
resource_parent_links: true
command_channels: true
output_destinations: true
persistent_panel_records: true
no_unfinished_setup: true
counts: resources=16, command_channels=21, output_destinations=9, panels=4, jobs=0, hunts=0
local_checkpoint_passed: true
full_phase2_accepted: false
```

The focused rerun followed explicit connection-close and missing-resource guard improvements. Remaining L01 cases are tracked in the roadmap checkpoint; they were not silently passed. Source policy/metadata pages were reviewed again, without discovery queries or dataset downloads. Initial locality/category and D12 source approval are still prerequisites. Phase 3 application features have not started and AI/hunting remain disabled. Required manual actions are the live Discord checks and later selection of the first small campaign/source fixture. No package version or release tag changed for this verification tooling.
