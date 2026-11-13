# 04 — Database schema

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and conventions

This schema is the authoritative table/column contract for [architecture](02-TECHNICAL-ARCHITECTURE.md), [discovery](08-BUSINESS-DISCOVERY.md), [jobs](17-BACKGROUND-JOBS.md), and [CRM](14-CRM-AND-PIPELINE.md). Use numbered SQL migrations, not runtime table creation. Every connection enables foreign keys and a 5-second busy timeout; use WAL with an online-backup procedure. Serialize writes, use short `BEGIN IMMEDIATE` transactions for competing claims, and parameterize every query.

Notation below is an implementable schema DSL: `id` means `TEXT NOT NULL PRIMARY KEY` application UUID; `text`, `int`, `real`, `json`, `utc`, `snowflake` and references are NOT NULL unless suffixed `?`; `ref(table)` means `TEXT REFERENCES table(id) ON DELETE RESTRICT`; `unique(...)` creates a unique constraint; `pk(...)` is a composite primary key. All primary-key columns explicitly require NOT NULL, including TEXT/composite keys; do not rely on SQLite's implicit primary-key null behavior. JSON is TEXT with `CHECK(json_valid(column))` plus application schema validation. UTC is TEXT formatted `YYYY-MM-DDTHH:MM:SS.ffffffZ`; snowflake is canonical positive decimal TEXT validated before write (not a signed 64-bit assumption). Boolean is INTEGER CHECK IN (0,1). Nonnegative counters have CHECK >=0. Enumerations below require SQL CHECK constraints. Do not silently coerce invalid enums or omit stated constraints.

## Deployment, Discord, configuration

```text
schema_migrations(version int PK, checksum text, applied_at utc)
deployment(id int PK CHECK(id=1), guild_id snowflake UNIQUE, created_at utc)
guild_config(id text PK CHECK(id='guild'), guild_id snowflake UNIQUE,
  setup_state text, revision int, settings_json json, updated_at utc)
role_grants(guild_id snowflake, role_id snowflake, permission text,
  created_by snowflake, created_at utc, pk(guild_id,role_id,permission))
discord_resources(id, guild_id snowflake, resource_key text, kind text,
  discord_id snowflake?, parent_resource_id ref(discord_resources)?,
  state text, revision int, unique(guild_id,resource_key), unique(discord_id))
command_channels(command_key text PK, resource_id ref(discord_resources), revision int)
output_destinations(output_key text PK, resource_id ref(discord_resources), revision int)
setup_plans(id, guild_id snowflake, actor_id snowflake, plan_json json,
  plan_hash text, expires_at utc, state text, created_at utc)
setup_steps(id, plan_id ref(setup_plans), step_key text, state text,
  discord_id snowflake?, error_code text?, updated_at utc, unique(plan_id,step_key))
panels(id, resource_id ref(discord_resources), panel_key text, message_id snowflake?,
  revision int, state text, unique(resource_id,panel_key))
campaigns(id, name text, state text, current_version int, created_by snowflake,
  created_at utc, updated_at utc)
campaign_versions(campaign_id ref(campaigns), version int, config_json json,
  created_by snowflake, created_at utc, pk(campaign_id,version))
```

`guild_config.setup_state`: UNCONFIGURED/PARTIAL/READY. Resource kind CATEGORY/TEXT; state ACTIVE/MISSING/UNCERTAIN. Plans PREVIEW/CONFIRMED/APPLYING/COMPLETED/PARTIAL/EXPIRED; steps PENDING/APPLYING/COMPLETED/FAILED/UNCERTAIN. Panel state ACTIVE/MISSING/UNCERTAIN. Campaign state ACTIVE/ARCHIVED. Role permission is OPERATOR; administrator authority comes from live Discord. All guild IDs must match `deployment`; services enforce singleton binding. READY requires all command/output mappings, active resources, and published mandatory panels. Mapping changes increment revision and invalidate outstanding setup plans.

## Provider and execution records

```text
provider_verifications(id, provider_id text, cli_version text, executable_hash text,
  adapter_version text, status text, tested_at utc, expires_at utc,
  capabilities_json json, evidence_path text?, reason_code text?)
allowance_checks(id, provider_id text, verification_id ref(provider_verifications),
  account_fingerprint text, observed_at utc, expires_at utc, state text,
  windows_json json, source_kind text, reason_code text?)
ai_executions(id, job_id ref(jobs), provider_id text,
  allowance_check_id ref(allowance_checks), task_kind text, started_at utc,
  finished_at utc?, state text, usage_json json?, error_code text?)
```

