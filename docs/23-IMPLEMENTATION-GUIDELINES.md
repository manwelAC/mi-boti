# 23 — Implementation guidelines and configuration

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and authority

This implementation baseline ties [architecture](02-TECHNICAL-ARCHITECTURE.md), [schema](04-DATABASE-SCHEMA.md), [security](18-SECURITY-AND-PRIVACY.md), and [roadmap](21-DEVELOPMENT-ROADMAP.md) together. Read `AGENTS.md` first. The owner has authorized Phase 0 assessment, Phase 1 foundation and Phase 2 Discord infrastructure implementation; later components retain their phase gates.

## Configuration ownership and precedence

Environment owns secrets and deployment bootstrap. A local UTF-8 TOML file owns nonsecret immutable process settings and policy manifests. SQLite owns mutable guild mappings, role grants, active campaign and versioned campaign settings. Effective values are built from documented defaults then local TOML; mandatory environment identity/secrets override corresponding bootstrap fields only. There is no generic “environment overrides everything” mechanism. After initial guild binding, a conflicting environment guild ID fails startup. Unknown keys are errors; do not ignore typos. Secrets never appear in TOML or Discord `/config view`.

| Environment variable | Required/default | Validation and handling |
|---|---|---|
| MI_BOTI_DISCORD_TOKEN | Required to connect | Nonempty opaque secret; never print; missing prevents connection |
| MI_BOTI_APPLICATION_ID | Optional | Canonical positive snowflake; if set, must match the authenticated application before command sync |
| MI_BOTI_GUILD_ID | Required | Canonical positive snowflake matching DB binding |
| MI_BOTI_OWNER_IDS | Required | Comma-separated unique positive snowflakes; at least one |
| MI_BOTI_CONFIG_FILE | `./config.toml` relative to launch directory | Resolve once to existing local file; no remote URL |
| MI_BOTI_DATA_DIR | `./data` relative to launch directory | Resolve absolute once, create safely, verify permissions/free space and lock |

Do not define token/API-key defaults, auto-read arbitrary `.env` files, or forward the whole environment to providers. Provider-specific official credential locations are documented only after Phase 0 verification; their secrets remain provider-managed.

## Local TOML keys and defaults

These are the canonical key names for limits referenced throughout the package. All integer limits must be positive unless explicitly stated. Review necessary dependency versions and target OS/Python range in Phase 1; the specification does not fabricate a tested version pin.

