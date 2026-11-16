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

## Phase 3 registry/discovery-core increment — 2026-11-14

The owner authorized a staged Phase 3 start using Quezon City restaurants and cafes. The owner also confirmed channel-rename button handling and deferred the separate-user live test for the solo server; that case is NOT PERFORMED. This increment is not full P2/P3 acceptance.

Implemented: pure Unicode/domain/address/contact identity signals; bounded observations; global transactional reservations and strong claims; duplicate provenance events; conflict/review holds and cross-query open-review reuse; explicit branch distinctions; fixed bounded query templates/fingerprints; offline Overpass parsing with provenance, missing-data limitations and conservative partial-result flags. Repository writes require a matching unexpired uncancelled DISCOVER lease and RUNNING query. All dispositions participate in matching. No research, lead, scoring, AI or quota records are created.

New application files: domain/registry.py, repositories/registry.py, discovery/__init__.py, discovery/planner.py and discovery/overpass.py under src/mi_boti. New tests: tests/integration/test_registry.py and tests/unit/test_registry_normalization.py, test_discovery_planner.py and test_overpass_parser.py. Updated README, CHANGELOG, docs 04/08/21/22/23 and the ignored local AGENTS implementation appendix; mandatory sections 1–22 remain unchanged. No dependencies or migrations changed.

Verification used synthetic observations and real SQLite, including two independent concurrent connections, consistent source ownership, split strong claims, normalized aliases, every disposition, persisted restart lookup, shared signals, ambiguous review reuse, stale/cancelled/foreign-policy results, fixed-query injection rejection and malformed/partial source payloads. Ordinary tests made no live source requests. The separately bounded source probe below is the only live discovery request in this increment.

```text
.venv\Scripts\python.exe -m pytest -q
404 passed, 16 warnings in 10.67s
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
Exit 0; all nine local checks true
resources=16, command_channels=21, output_destinations=9, panels=4, jobs=0, hunts=0
full_phase2_accepted=false
```

The 16 warnings remain upstream discord.py deprecations. The production checkpoint was read-only. No real business observations were inserted and no Discord resource mutations occurred during this increment.

The owner-requested single bounded live query produced this actual diagnostic output. Timeout means a usable response did not arrive in time; it is not a zero-business result or an AI allowance event. No alternate endpoint was used.

```json
{
  "endpoint": "https://overpass-api.de/api/interpreter",
  "query_sha256": "17f5fe5005595b4a3674d99d28bc931d32398ace2f7df6fb1b8eefea770a0b34",
  "bbox": [
    14.648,
    121.047,
    14.657,
    121.061
  ],
  "categories": [
    "restaurant",
    "cafe"
  ],
  "attempts": 1,
  "element_cap": 5,
  "response_cap_bytes": 1048576,
  "client_deadline_seconds": 20,
  "production_source_approved": false,
  "state": "FAILED",
  "error_type": "ReadTimeout",
  "elapsed_seconds": 18.7
}
```

The following documentation audit was executed before adding this record. It checks local Markdown/HTML file targets and headings, including ../ links. It does not repeat the historical scoring-arithmetic or full schema/config audit. Existing schema/config values and scoring contracts were not changed.

```json
{
  "published_markdown_files": 27,
  "relative_targets_checked": 252,
  "anchors_checked": 31,
  "broken_targets": [],
  "protected_local_agents_sha256": "3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259"
}
```

Limitations: live L03 remains unpassed, D12 source approval is open, and the source must stay disabled. Campaign Discord handlers, approved SSRF-safe transport, request/daily budget reservations, persisted query/coverage lifecycle, bounded worker dispatch with fresh authorization, review resolution UI and parent-link management remain unfinished. No local extract or new parser dependency was selected or downloaded. Full Phase 3 and later phases are not complete. Required next input is a viable approved source path; further offline work can proceed without enabling it. No package release version or milestone tag is advanced for this partial increment.

## Phase 3 campaigns, query/coverage lifecycle, worker and identity review — 2026-11-14

Implemented the remaining offline Phase 3 core components while keeping live source transport (`D12`/`L03`) and AI/hunting (`D11`/`L02`) disabled:

- **Versioned non-AI campaigns (`domain/campaigns.py`, `repositories/campaigns.py`, `discord_app/bot.py`):** Validated PH geography (`<=1.0` degree bounding box, 1–25 unique cells), approved categories (`restaurant`, `cafe`), rubric v1 weights/gates, null `provider_id`, versioned edits (`campaign_versions`), archive transitions (clearing `active_campaign_id` in `guild_config`), `/campaign create|list|edit`, and `/config set key:active_campaign_id`.
- **Query and coverage lifecycle (`repositories/campaigns.py`):** Implemented `plan_unexhausted_queries`, `queue_discovery_query`, `begin_discovery_attempt` (enforcing per-query attempt caps, per-job request caps, and source daily request caps), and `finish_discovery_query` (`FRESH`, `EXHAUSTED`, and `PARTIAL` coverage cells with 30-day TTL; partial results never claim complete coverage).
- **Bounded manual discovery worker and startup recovery (`jobs/discovery.py`, `runtime.py`):** Implemented idempotent `enqueue_manual_discovery`, atomic `claim_discover_job`, `heartbeat_job_lease`, `request_job_cancellation`, `recover_interrupted_work` (marking unfinished hunts/jobs `INTERRUPTED` on startup and charging at most the reserved 30-second active lease, never the offline interval), and `execute_manual_discovery_job` using an injectable `DiscoverySourcePort` outside SQLite transactions.
- **Identity review resolution and hierarchy (`repositories/registry.py`):** Implemented `resolve_identity_review` (`LINK_EXISTING` and `CREATE_NEW`) and `link_parent_business` with named actors, revision checks, parent-cycle prevention, cross-query candidate updates, and zero retroactive hunt quota credits.

Verification executed on Windows / CPython 3.14.6:

```text
.venv\Scripts\python.exe -m pytest -q
437 passed, 19 warnings in 13.70s
.venv\Scripts\python.exe -m compileall -q src tests
Exit 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
Exit 0; local_checkpoint_passed=true, full_phase2_accepted=false
```

Limitations: live discovery source (`D12`/`L03`) remains unapproved and disabled; `/discover` remains blocked from live network calls until a permitted source path passes L03.

## Phase 3 review blocker fixes and gate status — 2026-11-14

Corrected the five Phase 3 review blockers while keeping live discovery (`D12`/`L03`), AI execution (`D11`/`L02`), and autonomous hunting disabled:

1. **Source approval (`D12`) and `L03` gate correction:**
   - The OpenStreetMap v0.6 editing API (`https://api.openstreetmap.org/api/0.6/map.json`) is governed by the [OSM API Usage Policy](https://operations.osmfoundation.org/policies/api/), which prohibits read-only projects. Although a single network request returned HTTP 200 in 2.19 seconds, connectivity to an unpermitted editing endpoint does **not** satisfy `D12` or pass `L03`.
   - Removed `map.json` support from `OverpassDiscoveryAdapter` (now explicitly rejected with `POLICY_UNKNOWN`) and restored fail-closed config validation (`enabled = true` is rejected in `src/mi_boti/config.py`). `D12` and `L03` remain **OPEN**.
2. **Complete SSRF IP pinning (`src/mi_boti/discovery/overpass.py`):**
   - `OverpassDiscoveryAdapter` resolves DNS via `resolve_public_host`, rejects the host if **any** returned record is non-global (including mixed public/private records and IPv4-mapped IPv6 addresses), rewrites the request target to the pinned literal IP (`format_pinned_url`), preserves the original `Host` header, and sets `extensions={"sni_hostname": ascii_host}` so TLS SNI and certificate hostname verification validate the original hostname without secondary DNS resolution.
3. **Fresh authorization revalidation (`src/mi_boti/jobs/discovery.py`, `src/mi_boti/discord_app/bot.py`):**
   - Replaced the captured `authorized_ok` boolean with a live callback (`_fresh_job_authorized`) re-evaluated before every external query dispatch, before every retry attempt, and before every result commit. Covers lost operator roles, changed channel mappings, incomplete configuration, and unavailable authorization checks.
4. **Non-blocking async worker execution, thread-isolated SQLite heartbeats, end-to-end deadlines, and bounded resolver/worker lifecycle (`src/mi_boti/jobs/discovery.py`, `src/mi_boti/discovery/overpass.py`, `src/mi_boti/discord_app/bot.py`):**
   - Added `execute_manual_discovery_job_async` so `/discover` executes network calls outside `AsyncDatabase`'s single-thread SQLite executor, keeping database queries responsive during slow network fetches.
   - In synchronous `execute_manual_discovery_job`, the heartbeat thread opens its own dedicated WAL `Database(db.path)` connection (`_hb_thread_loop`) rather than sharing the caller's `sqlite3.Connection` across threads or disabling `check_same_thread`.
   - Enforced a total monotonic deadline (`op_deadline` / `attempt_deadline_m`) across slot waits, DNS resolution, TCP/TLS connection, response headers, and body streaming, selecting the stricter (`min`) of an explicit `request_timeout_seconds` and `policy["timeout_seconds"]`, rejecting late responses, and registering `client.close` via `register_abort` so cancellation or timeout actively aborts in-flight HTTP work and settles jobs/queries (`INTERRUPTED`/`FAILED`/`CANCELLED`) without leaving them `RUNNING`.
   - Replaced per-attempt `ThreadPoolExecutor` workers (whose `atexit` handler blocks process shutdown on hung threads) with tracked, bounded daemon workers for both DNS resolution (`_resolve_public_host_bounded` / `active_resolver_worker_count` / `shutdown_resolver_workers`) and source execution (`active_discovery_worker_count` / `shutdown_discovery_workers`). If a DNS lookup or source call times out without cooperating with `register_abort`, the wedged worker remains tracked (`active_discovery_worker_count() == 1`), blocks further retry/job admission (`SOURCE_UNAVAILABLE`) so untracked threads never accumulate, and `shutdown_discovery_workers` honestly reports `{"drained": False, "remaining": 1}` until the thread actually exits.
5. **Process-wide source rate limiting and `Retry-After` enforcement (`src/mi_boti/discovery/overpass.py`):**
   - Shared concurrency (`max_concurrency = 1`), minimum interval (`min_interval_seconds >= 10`), and `Retry-After` backoff state across all `OverpassDiscoveryAdapter` instances via `_GLOBAL_SOURCE_RATES`. Preserves and honors `Retry-After` (delta-seconds or HTTP-date) within remaining job deadlines and budgets.

Executed verification on Windows / CPython 3.14.6:

```text
.venv\Scripts\python.exe -m pytest -q
474 passed, 37 warnings in 16.83s
.venv\Scripts\python.exe -m compileall -q src tests
Exit 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
Exit 0; local_checkpoint_passed=true, full_phase2_accepted=false
```

Phase 3 is **not** marked complete while `D12` (approved discovery source policy) and `L03` (live verification against a permitted source) remain open.

## Approved Philippines extract importer and live L03 verification — 2026-11-14

Implemented [docs/PHILIPPINES-EXTRACT-PLAN.md](PHILIPPINES-EXTRACT-PLAN.md) after the project owner approved Geofabrik's public Philippines regional OpenStreetMap extract (`https://download.geofabrik.de/asia/philippines-latest.osm.pbf`, official region page `https://download.geofabrik.de/asia/philippines.html`, ODbL license `https://www.openstreetmap.org/copyright`) as the Phase 3 discovery source direction:

1. **Optional parser dependency (`osmium==4.3.2`):**
   - Pinned `osmium==4.3.2` (PyOsmium, BSD 2-Clause) under `[project.optional-dependencies] discovery` in `pyproject.toml` and `requirements-py314-windows.txt`.
   - Installed and verified the prebuilt `osmium-4.3.2-cp314-cp314-win_amd64.whl` wheel on Windows / CPython 3.14.6 via `--only-binary=:all:` without compiling native code.
2. **Explicit bounded download, subprocess-isolated PBF import, immutable snapshot generations, and deferred cursor acknowledgement (`src/mi_boti/discovery/philippines_extract.py`, `src/mi_boti/jobs/discovery.py`, `src/mi_boti/__main__.py`):**
   - Added `download_and_import_philippines_extract`, `import_pbf_to_snapshot`, `resolve_active_snapshot_generation`, `verify_local_snapshot`, `PhilippinesExtractAdapter`, and explicit CLI commands `import-ph-extract` and `verify-ph-extract`.
   - Enforced HTTPS-only allowlisted redirects (`<=3` hops on `download.geofabrik.de`), SSRF IP pinning (`resolve_public_host` + `format_pinned_url` + `Host` header + `sni_hostname`), process-wide rate limiting (`min_interval_seconds >= 10`, `max_concurrency = 1`), streaming size caps (`<=1 GiB`), provider MD5 error-detection verification (explicitly documented as error detection, not a cryptographic signature), and local SHA-256 verification (`pbf_sha256` and `snapshot_db_sha256`).
   - Substantiated bounded parser isolation: `import_pbf_to_snapshot(..., isolate_process=True)` and the `import-ph-extract --pbf-file` CLI path enforce a finite monotonic deadline (`monotonic() + max(policy["timeout_seconds"], 1.0)`) and execute native PyOsmium (`osmium==4.3.2`) PBF parsing inside a child subprocess (`_parse_pbf_in_isolated_subprocess`), killing the child process (`proc.kill()`) immediately on timeout or cancellation without stalling the parent process or corrupting the active snapshot.
   - Streamed `amenity=cafe|restaurant` POIs via `osmium.FileProcessor` + `TagFilter`, resolved `way` and `relation` (`type=multipolygon|site|building`) geometry in a temporary disk-backed SQLite scratch database under `tmp/extract_import_<uuid>/`, labelled derived `way`/`relation` centroids `"approximate": True` with an explicit limitation note, recorded `incomplete_geometry` / `unsupported_relations` / `truncated_by_cap` counts (`incomplete_snapshot = true` prevents `EXHAUSTED` coverage claims), and preserved distinct `observed_at` (extract data timestamp) versus `local_queried_at` (query time).
   - Published each verified snapshot into an immutable generation directory `datasets/philippines/generations/<snapshot_id>/` containing its matching `snapshot.sqlite3` and `manifest.json`, serialized concurrent imports/publications via `datasets/philippines/publish.lock` (`DeploymentLock`), verified the generation directory (`_verify_generation_dir`), and switched a single active-generation pointer `datasets/philippines/active_generation.json` via `_replace_file_with_sharing_retry` (recovering from transient Windows `PermissionError` / `WinError 5` / `32` / `33` sharing conflicts under concurrent readers within bounded attempts, while cleaning up the unpublished generation directory and preserving the previous verified generation on failure).
   - Decoupled page fetching from durable cursor advancement across `mi_boti.sqlite3` and `datasets/philippines/cursors.sqlite3`, binding cursors and `checkpoint_token`s to the immutable generation ID (`snapshot_id`) as well as `snapshot_sha256`: `PhilippinesExtractAdapter.discover()` does not mutate `cursors.sqlite3`, resets `last_ord` to `0` whenever `snapshot_id` changes (even if identical PBF bytes are reimported with changed filtering or index caps), and returns `DiscoveryBatch(..., checkpoint_token=checkpoint_token)`. `execute_manual_discovery_job` and `execute_manual_discovery_job_async` invoke `source.acknowledge_checkpoint(checkpoint_token)` **only after** `resolve()`, `finish_discovery_query()`, and `jobs.progress_json` are durably committed in `mi_boti.sqlite3` under valid authorization and lease ownership. `acknowledge_checkpoint()` coordinates with `publish.lock` to prevent racing an in-flight pointer switch, validates both `snapshot_id` and `snapshot_sha256`, and advances `last_ord` monotonically under `BEGIN IMMEDIATE`. Unacknowledged pages replay safely through deduplication (`existing` count incremented, zero records skipped or duplicated).
   - Kept production discovery disabled in configuration (`src/mi_boti/config.py` rejects `enabled = true` on all sources and providers, and `config.example.toml` keeps `enabled = false`).
3. **Executed automated suite (`tests/integration/test_philippines_extract.py` and full suite):**
   - Added 12 comprehensive automated tests in `tests/integration/test_philippines_extract.py` covering policy validation, MD5 sidecar parsing, synthetic PBF `node`/`way`/`relation` import, approximate centroid labelling, incomplete geometry and unsupported relation handling, redirect validation, MD5/corrupt PBF rejection preserving the prior verified snapshot, multi-page cursor progression across capped `/discover` runs, snapshot refresh cursor reset, duplicate-only repeat queries, exhausted daily request budgets, no startup execution on `initialize(settings)`, fail-closed config rejection of `enabled = true`, failure injection between generation write and `active_generation.json` pointer switch, transient/persistent Windows sharing-conflict recovery during pointer switch, multi-reader concurrent reads during publication (verified across 10 consecutive repeat runs), serialized concurrent import/publication via `publish.lock`, deferred cursor acknowledgement across cancellation/authorization loss/post-commit crash/competing jobs/snapshot changes, reimporting identical PBF bytes with changed filtering/index caps (`snapshot_id` cursor binding and stale checkpoint rejection), and subprocess-isolated PBF parsing with `--pbf-file` deadline enforcement.

```text
.venv\Scripts\python.exe -m pytest -q
486 passed, 37 warnings in 34.31s
.venv\Scripts\python.exe -m compileall -q src tests
Exit 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
.venv\Scripts\python.exe scripts/check_phase2_prerequisites.py
Exit 0; local_checkpoint_passed=true, full_phase2_accepted=false
counts: resources=16, command_channels=21, output_destinations=9, panels=4, jobs=0, hunts=0
```

4. **Executed live `L03` discovery verification against the real Geofabrik Philippines extract:**
   - Downloaded `https://download.geofabrik.de/asia/philippines-latest.osm.pbf` (redirected to `https://download.geofabrik.de/asia/philippines-261113.osm.pbf`) and its `.md5` sidecar into a disposable SQLite workspace, imported the national extract into `datasets/philippines/snapshot.sqlite3`, and ran three Quezon City fixture discovery jobs (`bbox = [14.648, 121.047, 14.657, 121.061]`, `cafe` + `restaurant`):

```json
{
  "gate": "L03_DISCOVERY_EXTRACT",
  "provider_url": "https://download.geofabrik.de/asia/philippines-latest.osm.pbf",
  "final_download_url": "https://download.geofabrik.de/asia/philippines-261113.osm.pbf",
  "downloaded_at": "2026-11-14T12:23:11.897895Z",
  "snapshot_observed_at": "2026-11-13T21:22:20.000000Z",
  "pbf_bytes": 613918681,
  "provider_md5": "690772965227a78819ee413182ee38ba",
  "pbf_sha256": "aaf01a39336ff80a049935c66199f3786f2ece65a2f056e9ebf350f60ec191c7",
  "snapshot_db_bytes": 10465280,
  "snapshot_db_sha256": "daa61c85ac37f29d679ba69d28c374620ddfddf66f410b9406bc215eeb3b1871",
  "parser": "pyosmium==4.3.2",
  "policy_version": "geofabrik-ph-2026-11",
  "attribution": "© OpenStreetMap contributors — ODbL; https://www.openstreetmap.org/copyright",
  "download_seconds": 69.79,
  "import_seconds": 35.25,
  "national_counts": {
    "nodes_indexed": 22486,
    "ways_indexed": 3563,
    "relations_indexed": 48,
    "approximate_centroids": 3611,
    "incomplete_geometry": 1,
    "unsupported_relations": 0,
    "skipped_invalid_tags": 0,
    "truncated_by_cap": 0
  },
  "incomplete_snapshot": true,
  "limitations": [
    "1 OSM element(s) had missing or incomplete geometry."
  ],
  "qc_fixture_bbox": [14.648, 121.047, 14.657, 121.061],
  "query_1_page_1": {
    "state": "SUCCEEDED",
    "elapsed_seconds": 0.4917,
    "dispositions": {
      "seen": 25,
      "new": 24,
      "existing": 0,
      "ambiguous": 0,
      "invalid": 1,
      "discovery_requests": 1,
      "phase": "COMPLETED"
    }
  },
  "query_2_page_2_cursor": {
    "state": "SUCCEEDED",
    "elapsed_seconds": 0.1949,
    "dispositions": {
      "seen": 7,
      "new": 6,
      "existing": 0,
      "ambiguous": 0,
      "invalid": 1,
      "discovery_requests": 1,
      "phase": "COMPLETED"
    }
  },
  "query_3_repeat_page_1": {
    "state": "SUCCEEDED",
    "elapsed_seconds": 0.3548,
    "dispositions": {
      "seen": 25,
      "new": 0,
      "existing": 24,
      "ambiguous": 0,
      "invalid": 1,
      "discovery_requests": 1,
      "phase": "COMPLETED"
    }
  },
  "disposable_db_totals": {
    "businesses": 30,
    "open_identity_reviews": 0,
    "hunt_credits": 0,
    "coverage_state": "PARTIAL"
  }
}
```

5. **Remaining limitations and gate status:**
   - The Philippines OSM regional extract discovery source direction (`D12` for Phase 3 discovery), recovery requirements (immutable snapshot generations, deferred cross-database cursor acknowledgement, and subprocess-isolated PBF parsing), and live `L03` discovery subset are now verified.
   - Production discovery remains disabled in configuration (`src/mi_boti/config.py` rejects `enabled = true` on all sources and providers, and `config.example.toml` keeps `[sources.philippines_extract] enabled = false`).
   - Full Phase 2 (`L01` remaining live cases) and full Phase 3 (Discord identity-review resolution UI and live Discord `/campaign` + `/discover` walkthrough) remain tracked before claiming full P2/P3 completion.
   - Phase 4a website research policies (`D12` website sources), AI provider verification (`D11`/`L02`), Phase 4b scoring, and Phase 5 autonomous hunting remain disabled.

## Codex checkpoint-lock and DNS-test fixes — 2026-11-14

Applied the requested follow-up to the current uncommitted Phase 3 implementation. `PhilippinesExtractAdapter.acknowledge_checkpoint()` now calls `DeploymentLock(...).acquire()` before validating the active generation or writing its cursor, and releases ownership in its existing finally block. The new lock-contention regression holds the actual OS publication lock through a distinct owner, proves acknowledgement returns False within its bounded wait without inserting a cursor, then verifies the same token can commit after release and that acknowledgement releases the lock afterward.

The stalled-DNS regression no longer depends on the OS scheduling a new source and resolver thread within a 100 ms attempt budget. It gives the fixture a unique source/limiter key, explicitly establishes a resolver blocked on a test-controlled event, cancels and joins the initiating probe, then verifies sync/async job admission remains blocked, no second resolver starts, strict timeout selection remains unchanged and shutdown truthfully reports outstanding work. Cleanup releases the resolver in finally and inspects only this fixture's worker state rather than unrelated global workers. Separate existing tests continue to cover actual request deadlines and late-response rejection; production timeout behavior was not relaxed.

Executed verification:

```text
Focused lock-contention and stalled-DNS regressions:
2 passed in 3.16s
Five separate consecutive stalled-DNS regression invocations:
1 passed in 0.42s
1 passed in 0.55s
1 passed in 0.89s
1 passed in 0.76s
1 passed in 0.62s
.venv\Scripts\python.exe -m pytest -q
487 passed, 37 warnings in 31.14s
```

The warnings remain existing discord.py deprecations. Changed application/test files: src/mi_boti/discovery/philippines_extract.py, tests/integration/test_philippines_extract.py and tests/integration/test_discovery_worker.py. This ledger and DEVELOPMENT-HANDOFF.md were updated with the results. No production data or Discord resources were modified, no source download/probe was performed and discovery/AI/hunting enablement was not changed. Other Antigravity work remains uncommitted; this follow-up does not claim full P2/P3 acceptance or replace the remaining live workflow/review-UI gates.

## Owner-requested tool guide — 2026-11-16

Implemented the requested private guide channel under Control Center, a persistent guide panel, a dashboard navigation link and the guide canonical command. The guide covers every command key with purpose, current mapped channel, usage and availability, plus result terminology and the first campaign steps. It explicitly distinguishes implemented, disabled and planned tools and never starts jobs/source/AI work. The manifest now contains four categories and thirteen text channels (17 resources), 22 command mappings, nine output destinations and five mandatory panels. Counts in automated setup fixtures were updated to the new manifest; no SQL migration or configurable key was added.

Existing guilds must restart and explicitly preview/confirm /setup to add the guide. Until that upgrade is approved, missing guide resources/mappings/panels fail readiness closed while the setup exception remains available. No real server resources were created or changed during development. Initial creation, repeated setup, legacy-workspace upgrade, private command/button output, wrong-channel rejection and help-catalog/embed limits are covered by synthetic tests. Human-readable guide publication and readability in the real guild remain a live check after confirmation.

Executed checks:

```text
Focused initial guide content, private interaction and legacy upgrade tests:
4 passed in 1.05s
.venv\Scripts\python.exe -m pytest -q
502 passed, 39 warnings in 21.17s
After the final /guide command-description/registration refinement:
.venv\Scripts\python.exe -m pytest -q tests/integration/test_discord_transport.py tests/unit/test_operator_guide.py
23 passed, 39 warnings in 3.41s
```

Warnings remain upstream discord.py deprecations. Changed application files: domain/discord.py and discord_app/bot.py, transport.py, views.py; added discord_app/guide.py. Tests: updated setup/prerequisite counts, added guide integration/upgrade checks and tests/unit/test_operator_guide.py. Updated README, CHANGELOG and docs 06/07/16 plus this acceptance record and development handoff. Existing runtime datasets/registry/configuration and provider gates remain unchanged. Phase 3 identity review UI and the live campaign/discovery walkthrough are still pending; this guide addition does not claim phase completion.

## Phase 3 identity-review UI — 2026-11-16

Implemented private /lead inspection for review/business/lead UUIDs and a ten-item open-review queue. Reviews display source assertions, observation time, address and suggested identities. Link/separate previews require a rationale and an actor-bound five-minute confirmation. Confirmation rechecks live membership, channel policy and managed resources. Linking uses the previewed business revision; repository transactions retain provenance and prevent double resolution. Concurrent clicks, replay, expiry, stale revisions, another actor, wrong channel, lost membership and invalid rationale have regression coverage. No migration, runtime-source enablement, AI execution or production-data change was made. CRM qualification, notes and history remain unimplemented.

Executed verification:

```text
.venv\Scripts\python.exe -m pytest -q
512 passed, 108 warnings in 24.75s
.venv\Scripts\python.exe -m compileall -q src tests
Exit code 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
git diff --check
Exit code 0 (line-ending notices only)
git ls-files AGENTS.md
(no output)
git check-ignore AGENTS.md
AGENTS.md
```

The warnings are the existing discord.py positional-count deprecation, exercised by additional escaping tests. Live rendering and the campaign/discovery operator walkthrough remain pending; this is not full Phase 3 acceptance. Transient private confirmations do not survive restart and must be reopened. Changed files: discord_app/identity.py, bot.py, guide.py, tests/integration/test_identity_ui.py, README, CHANGELOG, docs 07/22 and DEVELOPMENT-HANDOFF.

## Manual local-source enablement — 2026-11-16

Owner authorized proceeding with snapshot discovery followed by Phase 4a live website research. Added the narrow config gate for the verified Philippines extract only; Overpass, unknown sources and AI remain blocked. Source policy validation checks safety bounds, current dates, approved endpoint/host and categories. Status/campaign replies now reflect enabled configuration instead of hardcoding discovery as unavailable. Example policy stays disabled by default; ignored local config now contains the reviewed policy enabled after successful import/verification. No application registry rows were inserted and no bot or Discord operation was launched by this work.

Actual local import and independent verify-ph-extract output agreed:

```text
snapshot_id: c89257a5-e373-426f-9b2b-d86640775829
snapshot_observed_at: 2026-11-15T21:22:28.000000Z
pbf_sha256: c48acd3cc4c6a907b0d8f42fcfd1c942f3ad2825d1733d8cc229fd7a1c12a0aa
snapshot_db_sha256: 89402014fadaf84ca7f8c48893a51201cd52aa7c2c372434feb1896059722466
nodes_indexed: 22484; ways_indexed: 3562; relations_indexed: 48
approximate_centroids: 3610; incomplete_geometry: 1; incomplete_snapshot: true
skipped_invalid_tags: 0; truncated_by_cap: 0; unsupported_relations: 0
verify-ph-extract: verified=true
pytest -q: 518 passed, 108 warnings in 22.61s
compileall -q src tests: exit code 0
pip check: No broken requirements found.
check-config: configuration=valid, discovery_enabled=true, ai_enabled=false, hunting_enabled=false
```

The shell check-config intentionally used no Discord identity/token; its guild/owner/token flags were false. The existing launcher supplies identity and cached credentials when the owner restarts it. No credentials were read. Warnings remain discord.py deprecations. Owner screenshots confirm private /lead empty queue and real campaign creation, not live link/separate confirmation or /discover results. Next live check: restart and run a bounded /discover for the saved campaign. Phase 3 remains unaccepted pending that walkthrough; no Phase 4a fetching is implemented or claimed here.

## Discovery result browser — 2026-11-16

Owner's screenshot shows job 70ac3fe6-5d59-41e8-ab0e-bf7201d0ba72 SUCCEEDED with requests=1, seen=10, new=10, existing=0, ambiguous=0, invalid=0. This is owner-supplied live command evidence, not a developer replay or complete Phase 3 acceptance.

Implemented private saved-observation pages automatically following the completion summary. /discover job_id:<UUID> page:<int> reopens historical jobs independently of source availability, without source calls or new jobs. Pages show names, business IDs, disposition, source identifiers and observation dates. Actor-bound ten-minute controls recheck current discover authorization and offer saved source/address/attribution/limitation details; they do not bypass lead-channel identity decisions. Added tests for record lookup, empty pages, private rendering, detail selection, wrong channel, another actor, lost membership, expiry and unchanged candidate state/no dispatched tasks. No migration, provider call or runtime-data mutation was needed.

Executed checks:

```text
.venv\Scripts\python.exe -m pytest -q
525 passed, 174 warnings in 21.22s
.venv\Scripts\python.exe -m compileall -q src tests
Exit code 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
git diff --check
Exit code 0 (line-ending notices only)
```

Warnings are existing discord.py positional-count deprecations exercised by additional escaping. Changed: discord_app/discovery_results.py, bot.py, guide.py; tests/integration/test_discovery_results_ui.py; README, CHANGELOG, docs 07/22/LOCAL-OPERATIONS and DEVELOPMENT-HANDOFF. Live result-card rendering after restart remains pending. Website research/qualification/AI/hunting are not implemented or enabled by this increment.

## Phase 4a collection/evidence foundation — 2026-11-16

Owner screenshots verify saved discovery-list and detail rendering. Corrected detail presentation: empty addresses now say Not provided by this source; limitation strings render as prose instead of JSON arrays. This does not infer missing business data.

Added research/collector.py and repositories/research.py with independent unit/integration tests. The collector requires a current named exact-host access-review input before any request, then validates robots, pins public DNS results for actual HTTPX destinations with Host/SNI retained, serializes host starts at least two seconds apart, bounds redirects/body/text/pages/requests/time, rejects unsupported compression/MIME, extracts literal public text, and preserves source/final URL, timestamps, policy version and hashes. DNS admission remains reserved until a cancelled resolver actually finishes. Critical URL/DNS/redirect violations fail the collection. The evidence repository requires an owned uncancelled manual RESEARCH lease and explicit refresh/analyze:false, blocks unresolved identity, validates excerpt hashes/times and writes new immutable research/evidence rows. It never inserts findings, scores, leads or quota credits.

Executed checks:

```text
Focused collector tests: 26 passed in 18.43s
Full suite: 553 passed, 174 warnings in 38.90s
.venv\Scripts\python.exe -m compileall -q src tests
Exit code 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
git diff --check
Exit code 0 (line-ending notices only)
```

The warnings remain existing discord.py deprecations. Tests use simulated DNS/HTTP; no business website was fetched and no live OS/TLS collector verification was claimed. Provider-free architecture and zero score/lead/quota writes are verified at the module/repository boundary; full runtime provider-spy coverage is still pending integration. No schema change or new dependency. Research stays unavailable from Discord: durable worker/admission/cancellation/recovery, persisted reviewed-site policies, configuration-driven runtime limits, UI and live research checks are pending. This increment does not complete P4a or waive remaining P3 live acceptance. New modules are staged library code, not a production-ready fetch release.

## Phase 4a Discord research integration — 2026-11-16

Implemented /research collect/status/cancel/review/revoke using the existing canonical research command and business-research mapping. Site-access review is administrator-only, actor-bound, expires after five minutes as a confirmation, compares config revision and records an exact-host seven-day named policy/rationale. Current reviews live in guild_config.settings_json.research_access (at most 64), with full audit history on edits and revocation. The saved URL is explicit and never guessed. An empty research.user_agent blocks collection; the ignored deployment config now uses the repository's descriptive contact URL. No credential was read or changed.

Research admission requires explicit refresh and analyze:false, resolved identity, current access review and available background-job slots. Replayed interactions reuse the original job without another fetch. Shared async collection runs outside the SQLite owner; each dispatch checks authorization/policy/lease after DNS. Monitoring polls persisted policy/cancellation once per second and Discord authorization at the heartbeat interval. Final evidence/run/job success is atomic and validates the access-policy version/host inside the transaction. Cancel/revoke/role loss abort collection before failure settlement; shutdown and startup recovery mark queued/running research and unfinished runs INTERRUPTED without auto-resume. Native DNS uses at most two admitted daemon workers; cancellation retains a DNS slot until the resolver really finishes, so stalled OS resolution cannot accumulate work or delay process shutdown.

Executed final automated verification:

```text
.venv\Scripts\python.exe -m pytest -q
572 passed, 261 warnings in 48.82s
.venv\Scripts\python.exe -m compileall -q src tests
Exit code 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
git diff --check
Exit code 0 (line-ending notices only)
```

The warnings remain upstream discord.py escaping deprecations. New workflow cases cover success, immutable refresh, idempotent replay, cancellation, access revoke/version change, permission loss, shutdown, restart of queued/running jobs, AI denial, missing policy, wrong channel, and wrong-actor/expired/stale/ordinary-member review confirmations. Success/failure paths use subprocess/API spies that fail if a CLI or incidental HTTP client is invoked outside the collector, and assert no findings, scores, leads or credits. Collector tests additionally prove pinned IPv4/IPv6, mixed-DNS/rebinding rejection, robots/MIME/body/redirect controls, and retained admission for cancelled native DNS.

Real collector probe against the documented public HTTP test service [HTTPBin](https://httpbin.org/) and its [robots policy](https://httpbin.org/robots.txt):

```text
state=SUCCEEDED, requests=2, pages=1
observed_at=2026-11-16T08:00:31.875790Z
excerpt_sha256=b04ac75624cb829db0e502fc04d2758ba7de1dd4531467b80d7cd62a5137ccfb
limitations=[]
```

A second explicit probe exercised durable admission, a real collector and evidence commit in disposable fixture .pytest_cache/live-research/9caf1d48111c4d7ba66ca248710d69c5 (production registry untouched):

```text
job_state=SUCCEEDED; error_code=null; requests=2
run_id=a44fe9cd-788c-48d7-9dd9-f4a85cff0446
evidence_id=ce5049c1-0277-4faf-932f-8a14c1d3a276
research_runs=1; evidence=1; findings=0; scores=0; leads=0; hunt_credits=0
Discord authorization=simulated; not live L01
```

The first full-pipeline fixture attempt lacked a guild_config row and stopped before any fetch. The fixture setup was corrected and prepare_access now reports missing setup safely. Technical fixture policies were developer-only and never installed into production or represented as owner approval for a business. Real HTTP transport evidence does not complete real Discord/business-site acceptance. The first ten saved production observations contain no website URL; an explicit official URL and access review are still required for that check. No production review, research job, evidence record or real Discord resource was created by development.

Changed application files: discord_app/bot.py, guide.py, transport.py and new research.py; jobs/discovery.py and new jobs/research.py; repositories/research.py and new research_access.py; research/collector.py. Tests: new integration/test_research_workflow.py, extended unit/test_website_collector.py, updated unit/test_operator_guide.py. Updated README, CHANGELOG, docs 04/07/09/17/21/23/LOCAL-OPERATIONS, this record and DEVELOPMENT-HANDOFF. No SQL migration, added dependency, application-version bump or AI/provider enablement. Remaining limits: conservative compression/robots rejection, one attempt/page within configured maximum, 32 requests/120 seconds per collection, 64 reviewed businesses/host admissions, evidence-card previews rather than full-text export. P4a and remaining P3 live acceptance remain open pending owner-driven checks.

Final documentation/authority spot check (file targets only; anchor IDs and the full historical command/schema/scoring audit were not rerun):

```text
AGENTS sections 1-22 SHA256: 3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259
{"markdown_files": 28, "relative_targets_checked": 302, "missing_file_targets": []}
git ls-files AGENTS.md: (no output)
git check-ignore AGENTS.md: AGENTS.md
```

The final collector guard tests additionally deny access before DNS and again after DNS, with zero HTTP dispatch. The final executed full-suite result is 572 passed, 261 warnings in 48.82s.

Owner clarified that no sample website is available. A read-only web lookup identified [Max's official brand site](https://maxschicken.com/) as a candidate corresponding to the discovered brand name. This does not establish branch-specific identity or automated-access permission. The browsing tool could not verify its robots URL, and no adequate same-host automation permission reference was established, so no production access review or business collection was approved. Do not treat this lookup as Mi Boti research evidence or a passed business-site live check.

## Autonomous live-source testing and continued development — 2026-11-16

Owner authorized testing without requiring them to provide a sample, then continuing development. Reviewed [Scrape This Site's official FAQ](https://www.scrapethissite.com/faq/), which expressly permits automated access with an identifying user-agent, robots compliance and a maximum of one request/second. Mi Boti uses at least two seconds between host request starts. Its public training-service homepage was used for isolated source validation, not a Philippine prospect or owner-approved production record. No bot token, production access policy or production research data was used/changed. Real Discord delivery was not exercised by this test.

Actual public sandbox smoke checks:

```text
https://www.scrapethissite.com/pages/simple/
SUCCEEDED; requests=2; pages=1
excerpt_sha256=a1b859f8b508651aa89ca5243f059481b06f32ea8b73aa39fddff3c3c7f7577a
https://books.toscrape.com/
FAILED; requests=1; pages=0
Website or robots policy was unavailable; no access bypass was attempted.
```

The first isolated full worker/evidence/viewer fixture used the live countries sandbox page, stored 18,262 characters including the source-assertion label, and rendered the saved excerpt across 16 evidence pages. It recorded one research run/evidence and zero findings/scores/leads/credits. Fixture: .pytest_cache/live-research/fa329e6ff4b44ebf9c643ed1b28d0725. No production records were added.

A second full worker test collected the permitted training-service homepage twice, reusing the shared collector/robots cache and preserving the original evidence unchanged. Actual output:

```text
source_url=https://www.scrapethissite.com/
permission_reference=https://www.scrapethissite.com/faq/
run 1: SUCCEEDED; requests=2; evidence=5f69d8d2-83d8-48ef-8247-88dee5502a36
observed_at=2026-11-16T08:49:58.133135Z
run 2: SUCCEEDED; requests=1; evidence=f9585490-e4fa-4205-b8a5-02de1d6128c3
observed_at=2026-11-16T08:49:59.645131Z
original_evidence_unchanged=true
research_runs=2; evidence=2; findings=0; scores=0; leads=0; hunt_credits=0
production_data_changed=false
Discord authorization=simulated; real Discord delivery not exercised
fixture=.pytest_cache/live-research/c5518c2d3276499780bbbcaec1f6aff9
report=LIVE-RESEARCH-REPORT.md
```

Continued development after live collection: /guide refresh:true now permits owner/admin to edit only the already managed bot-owned saved guide message. It never creates resources/messages/jobs, preserves IDs/revisions and fails closed for missing/unowned targets. Default guide reads remain private. Research result dropdowns and /research action:evidence evidence_id:<UUID> page:<int> now expose complete immutable saved excerpts in 1,200-character pages with source, timestamp, policy version, confidence and limitations. Actor/expiry/member/channel checks repeat on every control; reading never refetches or enqueues work. Extraction now records when the configured text cap may omit further source content.

Executed checks:

```text
.venv\Scripts\python.exe -m pytest -q
584 passed, 341 warnings in 51.03s
After final policy-version/source-reference card-label refinement:
.venv\Scripts\python.exe -m pytest -q tests/integration/test_evidence_reader.py tests/integration/test_discord_transport.py tests/unit/test_operator_guide.py
35 passed, 143 warnings in 5.03s
.venv\Scripts\python.exe -m compileall -q src tests
Exit code 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
git diff --check
Exit code 0 (line-ending notices only)
```

Warnings remain discord.py escaping deprecations. New tests reconstruct the full saved text across pages, validate embed limits/mention escaping, deny stale/foreign/wrong-channel/revoked evidence controls, exercise evidence selection, and verify guide refresh does not create anything and refuses another author's message. Changed application files: discord_app/bot.py, guide.py, research.py, transport.py, new evidence.py and research/collector.py. Tests: fakes_discord.py, integration/test_discord_transport.py and new integration/test_evidence_reader.py. Updated README, CHANGELOG, docs 07/09/16/LOCAL-OPERATIONS, this record and DEVELOPMENT-HANDOFF. No migration, dependency, application-version bump or AI enablement. Real successful /research delivery and guide-refresh rendering in Discord remain pending; P4a is not declared complete and no real prospect is qualified by these tests.

## Research backup/recovery checkpoint — 2026-11-16

Added offline research-integrity validation to basic backup verification: evidence must belong to its research run's business, research runs must refer to RESEARCH jobs with matching business ownership when populated, successful/partial runs retain evidence, and literal excerpt hashes/metadata must match saved text. Existing SQLite FK checks alone cannot detect valid-FK wrong-business provenance or modified excerpt text. Copies failing these invariants are not published. Other evidence types without excerpt-hash metadata are not forced into the literal HTML format.

A real disposable process drill found a restore-startup bug: verification of a WAL-mode temporary copy left .partial-wal and .partial-shm companions, and normal prepare_data_root correctly rejected those unrelated root files. Fixed both backup and restore by checkpointing/sealing the private output copy in DELETE journal mode before publication, with cleanup restricted to the generated temporary basename and its exact SQLite companions. The active source stays WAL. The regression explicitly reopens the restored directory through normal private-root preparation; source WAL and standalone backup DELETE modes are checked.

Executed checks:

```text
.venv\Scripts\python.exe -m pytest -q
591 passed, 361 warnings in 51.66s
After explicit source/backup journal-mode assertions:
.venv\Scripts\python.exe -m pytest -q tests/integration/test_research_recovery.py tests/integration/test_storage.py tests/integration/test_research_checkpoint.py
23 passed in 1.86s
.venv\Scripts\python.exe -m compileall -q src tests scripts
Exit code 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
```

The process drill used a disposable copy of the earlier permitted live-source fixture, created/claimed a RESEARCH job and run in a child process, then deliberately called os._exit after its commit. The parent created a verified backup after that abrupt exit, restored into a different prepared root, and invoked normal initialize/recovery. First attempt failed on the sidecar bug above; the corrected rerun passed. Actual final output:

```text
fixture=.pytest_cache/research-recovery/f7616972fed74d26aff63fb1d42789a2
committed_before_exit=true
backup_sha256=fd92fef1a87d25cd0507d8a9fc63f7f5f2a49007a0f7801d7bbaab113e419d66
backup_bytes=733184
research_runs=3; evidence=2; excerpt_hashes=2
original_evidence_unchanged=true
access_reviews_unchanged=true; restored_review_records=1
recovered_job=INTERRUPTED; recovered_run=INTERRUPTED
running_jobs_after_restart=0
temporary_sidecars_before_restart=[]
network_or_provider_called=false; production_data_changed=false
```

Added scripts/check_research_prerequisites.py, a credential-free read-only checkpoint. Actual production-database output:

```json
{"checks":{"foreign_keys":true,"migration_history":true,"research_integrity":true,"schema_version":true,"setup_ready":true,"sqlite_quick_check":true},"evidence":0,"excerpt_hashes":0,"full_phase4a_accepted":false,"limitations":["Local records do not prove current Discord permissions, site access permission, HTTP compatibility or live delivery."],"local_checkpoint_passed":true,"mode":"read_only","research_runs":0,"unexpired_review_records":0,"unfinished_research_jobs":0}
```

No fixture records, credentials, source policies or bot operations were written into production. The computer-use skill was used to inspect existing Discord session availability/navigation. Native desktop input recovery reported coordinate input geometry is unavailable, then user input was detected in this window; desktop automation stopped without submitting slash commands or editing server content. Earlier owner reports verify missing-review rejection, AI-disabled rejection and wrong-channel restriction. Successful research/evidence delivery in real Discord remains unverified. T13/T16 research-local recovery checks now have automated and process-level evidence; this does not complete L01 or full P4a. CRM implementation has not started because its preceding phase remains unaccepted.

Changed: storage/backup.py; new repositories/research_integrity.py and scripts/check_research_prerequisites.py; new integration/test_research_recovery.py and test_research_checkpoint.py. Updated README, CHANGELOG, docs 05/20/LOCAL-OPERATIONS, this acceptance record and DEVELOPMENT-HANDOFF. No SQL migration, dependency, version/tag change or AI enablement.

## Owner-approved isolated CRM core — 2026-11-16

The owner explicitly selected Begin isolated CRM development after being asked about the open Phase 4a successful live-Discord check. Recorded FINAL decision D16 in README and a roadmap sequencing exception. Local ignored AGENTS.md adds the owner exception after the mandatory sections; sections 1–22 remain byte-identical with SHA-256 3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259. This permits development only, not release or Phase 4a/6 acceptance.

Implemented domain/crm.py, repositories/crm.py and services/crm.py. Manual qualification validates current business revision, unresolved identity holds, one-to-ten distinct source-linked same-business evidence records, nonempty human rationale and evidence excerpt/time integrity. It creates exactly one MANUAL/NEW lead with null score, records named evidence/rationale and updates business disposition/revision without touching origin ownership, scores, findings or hunt credits. It makes no automatic claim about business software needs. Independent competing SQLite writers cannot create duplicate leads.

The pipeline implements the complete documented graph. READY requires explicitly reviewed evidence plus an existing source-backed contact; CONTACTED requires operator attestation of manual contact; FOLLOW_UP creates a future UTC PENDING due item atomically; outcomes/reopening require notes. Notes and corrections append with named author/time, validate same-lead correction references and increment lead revision. Stage/note mutations do not silently overwrite stale revisions or alter business qualification disposition. Reads provide business names and bounded ten-record lead/note/event pages.

ManualCrmService requires an injected fresh asynchronous authorizer and explicit confirmation for qualification/transitions. Within each transaction it repeats persisted guild/readiness/channel/resource/operator-grant checks. The service does not itself obtain Discord membership; the eventual adapter must bind the live interaction and supply real fresh authorization. This is not yet a Discord preview/confirmation implementation. All CRM command placeholders remain disabled and no runtime data was changed.

Executed checks:

```text
Focused isolated CRM and research recovery tests:
94 passed in 6.61s
.venv\Scripts\python.exe -m pytest -q
680 passed, 361 warnings in 59.57s
.venv\Scripts\python.exe -m compileall -q src tests scripts
Exit code 0
.venv\Scripts\python.exe -m pip check
No broken requirements found.
git diff --check
Exit code 0 (line-ending notices only)
AGENTS mandatory prefix SHA256:
3c139ab0bdbb9a434d587f2ca45f3ba117963a19bce5fd9e362bf7747aeaf259
git check-ignore AGENTS.md
AGENTS.md
```

Warnings are the existing upstream SDK deprecation. T12 isolated-core tests use an independent expected graph for all 64 stage pairs, prerequisite and revision failures with complete rollback, foreign/empty/duplicate/tampered/unknown-confidence/future evidence, duplicate-lead races across real separate connections, append-only corrections, fresh authorization/role/channel/confirmation guards, and backup/restore persistence of stage/note/event history. Network/provider spies reject unexpected HTTP/CLI execution in service tests. Source provenance and evidence excerpt hashes share a reusable verifier with backup validation.

Changed application files: new domain/crm.py, repositories/crm.py, services/crm.py; factored repositories/research_integrity.py excerpt validation for reuse. Added integration/test_manual_crm.py. Updated README (status/decision D16), CHANGELOG, docs 04/14/20/21, this record and DEVELOPMENT-HANDOFF; local AGENTS remains ignored/untracked. No SQL migration, dependency, bot registration, source request, version/tag or AI/hunting enablement. Remaining: reviewed contact capture, actor-bound Discord qualification/pipeline confirmations/rendering, CRM list/detail/notes adapters, reminders, exports and manual drafts. No full T12, P4a, P6 or live-readiness claim is made.

## Isolated contact capture and CRM interaction verification � 2026-11-16

Continued owner-authorized D16 development without registering CRM commands or changing production records. Added source-backed EMAIL/PHONE/WEBSITE contact capture, supporting registry identifiers, read-only previews and actor-bound expiring native Discord confirmations. Added bounded lead/detail/note views and full review-text access. Confirmation repeats authorization and revision checks; cancellation, replay and stale proposals cannot apply mutations. Explicit null revisions fail closed. Literal contact proof rejects guessed, partial and Unicode-confusable matches; URL paths remain exact without punctuation trimming. Shared contacts do not merge businesses. Qualification remains MANUAL with no score or hunt credit.

Executed verification:

```text
.venv\Scripts\python.exe -m pytest -q
723 passed, 514 warnings in 91.93s
.venv\Scripts\python.exe -m pytest -q tests/integration/test_crm_interactions.py tests/integration/test_manual_crm.py
135 passed, 153 warnings in 19.19s
```

The full suite preceded final contact-proof refinements; the focused result above covers those refinements and two additional exact-URL regressions. Do not interpret 723 as a final full-suite rerun. Warnings originate in discord.py's deprecated positional re.sub count. Tests use synthetic SQLite records and native Discord objects with simulated transport/authorization; no real Discord acceptance is claimed.

Application files: src/mi_boti/repositories/crm.py, src/mi_boti/services/crm.py and new src/mi_boti/discord_app/crm.py. Tests: tests/integration/test_manual_crm.py and new tests/integration/test_crm_interactions.py. Documentation: README, CHANGELOG, docs 04/14/16/20/21/22 and DEVELOPMENT-HANDOFF. No migration, dependency, version/tag, runtime registration, provider call, autonomous hunting or outreach sending was added. Contact proof conservatively requires a literal saved observation (or exact observed website URL); inferred routes and unsupported formatting remain rejected.

Remaining: connect and accept CRM interaction routes/input workflows before release, then implement manual drafts and follow-up delivery under the existing specifications. Successful live-Discord research delivery remains open; neither Phase 4a nor Phase 6 is accepted by these isolated tests. AGENTS.md remains local and ignored.

Additional executed checks: `compileall -q src tests scripts` exited 0; `pip check` reported `No broken requirements found.`; `git diff --check` exited 0 with line-ending notices only.