Verification status VERIFIED/BLOCKED/EXPIRED. Allowance state AVAILABLE/EXHAUSTED/UNKNOWN; execution state RUNNING/SUCCEEDED/FAILED/CANCELLED/INTERRUPTED. Fingerprints are salted local account identifiers, not credentials. `windows_json` follows [10](10-AI-PROVIDER-INTEGRATION.md). SQL migrations create referenced tables in valid dependency order; the display grouping is not migration execution order. Cyclic job/hunt references are resolved by creating both tables before transactions use them.

## Registry, discovery, evidence

```text
businesses(id, name text, normalized_name text, address_json json?,
  normalized_address text?, country_code text?, parent_id ref(businesses)?,
  entity_kind text, disposition text, origin_job_id ref(jobs),
  origin_hunt_id ref(hunts)?, created_at utc, updated_at utc, revision int)
business_identifiers(id, business_id ref(businesses), kind text, namespace text,
  value text, strength text, created_at utc,
  unique(business_id,kind,namespace,value))
identity_claims(claim_key text PK, business_id ref(businesses), created_at utc)
business_contacts(id, business_id ref(businesses), kind text, value text,
  normalized_value text, evidence_id ref(evidence), created_at utc,
  unique(business_id,kind,normalized_value))
discovery_queries(id, job_id ref(jobs), campaign_id ref(campaigns), hunt_id ref(hunts)?,
  source text, query_hash text, policy_version text, geographic_cell text,
  request_json json, state text, attempts int, result_count int,
  started_at utc, finished_at utc?, error_code text?)
coverage_cells(campaign_id ref(campaigns), source text, geographic_cell text,
  query_hash text, last_query_id ref(discovery_queries), observed_at utc,
  state text, pk(campaign_id,source,geographic_cell,query_hash))
candidates(id, query_id ref(discovery_queries), observation_key text,
  observation_json json, state text, business_id ref(businesses)?,
  resolution_json json?, created_at utc, unique(query_id,observation_key))
identity_reviews(id, candidate_id ref(candidates) UNIQUE, matches_json json,
  state text, resolution text?, actor_id snowflake?, resolved_at utc?)
business_events(id, business_id ref(businesses), actor_id snowflake?,
  event_kind text, payload_json json, created_at utc)
research_runs(id, business_id ref(businesses), job_id ref(jobs),
  kind text, state text, started_at utc, finished_at utc?, limitations_json json)
artifacts(id, relative_path text UNIQUE, sha256 text, bytes int,
  media_type text, created_at utc, expires_at utc?, state text)
evidence(id, business_id ref(businesses), research_run_id ref(research_runs)?,
  candidate_id ref(candidates)?, source_url text?, source_identifier text?,
  observed_at utc, extracted_fact text, confidence real,
  limitations_json json, artifact_id ref(artifacts)?, policy_version text)
findings(id, research_run_id ref(research_runs), kind text, statement text,
  confidence real, limitations_json json, created_at utc)
finding_evidence(finding_id ref(findings), evidence_id ref(evidence),
  pk(finding_id,evidence_id))
scores(id, business_id ref(businesses), research_run_id ref(research_runs),
  campaign_id ref(campaigns), campaign_version int, rubric_version text,
  components_json json, total real, qualification text, rationale text,
  created_at utc)
```

Entity kind BUSINESS/PARENT/BRANCH; no self-parent or cyclic parent graph (service validation inside transaction). Disposition PENDING/QUALIFIED/UNQUALIFIED/REJECTED/ARCHIVED; contacted belongs to CRM stage, keeping identity regardless. Identifier kind SOURCE/DOMAIN/NAME_ADDRESS/PHONE/EMAIL; strength STRONG/SUPPORTING. `identity_claims` owns only strong keys; supporting domains/phones are nonunique across businesses. Stable source IDs get `source:<namespace>:<value>` claims. A full branch-specific canonical name/address gets a claim only after exact normalization with no ambiguity; do not use a domain-only unique claim. Alias claims are kept when records change.