| Key | Default / validation |
|---|---|
| runtime.log_level | `INFO`; DEBUG/INFO/WARNING/ERROR only; redaction always on |
| runtime.log_max_bytes | 5242880 |
| runtime.log_backups | 5 |
| runtime.sqlite_busy_timeout_ms | 5000 |
| runtime.minimum_disk_free_mib | 500 |
| jobs.max_concurrency | 2 |
| jobs.ai_concurrency | 1; AI concurrency fixed at 1 in initial release |
| jobs.lease_seconds | 30; heartbeat < lease/2 |
| jobs.heartbeat_seconds | 10; heartbeat < lease/2 |
| jobs.max_attempts | 3 total; specific stricter limits win |
| jobs.retry_base_seconds | 2; exponential, within remaining active and absolute-age budgets |
| jobs.retry_jitter_seconds | 1; exponential, within remaining active and absolute-age budgets |
| jobs.cancel_grace_seconds | 10 |
| jobs.manual_max_age_seconds | 3600 wall-clock ceiling for a standalone non-hunt job |
| hunt.max_quota | 100; operator quota 1..max |
| hunt.base_discovery_requests | 20 minimum effective requests |
| hunt.discovery_requests_per_lead | 2 per quota lead |
| hunt.max_discovery_requests | 200 absolute request cap |
| hunt.base_candidates | 200 minimum effective observations |
| hunt.candidates_per_lead | 20 per quota lead |
| hunt.max_candidates | 2000 absolute observation cap |
| hunt.base_http_requests | 800 minimum effective HTTP requests |
| hunt.http_requests_per_lead | 160 per quota lead |
| hunt.max_http_requests | 16000 absolute HTTP request cap |
| hunt.base_ai_tasks | 100 minimum effective AI executions |
| hunt.ai_tasks_per_lead | 20 per quota lead |
| hunt.max_ai_tasks | 2000 absolute AI task cap |
| hunt.quota_block_size | 5 leads per active-time block |
| hunt.max_active_seconds | 3600 base active seconds per quota block; RUNNING/PAUSING/STOPPING only |
| hunt.max_active_cap_seconds | 86400 cap on the quota-scaled active budget |
| hunt.max_age_seconds | 604800 absolute age from creation, including pause/interruption |
| discovery.manual_default_limit | 25 |
| discovery.manual_max_limit | 100 |
| discovery.max_bbox_degrees | 1.0 per axis; finite geographic bounds |
| discovery.max_tags | 100; finite geographic bounds |
| discovery.coverage_ttl_seconds | 2592000 (30 days) |
| discovery.similarity_review_threshold | 0.85 name-token Jaccard, supporting signal also required |
| research.max_pages | 5 |
| research.max_depth | 1 |
| research.timeout_seconds | 10 |
| research.max_attempts | 2 per page |
| research.max_body_bytes | 2097152 decoded |
| research.max_redirects | 3 |
| research.max_text_chars | 20000 per page |
| research.host_interval_seconds | 2 |
| research.host_concurrency | 1 |
| research.robots_ttl_seconds | 86400; inaccessible policy fails closed |
| research.allowed_ports | [80,443]; HTTP/HTTPS only |
| research.trust_env_proxy | false; true requires separate validated policy |
| research.playwright_enabled | false; true requires separate validated policy |
| research.user_agent | Required descriptive application/contact string before fetching |
| providers.verification_ttl_seconds | 604800 (7 days); tuple change invalidates sooner |
| providers.allowance_max_age_seconds | 30; source expiry can be shorter |
| providers.task_timeout_seconds | 120 |
| providers.max_input_bytes | 65536 |
| providers.max_output_bytes | 262144 |
| providers.max_output_repairs | 1; fresh eligibility each time |
| ui.setup_confirmation_ttl_seconds | 300 |
| ui.progress_interval_seconds | 10 |
| ui.page_size | 10 maximum |
| storage.temp_ttl_hours | 24 |
| storage.artifact_ttl_days | 30 |
| storage.export_ttl_days | 7 |
| storage.backup_keep_verified | 7; never delete last verified backup |
| storage.verification_transcript_ttl_days | 30; retain referenced verification manifests |
| mcp.enabled | false; true rejected in initial release |

Local settings also contain `providers.<provider_id>.enabled` (false initially), `providers.<provider_id>.executable_path` (owner-selected absolute local file), `providers.<provider_id>.expected_backend` (verified subscription identifier), `providers.<provider_id>.model_scope` and `providers.<provider_id>.profile_id` (only values actually verified in Phase 0). Adapter discovery can report installation without enablement. No arbitrary argv templates, shell commands, metered API endpoints or authentication secrets are configurable through Discord.

Source settings require `sources.<source_id>.enabled`, `sources.<source_id>.endpoint`, `sources.<source_id>.allowed_hosts`, `sources.<source_id>.permission_url`, `sources.<source_id>.license_url`, `sources.<source_id>.attribution`, `sources.<source_id>.policy_version`, `sources.<source_id>.reviewed_at`, `sources.<source_id>.review_expires_at`, `sources.<source_id>.user_agent`, `sources.<source_id>.allowed_tags`, `sources.<source_id>.min_interval_seconds`, `sources.<source_id>.max_concurrency`, `sources.<source_id>.timeout_seconds`, `sources.<source_id>.max_response_bytes`, `sources.<source_id>.max_attempts`, `sources.<source_id>.max_requests_per_day`. The enabled value defaults to false until policy approval. Overpass caps: interval >=10, concurrency=1, timeout<=30, response<=5242880, attempts<=3. For the owner-approved regional Philippines OSM extract (`sources.philippines_extract`), caps are: `endpoint = "https://download.geofabrik.de/asia/philippines-latest.osm.pbf"`, `allowed_hosts = ["download.geofabrik.de"]`, `min_interval_seconds >= 10`, `max_concurrency = 1`, `timeout_seconds <= 600`, `max_response_bytes <= 1073741824` (1 GiB), `max_attempts <= 3`, and `enabled = false` remains enforced in `load_settings()` while production discovery is kept disabled. Daily budget has no invented public-instance entitlement: owner sets a reviewed positive ceiling allowed by that source's current policy; absent value disables access. Policy expiry likewise requires an explicit reviewed date. The stricter source/local/hunt limit wins; endpoint changes require policy review. Never endpoint-rotate on throttling.

## Effective hunt limits and clock accounting

For quota q, compute blocks = max(1, ceil(q / hunt.quota_block_size)). Effective active seconds equal min(hunt.max_active_cap_seconds, hunt.max_active_seconds * blocks). For each resource R in discovery_requests, candidates, http_requests and ai_tasks, effective_R = min(cap_R, max(base_R, q * factor_R)), using the exact singular keys from the table: discovery_requests_per_lead, candidates_per_lead, http_requests_per_lead and ai_tasks_per_lead. These symbolic R expressions describe a formula, not additional configuration keys. Validate base <= cap, positive factors and block size, and active cap <= absolute age. Snapshot evaluated values at admission.

With defaults and quota 25, effective limits are 18000 active seconds, 604800 absolute-age seconds, 50 discovery requests, 500 candidates, 4000 HTTP requests and 500 AI tasks. The base active setting remains 3600; the explicit D04 scaling supplies additional blocks for larger quotas. Source daily limits and verified subscription capacity remain stricter independent limits. Numerical settings do not guarantee the quota will be met.

Count only RUNNING/PAUSING/STOPPING intervals toward active_milliseconds. PAUSED/INTERRUPTED do not consume active time. Persist active_checkpoint_at and active_lease_expires_at, reserve at most one 30-second lease, and account for a crash using only that reserved interval. Never charge the whole offline period. Persist max_observed_at to detect wall-clock rollback. Resume requires remaining active time, absolute age and resource budgets and never resets any counter; see [17](17-BACKGROUND-JOBS.md).

## SQLite mutable settings

`guild_config.settings_json`: `active_campaign_id` nullable FK validated in services, and `timezone` display preference default Asia/Singapore (storage remains UTC). `role_grants` owns operator role IDs; `command_channels` and `output_destinations` own the exact keys in [07](07-DISCORD-COMMANDS-AND-INTERACTIONS.md) and [06](06-DISCORD-SERVER-ARCHITECTURE.md). `/config` may view safe settings or set `active_campaign_id`, `timezone`, `operator_role_ids`, `command_channel.<canonical_key>`, `output_destination.<output_key>`. Validate current guild membership/resources/permissions and audit revision changes. Settings command never enables an unverified provider or changes local security limits.

Campaign `config_json` schema version 1: `target_categories` (allowlisted source tags), `geography` (country code, finite bounding box/cells), `exclusions`, `provider_id` (nullable for non-AI campaigns; mandatory before AI execution), `service_description` (<=2,000 characters, no executable configuration), `rubric` (version, six weights, qualification_threshold=70, minimum_coverage=0.80, required ratings/gates in [13](13-LEAD-SCORING.md)). Require one explicit active campaign for start without a campaign argument. Campaign edits create new campaign_versions; prior versions and hunt snapshots remain immutable. No campaign setting can relax source permission, SSRF, allowance, manual sending or new-only credit rules.