Queries QUEUED/RUNNING/SUCCEEDED/PARTIAL/FAILED/CANCELLED; coverage FRESH/EXHAUSTED/PARTIAL. Candidates NEW/EXISTING/AMBIGUOUS/INVALID/RESOLVED_NEW/RESOLVED_EXISTING; reviews OPEN/RESOLVED. Research kind INITIAL/REFRESH/DRAFT_CONTEXT; state QUEUED/RUNNING/SUCCEEDED/PARTIAL/FAILED/CANCELLED/INTERRUPTED. Artifacts PRESENT/PURGED/MISSING. Findings FACT/INFERENCE/UNKNOWN; score qualification QUALIFIED/UNQUALIFIED/REVIEW_REQUIRED. Confidence CHECK 0<=value<=1; scores CHECK 0<=total<=100. Evidence CHECK at least one of source_url/source_identifier nonnull, and at least one origin research_run/candidate nonnull. Services validate same-business evidence links and FACT/INFERENCE evidence cardinality. A composite FK `(campaign_id,campaign_version)` references campaign_versions. Preserve observations even if the business is invalid or duplicate.

## Hunts, jobs, CRM and audit

```text
hunts(id, campaign_id ref(campaigns), campaign_version int,
  snapshot_json json, provider_id text, initiated_by snowflake, quota int,
  qualified_count int, state text, stop_reason text?, counters_json json,
  active_milliseconds int, active_checkpoint_at utc?, active_lease_expires_at utc?,
  max_observed_at utc, created_at utc, updated_at utc, revision int)
jobs(id, kind text, payload_json json, idempotency_key text UNIQUE,
  hunt_id ref(hunts)?, business_id ref(businesses)?, actor_id snowflake,
  state text, attempt int, max_attempts int, progress_json json,
  lease_token text?, lease_expires_at utc?, cancel_requested int,
  next_attempt_at utc?, created_at utc, updated_at utc, error_code text?)
hunt_credits(business_id ref(businesses) PK, hunt_id ref(hunts),
  lead_id ref(leads) UNIQUE, score_id ref(scores), created_at utc)
leads(id, business_id ref(businesses) UNIQUE, current_score_id ref(scores)?,
  qualification_kind text,
  stage text, revision int, created_at utc, updated_at utc)
lead_events(id, lead_id ref(leads), actor_id snowflake, kind text,
  payload_json json, created_at utc)
lead_notes(id, lead_id ref(leads), actor_id snowflake, body text,
  created_at utc, supersedes_id ref(lead_notes)?)
outreach_drafts(id, lead_id ref(leads), version int, body text, state text,
  evidence_ids_json json, created_by snowflake, approved_by snowflake?,
  approved_at utc?, manual_sent_at utc?, manual_sent_by snowflake?,
  created_at utc, unique(lead_id,version))
followups(id, lead_id ref(leads), due_at utc, note text, state text,
  created_by snowflake, revision int, created_at utc, completed_at utc?)
publications(id, job_id ref(jobs) UNIQUE, resource_id ref(discord_resources),
  subject_kind text, subject_id text, revision int, marker text? UNIQUE,
  message_id snowflake?, state text, updated_at utc,
  unique(resource_id,subject_kind,subject_id,revision))
audit_events(id, correlation_id text, actor_id snowflake?, action text,
  entity_kind text, entity_id text?, outcome text, redacted_details_json json,
  created_at utc)
backups(id, artifact_id ref(artifacts), manifest_json json?, state text,
  requested_by snowflake, created_at utc, verified_at utc?)
```