Hunt `snapshot_json`: schema_version, campaign/version, provider verification tuple reference, rubric, targeting, source policy versions, effective safety limits (both clock ceilings and evaluated resource formulas), initiated actor/guild, and created_at. `counters_json`: seen,new,existing,ambiguous,invalid,researched,unqualified,qualified,discovery_requests,http_requests,ai_tasks. `qualified` mirrors hunt_credits count and qualified_count; discrepancy halts processing for integrity review. Every job `payload_json` includes schema_version, command_key, initiating guild/channel/user IDs, requested record IDs, authorization configuration revision and typed options (RESEARCH includes refresh and analyze; analyze defaults to false); current member roles and mappings are reloaded before dispatch, not trusted from the payload. System publications/reminders retain the originating authorized actor and output purpose; an administrator can explicitly reauthorize recovery if that actor loses access. Job progress includes phase, current candidate/run IDs, completed_units and reserved budget counters, never credentials or raw command strings.

Standalone manual jobs use jobs.manual_max_age_seconds (3600 seconds) as a wall-clock ceiling and do not inherit a paused hunt clock. Their source, HTTP, task and candidate budgets use the resource base values from the table, subject to stricter source policy and explicit discovery limits. They remain bounded. `/discover limit` caps observations, not query-loop retries. Only optional Phase 4b analysis and AI draft jobs share the global AI lock; Phase 4a collection uses HTTP budgets without provider/allowance checks; they do not consume or create a hunt's quota. Finite source policy/daily counters are persisted in discovery_queries/usage-derived aggregates; concurrent checks reserve request slots transactionally before dispatch. HTTP budgets per manual job persist in jobs.progress_json.

## Startup and shutdown

1. Parse environment/TOML, validate every required key/type and restrictive setting; redact diagnostics.
2. Resolve/lock data root, verify free space, open SQLite, verify checksums/schema and guild binding; apply authorized migrations before workers.
3. Reconcile interrupted jobs/hunts and orphan process ownership, validate counters/credits, mark missing artifacts/resources; never enqueue autonomous research.
4. Load adapters disabled unless verification tuple valid; registration alone never executes a task. Restore persistent view routing and then connect Discord.
5. After ready, report degraded resources privately/local logs. Only safe output/reminder recovery can schedule without an explicit hunt command.

Shutdown stops admission, requests cancellation, checkpoints jobs, terminates owned subprocesses, marks unsettled work INTERRUPTED, flushes redacted logs and closes DB. A timeout does not convert unfinished work to SUCCEEDED. Reconnect starts no jobs.

## Coding and review rules

Use typed domain models and explicit enums; parse JSON with bounded sizes and strict schemas. Safe subprocess/URL/SQL helpers are the only allowed boundary APIs. Keep clocks, retries and cancellation injectable. Use transactions around invariants, not just convenient method boundaries. No broad exception swallowing or automatic DB resets. Add dependencies only with documented purpose/license/maintenance considerations and no prohibited service requirements.

Follow the roadmap phase gates and its owner-authorized non-AI path from phases 1–3 through Phase 4a into phase 6. Stop affected work at mandatory blockers; the approved fallback is already a scope decision, so do not request it again. Test critical negative paths, run appropriate suites, record actual commands/results, and update canonical documents plus dependent references together. Do not create tests that simply restate code for low-impact documentation changes; link/schema consistency checks are sufficient here.

## Acceptance

Configuration tests reject unknown keys, missing token/identity, invalid source policy, unsafe endpoint/path, changed guild, nonfinite/negative limits and disabled-feature enablement. Snapshot tests prove edits do not alter running hunts. Startup tests prove no autonomous work on import/start/reconnect/restore. Execute T04/T08/T13/T14/T16 and relevant L01–L04 under [20](20-TESTING-STRATEGY.md) before runtime completion claims.

## Implemented Phase 1 boundary

All 66 static TOML keys are parsed against their default types, positive/finite bounds and cross-field rules. Dynamic provider/source keys are allowlisted and their loaded values immutable. Source/provider enabled=true is rejected because no approved live adapter is wired yet; MCP, browser and proxy enablement also remain unavailable. This phase-specific implementation gate does not revise future adapter or policy requirements.

The offline check-config command permits missing Discord bootstrap values and reports only configured/not-configured booleans. It creates no runtime data and connects to nothing. init-db requires valid guild and owner IDs before storage work, but not a token. The run command requires valid identity and a token before creating runtime storage or connecting to Discord. Unknown variables/keys, invalid identities, unsafe source URLs, unverified feature activation, invalid retries and inconsistent budgets fail with safe messages.