Hunt/job enums are exactly [17](17-BACKGROUND-JOBS.md). Add `CHECK(quota>0 AND qualified_count>=0 AND qualified_count<=quota)`, campaign-version composite FK, and a partial UNIQUE index on constant `(1)` where hunt state IN ('RUNNING','PAUSING','PAUSED','STOPPING','INTERRUPTED'). Lead qualification_kind is MANUAL/AUTOMATIC. AUTOMATIC requires a nonnull valid current_score_id; MANUAL allows null and requires a named actor, public evidence references and review rationale in lead_events. A later automatic score does not erase the manual-origin history. Lead stages: NEW/REVIEWING/READY/CONTACTED/FOLLOW_UP/WON/LOST/ARCHIVED. Draft states DRAFT/APPROVED/REJECTED/MANUALLY_SENT. Follow-ups PENDING/NOTIFIED/DONE/CANCELLED. Publications PENDING/SENT/UNCERTAIN/FAILED; UNCERTAIN and nonnull marker are post-MVP delivery features. MVP uncertain sends use FAILED with DELIVERY_REVIEW_REQUIRED and cannot auto-retry. Backups CREATING/VERIFIED/FAILED; manifest_json is nullable for an MVP basic verified copy and populated for post-MVP expanded verification manifests. Artifact hash/size and verified_at still attest the basic copy checks. Approval/sending fields require corresponding states and named actors; manual send requires prior approval. Job cancel_requested is boolean. Counters are bounded validated integers. Hunt active_milliseconds is nonnegative and only accounts for RUNNING/PAUSING/STOPPING, including a bounded crash-reserved lease charge; active_checkpoint_at/active_lease_expires_at track the open accounting lease and max_observed_at prevents wall-clock rollback from extending absolute age. Effective clock ceilings and quota-derived resource caps are immutable fields of snapshot_json, as defined in doc 23.

## Indexes, migrations and transactions

Index `business_identifiers(kind,namespace,value)`, businesses(normalized_name,normalized_address), businesses(parent_id), candidates(state), discovery_queries(source,query_hash,started_at), evidence(business_id,observed_at), jobs(state,next_attempt_at), jobs(hunt_id,state), findings(research_run_id), scores(business_id,created_at), leads(stage), followups(state,due_at), audit_events(created_at), and each otherwise unindexed child FK used for joins. No raw contact full-text dump indexes.

Migration runner backs up existing DB, verifies prior checksums, acquires exclusive maintenance access, applies one migration transaction, records checksum/version, and runs foreign_key_check. Failure rolls back that migration and prevents startup; never reset production DB. A newer schema is rejected. Test both empty creation and upgrade with preserved fixtures.

Identity transaction: claim job lease → resolve strong/supporting signals → insert business with immutable origin fields and all strong claims → commit. A unique-key race reloads the winning business; it does not retry as a different new business. Ambiguous results persist candidate/review only and withhold research. Resolution later does not retroactively grant quota for that candidate.

Qualification transaction: validate job lease, RUNNING hunt, origin_hunt_id equality, origin_job_id belonging to this hunt, INITIAL research, unambiguous identity, valid score and remaining quota → insert/update lead → insert globally unique hunt_credit → increment qualified_count once → enqueue publication → mark COMPLETED if at quota → commit. On conflict roll back credit/count and read existing state. Manual qualification may create/update leads with qualification_kind=MANUAL and current_score_id=null, requiring named review, cited public evidence and a rationale; it never creates credits. Automatic qualification sets qualification_kind=AUTOMATIC and a valid score reference. hunt_credits must reference an AUTOMATIC lead and a QUALIFIED score belonging to that business/hunt campaign snapshot. Recompute counts from credits during integrity checks; discrepancy halts the hunt rather than guessing.

## Acceptance

T04 migrates empty/old DBs and rejects tampering; T06 races identity claims; T07 races quota commits at remaining=1; T11 validates evidence FKs; T12 persists CRM; T16 restores backups and passes integrity/foreign-key checks. No normal delete cascades may erase identity, credits, or audit history. See [testing](20-TESTING-STRATEGY.md).

## Phase 1 implementation notes

The static 0001_initial.sql migration and packaged checksum manifest implement all 41 tables using SQLite STRICT tables. Nullable JSON accepts SQL NULL; present JSON is validated for object/array shape. Primary keys reject NULL. State enums, snowflake text, timestamp shape, confidence/score ranges, approval/sending dependencies, one open hunt and immutable business origin fields are constrained. business_contacts.kind is PHONE/EMAIL/WEBSITE. Parent-cycle detection, evidence semantics, deduplication resolution and atomic qualification/credit services remain later-phase work; schema tests do not establish those workflows.

The runner validates packaged/applied checksums, rejects unknown/newer histories, makes a verified copy before upgrading an existing database, applies each migration in its own explicit transaction without executescript, checks foreign keys, and updates user_version atomically. Phase 2 must run blocking database work outside Discord handlers/the event loop. The current backup code provides local verified-copy primitives; the Discord backup workflow and its application backup records are not yet implemented.