The dedicated data root uses private Windows service-account/SYSTEM ACLs (mode 0700 on POSIX), refuses unrelated contents and symlink/junction paths, and holds an OS-backed deployment lock. Only Windows/Python 3.14.6 is currently tested. Phase 1 starts no scheduler; interrupted-job reconciliation and authorized resume remain Phase 5 work. Opening a database never processes queued jobs. Basic storage tests use real Windows locks/junctions and SQLite WAL backup/restore, not real Discord or AI tasks.

## Implemented Phase 2 boundary

The run command connects only the configured guild command surface. It restores component routing and marks unfinished setup plans partial without resuming provisioning. Setup requires a fresh private preview and actor-bound confirmation. SQLite operations run on a dedicated worker thread; Discord calls run outside transactions. REST calls are bounded to 15 seconds, command synchronization to 60 seconds, and setup work to 180 seconds.

The tracked run-local.example.ps1 template requests the token once through a masked prompt and caches a PSCredential using Windows DPAPI via Export-Clixml under LOCALAPPDATA/MiBoti/credentials, keyed by application ID. Only the same Windows account on the same computer can decrypt the cached secret. The launcher imports it on later runs and restores the prior process environment on exit. Use -ResetToken to delete and replace the cached token. No plaintext token file is written. The operator-specific run-local.ps1 is ignored. Regenerate any token previously shared in chat before use. The six supported environment variables are listed above; no automatic .env loader exists. Phase 2 supports staged operator-role, command-channel and output-destination edits. Campaign and timezone edits remain unavailable until their implementation phases. AI, discovery, research, CRM and backup Discord actions report unavailable without enqueuing work.

## Staged Phase 3 core boundary

The owner authorized offline registry/discovery-core development with Quezon City restaurants and cafes as the first test fixture, and subsequently approved the regional Geofabrik Philippines OpenStreetMap extract ([docs/PHILIPPINES-EXTRACT-PLAN.md](PHILIPPINES-EXTRACT-PLAN.md)) as the Phase 3 discovery source direction. This adds the optional discovery dependency `osmium==4.3.2` (`[project.optional-dependencies] discovery`) and the `[sources.philippines_extract]` TOML policy table (`enabled = false` by default in `config.example.toml`), with no new environment variables or SQL schema migration in `mi_boti.sqlite3`. Provider and public HTTP source `enabled = true` remain rejected in `load_settings()`. Only `sources.philippines_extract.enabled = true` is accepted, with a current valid policy, the exact approved Geofabrik Philippines URL and its single approved host. Missing/corrupt snapshots fail closed at discovery execution. Enabled configuration is reported separately from dataset verification; no source is downloaded on startup. The CLI commands `import-ph-extract` and `verify-ph-extract` run only when explicitly invoked by the operator; bot startup and reconnect never download or import the national extract.

## Website-access review ownership

`research.user_agent` remains a local TOML setting and must contain a descriptive operator/contact reference before collection. Mutable website-access reviews are explicitly administered through /research review/confirmation in business-research and stored under guild_config.settings_json.research_access; they are not arbitrary /config keys. Reviews require business UUID, exact-host URL, same-host permission reference and rationale, expire after seven days and are limited to 64 records. Revoke removes current permission; the audit retains history. Neither a recorded assertion nor robots alone substitutes for inspecting actual access terms.

The runtime enforces configured research.max_pages, timeout_seconds, max_body_bytes, max_redirects, max_text_chars, host_interval_seconds and robots_ttl_seconds within the collector's conservative hard caps (5 pages, 10 seconds/request, 2 MiB, 3 redirects, 20,000 characters, minimum 2-second host spacing, maximum 24-hour robots cache). Depth remains at most one. The initial engine makes one attempt per page, within research.max_attempts, and rejects compressed responses. Total research is capped at 120 seconds/32 requests and jobs.manual_max_age_seconds. No new environment variable, paid API fallback or provider setting is introduced.
