-- Phase 1 schema. Apply only through the checksummed migration runner.


CREATE TABLE schema_migrations (
    version INTEGER NOT NULL PRIMARY KEY CHECK (version>=0) CHECK (version>=1),
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL CHECK (length(applied_at)=27 AND applied_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE deployment (
    id INTEGER NOT NULL PRIMARY KEY CHECK(id=1) CHECK (id>=0),
    guild_id TEXT NOT NULL UNIQUE CHECK (length(guild_id) BETWEEN 1 AND 20 AND guild_id NOT GLOB '*[^0-9]*' AND substr(guild_id,1,1) BETWEEN '1' AND '9' AND (length(guild_id)<20 OR guild_id<='18446744073709551615')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE guild_config (
    id TEXT NOT NULL PRIMARY KEY CHECK(id='guild'),
    guild_id TEXT NOT NULL UNIQUE CHECK (length(guild_id) BETWEEN 1 AND 20 AND guild_id NOT GLOB '*[^0-9]*' AND substr(guild_id,1,1) BETWEEN '1' AND '9' AND (length(guild_id)<20 OR guild_id<='18446744073709551615')),
    setup_state TEXT NOT NULL CHECK (setup_state IN ('UNCONFIGURED','PARTIAL','READY')),
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    settings_json TEXT NOT NULL CHECK (CASE WHEN settings_json IS NULL THEN 1 WHEN json_valid(settings_json) THEN json_type(settings_json)='object' ELSE 0 END),
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE role_grants (
    guild_id TEXT NOT NULL CHECK (length(guild_id) BETWEEN 1 AND 20 AND guild_id NOT GLOB '*[^0-9]*' AND substr(guild_id,1,1) BETWEEN '1' AND '9' AND (length(guild_id)<20 OR guild_id<='18446744073709551615')),
    role_id TEXT NOT NULL CHECK (length(role_id) BETWEEN 1 AND 20 AND role_id NOT GLOB '*[^0-9]*' AND substr(role_id,1,1) BETWEEN '1' AND '9' AND (length(role_id)<20 OR role_id<='18446744073709551615')),
    permission TEXT NOT NULL CHECK (permission IN ('OPERATOR')),
    created_by TEXT NOT NULL CHECK (length(created_by) BETWEEN 1 AND 20 AND created_by NOT GLOB '*[^0-9]*' AND substr(created_by,1,1) BETWEEN '1' AND '9' AND (length(created_by)<20 OR created_by<='18446744073709551615')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    PRIMARY KEY (guild_id,role_id,permission)
) STRICT;


CREATE TABLE discord_resources (
    id TEXT NOT NULL PRIMARY KEY,
    guild_id TEXT NOT NULL CHECK (length(guild_id) BETWEEN 1 AND 20 AND guild_id NOT GLOB '*[^0-9]*' AND substr(guild_id,1,1) BETWEEN '1' AND '9' AND (length(guild_id)<20 OR guild_id<='18446744073709551615')),
    resource_key TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('CATEGORY','TEXT')),
    discord_id TEXT CHECK (length(discord_id) BETWEEN 1 AND 20 AND discord_id NOT GLOB '*[^0-9]*' AND substr(discord_id,1,1) BETWEEN '1' AND '9' AND (length(discord_id)<20 OR discord_id<='18446744073709551615')),
    parent_resource_id TEXT REFERENCES discord_resources(id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('ACTIVE','MISSING','UNCERTAIN')),
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    UNIQUE (guild_id,resource_key),
    UNIQUE (discord_id)
) STRICT;


CREATE TABLE command_channels (
    command_key TEXT NOT NULL PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES discord_resources(id) ON DELETE RESTRICT,
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1)
) STRICT;


CREATE TABLE output_destinations (
    output_key TEXT NOT NULL PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES discord_resources(id) ON DELETE RESTRICT,
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1)
) STRICT;


CREATE TABLE setup_plans (
    id TEXT NOT NULL PRIMARY KEY,
    guild_id TEXT NOT NULL CHECK (length(guild_id) BETWEEN 1 AND 20 AND guild_id NOT GLOB '*[^0-9]*' AND substr(guild_id,1,1) BETWEEN '1' AND '9' AND (length(guild_id)<20 OR guild_id<='18446744073709551615')),
    actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 20 AND actor_id NOT GLOB '*[^0-9]*' AND substr(actor_id,1,1) BETWEEN '1' AND '9' AND (length(actor_id)<20 OR actor_id<='18446744073709551615')),
    plan_json TEXT NOT NULL CHECK (CASE WHEN plan_json IS NULL THEN 1 WHEN json_valid(plan_json) THEN json_type(plan_json)='object' ELSE 0 END),
    plan_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL CHECK (length(expires_at)=27 AND expires_at GLOB '????-??-??T??:??:??.??????Z'),
    state TEXT NOT NULL CHECK (state IN ('PREVIEW','CONFIRMED','APPLYING','COMPLETED','PARTIAL','EXPIRED')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE setup_steps (
    id TEXT NOT NULL PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES setup_plans(id) ON DELETE RESTRICT,
    step_key TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING','APPLYING','COMPLETED','FAILED','UNCERTAIN')),
    discord_id TEXT CHECK (length(discord_id) BETWEEN 1 AND 20 AND discord_id NOT GLOB '*[^0-9]*' AND substr(discord_id,1,1) BETWEEN '1' AND '9' AND (length(discord_id)<20 OR discord_id<='18446744073709551615')),
    error_code TEXT,
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z'),
    UNIQUE (plan_id,step_key)
) STRICT;


CREATE TABLE panels (
    id TEXT NOT NULL PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES discord_resources(id) ON DELETE RESTRICT,
    panel_key TEXT NOT NULL,
    message_id TEXT CHECK (length(message_id) BETWEEN 1 AND 20 AND message_id NOT GLOB '*[^0-9]*' AND substr(message_id,1,1) BETWEEN '1' AND '9' AND (length(message_id)<20 OR message_id<='18446744073709551615')),
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    state TEXT NOT NULL CHECK (state IN ('ACTIVE','MISSING','UNCERTAIN')),
    UNIQUE (resource_id,panel_key)
) STRICT;


CREATE TABLE campaigns (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('ACTIVE','ARCHIVED')),
    current_version INTEGER NOT NULL CHECK (current_version>=0) CHECK (current_version>=1),
    created_by TEXT NOT NULL CHECK (length(created_by) BETWEEN 1 AND 20 AND created_by NOT GLOB '*[^0-9]*' AND substr(created_by,1,1) BETWEEN '1' AND '9' AND (length(created_by)<20 OR created_by<='18446744073709551615')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE campaign_versions (
    campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version>=0) CHECK (version>=1),
    config_json TEXT NOT NULL CHECK (CASE WHEN config_json IS NULL THEN 1 WHEN json_valid(config_json) THEN json_type(config_json)='object' ELSE 0 END),
    created_by TEXT NOT NULL CHECK (length(created_by) BETWEEN 1 AND 20 AND created_by NOT GLOB '*[^0-9]*' AND substr(created_by,1,1) BETWEEN '1' AND '9' AND (length(created_by)<20 OR created_by<='18446744073709551615')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    PRIMARY KEY (campaign_id,version)
) STRICT;


CREATE TABLE provider_verifications (
    id TEXT NOT NULL PRIMARY KEY,
    provider_id TEXT NOT NULL,
    cli_version TEXT NOT NULL,
    executable_hash TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('VERIFIED','BLOCKED','EXPIRED')),
    tested_at TEXT NOT NULL CHECK (length(tested_at)=27 AND tested_at GLOB '????-??-??T??:??:??.??????Z'),
    expires_at TEXT NOT NULL CHECK (length(expires_at)=27 AND expires_at GLOB '????-??-??T??:??:??.??????Z'),
    capabilities_json TEXT NOT NULL CHECK (CASE WHEN capabilities_json IS NULL THEN 1 WHEN json_valid(capabilities_json) THEN json_type(capabilities_json)='object' ELSE 0 END),
    evidence_path TEXT,
    reason_code TEXT
) STRICT;


CREATE TABLE allowance_checks (
    id TEXT NOT NULL PRIMARY KEY,
    provider_id TEXT NOT NULL,
    verification_id TEXT NOT NULL REFERENCES provider_verifications(id) ON DELETE RESTRICT,
    account_fingerprint TEXT NOT NULL,
    observed_at TEXT NOT NULL CHECK (length(observed_at)=27 AND observed_at GLOB '????-??-??T??:??:??.??????Z'),
    expires_at TEXT NOT NULL CHECK (length(expires_at)=27 AND expires_at GLOB '????-??-??T??:??:??.??????Z'),
    state TEXT NOT NULL CHECK (state IN ('AVAILABLE','EXHAUSTED','UNKNOWN')),
    windows_json TEXT NOT NULL CHECK (CASE WHEN windows_json IS NULL THEN 1 WHEN json_valid(windows_json) THEN json_type(windows_json)='array' ELSE 0 END),
    source_kind TEXT NOT NULL,
    reason_code TEXT
) STRICT;


CREATE TABLE ai_executions (
    id TEXT NOT NULL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    provider_id TEXT NOT NULL,
    allowance_check_id TEXT NOT NULL REFERENCES allowance_checks(id) ON DELETE RESTRICT,
    task_kind TEXT NOT NULL CHECK (task_kind IN ('QUALIFY','DRAFT')),
    started_at TEXT NOT NULL CHECK (length(started_at)=27 AND started_at GLOB '????-??-??T??:??:??.??????Z'),
    finished_at TEXT CHECK (length(finished_at)=27 AND finished_at GLOB '????-??-??T??:??:??.??????Z'),
    state TEXT NOT NULL CHECK (state IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','INTERRUPTED')),
    usage_json TEXT CHECK (CASE WHEN usage_json IS NULL THEN 1 WHEN json_valid(usage_json) THEN json_type(usage_json)='object' ELSE 0 END),
    error_code TEXT
) STRICT;


CREATE TABLE businesses (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    address_json TEXT CHECK (CASE WHEN address_json IS NULL THEN 1 WHEN json_valid(address_json) THEN json_type(address_json)='object' ELSE 0 END),
    normalized_address TEXT,
    country_code TEXT,
    parent_id TEXT REFERENCES businesses(id) ON DELETE RESTRICT,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('BUSINESS','PARENT','BRANCH')),
    disposition TEXT NOT NULL CHECK (disposition IN ('PENDING','QUALIFIED','UNQUALIFIED','REJECTED','ARCHIVED')),
    origin_job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    origin_hunt_id TEXT REFERENCES hunts(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z'),
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    CHECK (parent_id IS NULL OR parent_id != id),
    CHECK (length(trim(name))>0),
    CHECK (length(trim(normalized_name))>0)
) STRICT;


CREATE TABLE business_identifiers (
    id TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('SOURCE','DOMAIN','NAME_ADDRESS','PHONE','EMAIL')),
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    strength TEXT NOT NULL CHECK (strength IN ('STRONG','SUPPORTING')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    UNIQUE (business_id,kind,namespace,value)
) STRICT;


CREATE TABLE identity_claims (
    claim_key TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE business_contacts (
    id TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('PHONE','EMAIL','WEBSITE')),
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    UNIQUE (business_id,kind,normalized_value)
) STRICT;


CREATE TABLE discovery_queries (
    id TEXT NOT NULL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
    hunt_id TEXT REFERENCES hunts(id) ON DELETE RESTRICT,
    source TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    geographic_cell TEXT NOT NULL,
    request_json TEXT NOT NULL CHECK (CASE WHEN request_json IS NULL THEN 1 WHEN json_valid(request_json) THEN json_type(request_json)='object' ELSE 0 END),
    state TEXT NOT NULL CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','PARTIAL','FAILED','CANCELLED')),
    attempts INTEGER NOT NULL CHECK (attempts>=0),
    result_count INTEGER NOT NULL CHECK (result_count>=0),
    started_at TEXT NOT NULL CHECK (length(started_at)=27 AND started_at GLOB '????-??-??T??:??:??.??????Z'),
    finished_at TEXT CHECK (length(finished_at)=27 AND finished_at GLOB '????-??-??T??:??:??.??????Z'),
    error_code TEXT
) STRICT;


CREATE TABLE coverage_cells (
    campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
    source TEXT NOT NULL,
    geographic_cell TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    last_query_id TEXT NOT NULL REFERENCES discovery_queries(id) ON DELETE RESTRICT,
    observed_at TEXT NOT NULL CHECK (length(observed_at)=27 AND observed_at GLOB '????-??-??T??:??:??.??????Z'),
    state TEXT NOT NULL CHECK (state IN ('FRESH','EXHAUSTED','PARTIAL')),
    PRIMARY KEY (campaign_id,source,geographic_cell,query_hash)
) STRICT;


CREATE TABLE candidates (
    id TEXT NOT NULL PRIMARY KEY,
    query_id TEXT NOT NULL REFERENCES discovery_queries(id) ON DELETE RESTRICT,
    observation_key TEXT NOT NULL,
    observation_json TEXT NOT NULL CHECK (CASE WHEN observation_json IS NULL THEN 1 WHEN json_valid(observation_json) THEN json_type(observation_json)='object' ELSE 0 END),
    state TEXT NOT NULL CHECK (state IN ('NEW','EXISTING','AMBIGUOUS','INVALID','RESOLVED_NEW','RESOLVED_EXISTING')),
    business_id TEXT REFERENCES businesses(id) ON DELETE RESTRICT,
    resolution_json TEXT CHECK (CASE WHEN resolution_json IS NULL THEN 1 WHEN json_valid(resolution_json) THEN json_type(resolution_json)='object' ELSE 0 END),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    UNIQUE (query_id,observation_key)
) STRICT;


CREATE TABLE identity_reviews (
    id TEXT NOT NULL PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE RESTRICT UNIQUE,
    matches_json TEXT NOT NULL CHECK (CASE WHEN matches_json IS NULL THEN 1 WHEN json_valid(matches_json) THEN json_type(matches_json)='array' ELSE 0 END),
    state TEXT NOT NULL CHECK (state IN ('OPEN','RESOLVED')),
    resolution TEXT,
    actor_id TEXT CHECK (length(actor_id) BETWEEN 1 AND 20 AND actor_id NOT GLOB '*[^0-9]*' AND substr(actor_id,1,1) BETWEEN '1' AND '9' AND (length(actor_id)<20 OR actor_id<='18446744073709551615')),
    resolved_at TEXT CHECK (length(resolved_at)=27 AND resolved_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE business_events (
    id TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
    actor_id TEXT CHECK (length(actor_id) BETWEEN 1 AND 20 AND actor_id NOT GLOB '*[^0-9]*' AND substr(actor_id,1,1) BETWEEN '1' AND '9' AND (length(actor_id)<20 OR actor_id<='18446744073709551615')),
    event_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (CASE WHEN payload_json IS NULL THEN 1 WHEN json_valid(payload_json) THEN json_type(payload_json)='object' ELSE 0 END),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE research_runs (
    id TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('INITIAL','REFRESH','DRAFT_CONTEXT')),
    state TEXT NOT NULL CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','PARTIAL','FAILED','CANCELLED','INTERRUPTED')),
    started_at TEXT NOT NULL CHECK (length(started_at)=27 AND started_at GLOB '????-??-??T??:??:??.??????Z'),
    finished_at TEXT CHECK (length(finished_at)=27 AND finished_at GLOB '????-??-??T??:??:??.??????Z'),
    limitations_json TEXT NOT NULL CHECK (CASE WHEN limitations_json IS NULL THEN 1 WHEN json_valid(limitations_json) THEN json_type(limitations_json)='array' ELSE 0 END)
) STRICT;


CREATE TABLE artifacts (
    id TEXT NOT NULL PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL CHECK (bytes>=0),
    media_type TEXT NOT NULL,
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    expires_at TEXT CHECK (length(expires_at)=27 AND expires_at GLOB '????-??-??T??:??:??.??????Z'),
    state TEXT NOT NULL CHECK (state IN ('PRESENT','PURGED','MISSING'))
) STRICT;


CREATE TABLE evidence (
    id TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
    research_run_id TEXT REFERENCES research_runs(id) ON DELETE RESTRICT,
    candidate_id TEXT REFERENCES candidates(id) ON DELETE RESTRICT,
    source_url TEXT,
    source_identifier TEXT,
    observed_at TEXT NOT NULL CHECK (length(observed_at)=27 AND observed_at GLOB '????-??-??T??:??:??.??????Z'),
    extracted_fact TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    limitations_json TEXT NOT NULL CHECK (CASE WHEN limitations_json IS NULL THEN 1 WHEN json_valid(limitations_json) THEN json_type(limitations_json)='array' ELSE 0 END),
    artifact_id TEXT REFERENCES artifacts(id) ON DELETE RESTRICT,
    policy_version TEXT NOT NULL,
    CHECK (source_url IS NOT NULL OR source_identifier IS NOT NULL),
    CHECK (research_run_id IS NOT NULL OR candidate_id IS NOT NULL),
    CHECK (source_url IS NULL OR length(trim(source_url))>0),
    CHECK (source_identifier IS NULL OR length(trim(source_identifier))>0)
) STRICT;


CREATE TABLE findings (
    id TEXT NOT NULL PRIMARY KEY,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('FACT','INFERENCE','UNKNOWN')),
    statement TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    limitations_json TEXT NOT NULL CHECK (CASE WHEN limitations_json IS NULL THEN 1 WHEN json_valid(limitations_json) THEN json_type(limitations_json)='array' ELSE 0 END),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE finding_evidence (
    finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE RESTRICT,
    evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    PRIMARY KEY (finding_id,evidence_id)
) STRICT;


CREATE TABLE scores (
    id TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
    campaign_version INTEGER NOT NULL CHECK (campaign_version>=0) CHECK (campaign_version>=1),
    rubric_version TEXT NOT NULL,
    components_json TEXT NOT NULL CHECK (CASE WHEN components_json IS NULL THEN 1 WHEN json_valid(components_json) THEN json_type(components_json)='object' ELSE 0 END),
    total REAL NOT NULL CHECK (total BETWEEN 0 AND 100),
    qualification TEXT NOT NULL CHECK (qualification IN ('QUALIFIED','UNQUALIFIED','REVIEW_REQUIRED')),
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    FOREIGN KEY (campaign_id,campaign_version) REFERENCES campaign_versions(campaign_id,version) ON DELETE RESTRICT
) STRICT;


CREATE TABLE hunts (
    id TEXT NOT NULL PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
    campaign_version INTEGER NOT NULL CHECK (campaign_version>=0) CHECK (campaign_version>=1),
    snapshot_json TEXT NOT NULL CHECK (CASE WHEN snapshot_json IS NULL THEN 1 WHEN json_valid(snapshot_json) THEN json_type(snapshot_json)='object' ELSE 0 END),
    provider_id TEXT NOT NULL,
    initiated_by TEXT NOT NULL CHECK (length(initiated_by) BETWEEN 1 AND 20 AND initiated_by NOT GLOB '*[^0-9]*' AND substr(initiated_by,1,1) BETWEEN '1' AND '9' AND (length(initiated_by)<20 OR initiated_by<='18446744073709551615')),
    quota INTEGER NOT NULL CHECK (quota>=0),
    qualified_count INTEGER NOT NULL CHECK (qualified_count>=0),
    state TEXT NOT NULL CHECK (state IN ('RUNNING','PAUSING','PAUSED','STOPPING','INTERRUPTED','COMPLETED','STOPPED','FAILED')),
    stop_reason TEXT CHECK (stop_reason IN ('QUOTA_REACHED','OPERATOR_STOP','SOURCE_EXHAUSTED','SOURCE_UNAVAILABLE','ALLOWANCE_EXHAUSTED','ALLOWANCE_UNKNOWN','AUTH_REQUIRED','VERIFICATION_INVALID','SAFETY_LIMIT','CRITICAL_ERROR','AUTHORIZATION_LOST','RESTART_INTERRUPTION','CANCEL_FAILED')),
    counters_json TEXT NOT NULL CHECK (CASE WHEN counters_json IS NULL THEN 1 WHEN json_valid(counters_json) THEN json_type(counters_json)='object' ELSE 0 END),
    active_milliseconds INTEGER NOT NULL CHECK (active_milliseconds>=0),
    active_checkpoint_at TEXT CHECK (length(active_checkpoint_at)=27 AND active_checkpoint_at GLOB '????-??-??T??:??:??.??????Z'),
    active_lease_expires_at TEXT CHECK (length(active_lease_expires_at)=27 AND active_lease_expires_at GLOB '????-??-??T??:??:??.??????Z'),
    max_observed_at TEXT NOT NULL CHECK (length(max_observed_at)=27 AND max_observed_at GLOB '????-??-??T??:??:??.??????Z'),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z'),
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    CHECK (quota>0 AND qualified_count<=quota),
    CHECK (state NOT IN ('COMPLETED','STOPPED','FAILED','INTERRUPTED') OR stop_reason IS NOT NULL),
    FOREIGN KEY (campaign_id,campaign_version) REFERENCES campaign_versions(campaign_id,version) ON DELETE RESTRICT
) STRICT;


CREATE TABLE jobs (
    id TEXT NOT NULL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('DISCOVER','RESEARCH','QUALIFY','DRAFT','PUBLISH','REMINDER','BACKUP','EXPORT','VERIFY_PROVIDER')),
    payload_json TEXT NOT NULL CHECK (CASE WHEN payload_json IS NULL THEN 1 WHEN json_valid(payload_json) THEN json_type(payload_json)='object' ELSE 0 END),
    idempotency_key TEXT NOT NULL UNIQUE,
    hunt_id TEXT REFERENCES hunts(id) ON DELETE RESTRICT,
    business_id TEXT REFERENCES businesses(id) ON DELETE RESTRICT,
    actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 20 AND actor_id NOT GLOB '*[^0-9]*' AND substr(actor_id,1,1) BETWEEN '1' AND '9' AND (length(actor_id)<20 OR actor_id<='18446744073709551615')),
    state TEXT NOT NULL CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','RETRY_WAIT','INTERRUPTED')),
    attempt INTEGER NOT NULL CHECK (attempt>=0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts>=0),
    progress_json TEXT NOT NULL CHECK (CASE WHEN progress_json IS NULL THEN 1 WHEN json_valid(progress_json) THEN json_type(progress_json)='object' ELSE 0 END),
    lease_token TEXT,
    lease_expires_at TEXT CHECK (length(lease_expires_at)=27 AND lease_expires_at GLOB '????-??-??T??:??:??.??????Z'),
    cancel_requested INTEGER NOT NULL CHECK (cancel_requested>=0),
    next_attempt_at TEXT CHECK (length(next_attempt_at)=27 AND next_attempt_at GLOB '????-??-??T??:??:??.??????Z'),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z'),
    error_code TEXT,
    CHECK (cancel_requested IN (0,1)),
    CHECK (max_attempts BETWEEN 1 AND 3),
    CHECK (attempt<=max_attempts),
    CHECK (state != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL))
) STRICT;


CREATE TABLE hunt_credits (
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT PRIMARY KEY,
    hunt_id TEXT NOT NULL REFERENCES hunts(id) ON DELETE RESTRICT,
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE RESTRICT UNIQUE,
    score_id TEXT NOT NULL REFERENCES scores(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE leads (
    id TEXT NOT NULL PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT UNIQUE,
    current_score_id TEXT REFERENCES scores(id) ON DELETE RESTRICT,
    qualification_kind TEXT NOT NULL CHECK (qualification_kind IN ('MANUAL','AUTOMATIC')),
    stage TEXT NOT NULL CHECK (stage IN ('NEW','REVIEWING','READY','CONTACTED','FOLLOW_UP','WON','LOST','ARCHIVED')),
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK (qualification_kind != 'AUTOMATIC' OR current_score_id IS NOT NULL)
) STRICT;


CREATE TABLE lead_events (
    id TEXT NOT NULL PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE RESTRICT,
    actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 20 AND actor_id NOT GLOB '*[^0-9]*' AND substr(actor_id,1,1) BETWEEN '1' AND '9' AND (length(actor_id)<20 OR actor_id<='18446744073709551615')),
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (CASE WHEN payload_json IS NULL THEN 1 WHEN json_valid(payload_json) THEN json_type(payload_json)='object' ELSE 0 END),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE lead_notes (
    id TEXT NOT NULL PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE RESTRICT,
    actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 20 AND actor_id NOT GLOB '*[^0-9]*' AND substr(actor_id,1,1) BETWEEN '1' AND '9' AND (length(actor_id)<20 OR actor_id<='18446744073709551615')),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    supersedes_id TEXT REFERENCES lead_notes(id) ON DELETE RESTRICT
) STRICT;


CREATE TABLE outreach_drafts (
    id TEXT NOT NULL PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version>=0) CHECK (version>=1),
    body TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('DRAFT','APPROVED','REJECTED','MANUALLY_SENT')),
    evidence_ids_json TEXT NOT NULL CHECK (CASE WHEN evidence_ids_json IS NULL THEN 1 WHEN json_valid(evidence_ids_json) THEN json_type(evidence_ids_json)='array' ELSE 0 END),
    created_by TEXT NOT NULL CHECK (length(created_by) BETWEEN 1 AND 20 AND created_by NOT GLOB '*[^0-9]*' AND substr(created_by,1,1) BETWEEN '1' AND '9' AND (length(created_by)<20 OR created_by<='18446744073709551615')),
    approved_by TEXT CHECK (length(approved_by) BETWEEN 1 AND 20 AND approved_by NOT GLOB '*[^0-9]*' AND substr(approved_by,1,1) BETWEEN '1' AND '9' AND (length(approved_by)<20 OR approved_by<='18446744073709551615')),
    approved_at TEXT CHECK (length(approved_at)=27 AND approved_at GLOB '????-??-??T??:??:??.??????Z'),
    manual_sent_at TEXT CHECK (length(manual_sent_at)=27 AND manual_sent_at GLOB '????-??-??T??:??:??.??????Z'),
    manual_sent_by TEXT CHECK (length(manual_sent_by) BETWEEN 1 AND 20 AND manual_sent_by NOT GLOB '*[^0-9]*' AND substr(manual_sent_by,1,1) BETWEEN '1' AND '9' AND (length(manual_sent_by)<20 OR manual_sent_by<='18446744073709551615')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    UNIQUE (lead_id,version),
    CHECK (state NOT IN ('APPROVED','MANUALLY_SENT') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
    CHECK (state != 'MANUALLY_SENT' OR (manual_sent_by IS NOT NULL AND manual_sent_at IS NOT NULL)),
    CHECK ((approved_by IS NULL)=(approved_at IS NULL)),
    CHECK ((manual_sent_by IS NULL)=(manual_sent_at IS NULL)),
    CHECK (state != 'DRAFT' OR (approved_by IS NULL AND manual_sent_by IS NULL)),
    CHECK (manual_sent_by IS NULL OR state='MANUALLY_SENT')
) STRICT;


CREATE TABLE followups (
    id TEXT NOT NULL PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE RESTRICT,
    due_at TEXT NOT NULL CHECK (length(due_at)=27 AND due_at GLOB '????-??-??T??:??:??.??????Z'),
    note TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING','NOTIFIED','DONE','CANCELLED')),
    created_by TEXT NOT NULL CHECK (length(created_by) BETWEEN 1 AND 20 AND created_by NOT GLOB '*[^0-9]*' AND substr(created_by,1,1) BETWEEN '1' AND '9' AND (length(created_by)<20 OR created_by<='18446744073709551615')),
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    completed_at TEXT CHECK (length(completed_at)=27 AND completed_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK (state != 'DONE' OR completed_at IS NOT NULL)
) STRICT;


CREATE TABLE publications (
    id TEXT NOT NULL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT UNIQUE,
    resource_id TEXT NOT NULL REFERENCES discord_resources(id) ON DELETE RESTRICT,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision>=0) CHECK (revision>=1),
    marker TEXT UNIQUE,
    message_id TEXT CHECK (length(message_id) BETWEEN 1 AND 20 AND message_id NOT GLOB '*[^0-9]*' AND substr(message_id,1,1) BETWEEN '1' AND '9' AND (length(message_id)<20 OR message_id<='18446744073709551615')),
    state TEXT NOT NULL CHECK (state IN ('PENDING','SENT','UNCERTAIN','FAILED')),
    updated_at TEXT NOT NULL CHECK (length(updated_at)=27 AND updated_at GLOB '????-??-??T??:??:??.??????Z'),
    UNIQUE (resource_id,subject_kind,subject_id,revision),
    CHECK (state != 'SENT' OR message_id IS NOT NULL)
) STRICT;


CREATE TABLE audit_events (
    id TEXT NOT NULL PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    actor_id TEXT CHECK (length(actor_id) BETWEEN 1 AND 20 AND actor_id NOT GLOB '*[^0-9]*' AND substr(actor_id,1,1) BETWEEN '1' AND '9' AND (length(actor_id)<20 OR actor_id<='18446744073709551615')),
    action TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT,
    outcome TEXT NOT NULL,
    redacted_details_json TEXT NOT NULL CHECK (CASE WHEN redacted_details_json IS NULL THEN 1 WHEN json_valid(redacted_details_json) THEN json_type(redacted_details_json)='object' ELSE 0 END),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;


CREATE TABLE backups (
    id TEXT NOT NULL PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
    manifest_json TEXT CHECK (CASE WHEN manifest_json IS NULL THEN 1 WHEN json_valid(manifest_json) THEN json_type(manifest_json)='object' ELSE 0 END),
    state TEXT NOT NULL CHECK (state IN ('CREATING','VERIFIED','FAILED')),
    requested_by TEXT NOT NULL CHECK (length(requested_by) BETWEEN 1 AND 20 AND requested_by NOT GLOB '*[^0-9]*' AND substr(requested_by,1,1) BETWEEN '1' AND '9' AND (length(requested_by)<20 OR requested_by<='18446744073709551615')),
    created_at TEXT NOT NULL CHECK (length(created_at)=27 AND created_at GLOB '????-??-??T??:??:??.??????Z'),
    verified_at TEXT CHECK (length(verified_at)=27 AND verified_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK (state != 'VERIFIED' OR verified_at IS NOT NULL)
) STRICT;


CREATE INDEX idx_ai_executions_allowance_check_id ON ai_executions (allowance_check_id);

CREATE INDEX idx_ai_executions_job_id ON ai_executions (job_id);

CREATE INDEX idx_allowance_checks_verification_id ON allowance_checks (verification_id);

CREATE INDEX idx_audit_events_created_at ON audit_events (created_at);

CREATE INDEX idx_backups_artifact_id ON backups (artifact_id);

CREATE INDEX idx_business_contacts_business_id ON business_contacts (business_id);

CREATE INDEX idx_business_contacts_evidence_id ON business_contacts (evidence_id);

CREATE INDEX idx_business_events_business_id ON business_events (business_id);

CREATE INDEX idx_business_identifiers_business_id ON business_identifiers (business_id);

CREATE INDEX idx_business_identifiers_kind_namespace_value ON business_identifiers (kind,namespace,value);

CREATE INDEX idx_businesses_normalized_name_normalized_address ON businesses (normalized_name,normalized_address);

CREATE INDEX idx_businesses_origin_hunt_id ON businesses (origin_hunt_id);

CREATE INDEX idx_businesses_origin_job_id ON businesses (origin_job_id);

CREATE INDEX idx_businesses_parent_id ON businesses (parent_id);

CREATE INDEX idx_campaign_versions_campaign_id ON campaign_versions (campaign_id);

CREATE INDEX idx_candidates_business_id ON candidates (business_id);

CREATE INDEX idx_candidates_query_id ON candidates (query_id);

CREATE INDEX idx_candidates_state ON candidates (state);

CREATE INDEX idx_command_channels_resource_id ON command_channels (resource_id);

CREATE INDEX idx_coverage_cells_campaign_id ON coverage_cells (campaign_id);

CREATE INDEX idx_coverage_cells_last_query_id ON coverage_cells (last_query_id);

CREATE INDEX idx_discord_resources_parent_resource_id ON discord_resources (parent_resource_id);

CREATE INDEX idx_discovery_queries_campaign_id ON discovery_queries (campaign_id);

CREATE INDEX idx_discovery_queries_hunt_id ON discovery_queries (hunt_id);

CREATE INDEX idx_discovery_queries_job_id ON discovery_queries (job_id);

CREATE INDEX idx_discovery_queries_source_query_hash_started_at ON discovery_queries (source,query_hash,started_at);

CREATE INDEX idx_evidence_artifact_id ON evidence (artifact_id);

CREATE INDEX idx_evidence_business_id ON evidence (business_id);

CREATE INDEX idx_evidence_business_id_observed_at ON evidence (business_id,observed_at);

CREATE INDEX idx_evidence_candidate_id ON evidence (candidate_id);

CREATE INDEX idx_evidence_research_run_id ON evidence (research_run_id);

CREATE INDEX idx_finding_evidence_evidence_id ON finding_evidence (evidence_id);

CREATE INDEX idx_finding_evidence_finding_id ON finding_evidence (finding_id);

CREATE INDEX idx_findings_research_run_id ON findings (research_run_id);

CREATE INDEX idx_followups_lead_id ON followups (lead_id);

CREATE INDEX idx_followups_state_due_at ON followups (state,due_at);

CREATE INDEX idx_hunt_credits_business_id ON hunt_credits (business_id);

CREATE INDEX idx_hunt_credits_hunt_id ON hunt_credits (hunt_id);

CREATE INDEX idx_hunt_credits_lead_id ON hunt_credits (lead_id);

CREATE INDEX idx_hunt_credits_score_id ON hunt_credits (score_id);

CREATE INDEX idx_hunts_campaign_id ON hunts (campaign_id);

CREATE INDEX idx_identity_claims_business_id ON identity_claims (business_id);

CREATE INDEX idx_identity_reviews_candidate_id ON identity_reviews (candidate_id);

CREATE INDEX idx_jobs_business_id ON jobs (business_id);

CREATE INDEX idx_jobs_hunt_id ON jobs (hunt_id);

CREATE INDEX idx_jobs_hunt_id_state ON jobs (hunt_id,state);

CREATE INDEX idx_jobs_state_next_attempt_at ON jobs (state,next_attempt_at);

CREATE INDEX idx_lead_events_lead_id ON lead_events (lead_id);

CREATE INDEX idx_lead_notes_lead_id ON lead_notes (lead_id);

CREATE INDEX idx_lead_notes_supersedes_id ON lead_notes (supersedes_id);

CREATE INDEX idx_leads_business_id ON leads (business_id);

CREATE INDEX idx_leads_current_score_id ON leads (current_score_id);

CREATE INDEX idx_leads_stage ON leads (stage);

CREATE INDEX idx_output_destinations_resource_id ON output_destinations (resource_id);

CREATE INDEX idx_outreach_drafts_lead_id ON outreach_drafts (lead_id);

CREATE INDEX idx_panels_resource_id ON panels (resource_id);

CREATE INDEX idx_publications_job_id ON publications (job_id);

CREATE INDEX idx_publications_resource_id ON publications (resource_id);

CREATE INDEX idx_research_runs_business_id ON research_runs (business_id);

CREATE INDEX idx_research_runs_job_id ON research_runs (job_id);

CREATE INDEX idx_scores_business_id ON scores (business_id);

CREATE INDEX idx_scores_business_id_created_at ON scores (business_id,created_at);

CREATE INDEX idx_scores_campaign_id ON scores (campaign_id);

CREATE INDEX idx_scores_research_run_id ON scores (research_run_id);

CREATE INDEX idx_setup_steps_plan_id ON setup_steps (plan_id);

CREATE UNIQUE INDEX one_open_hunt ON hunts ((1)) WHERE state IN ('RUNNING','PAUSING','PAUSED','STOPPING','INTERRUPTED');

CREATE TRIGGER business_origin_immutable BEFORE UPDATE OF origin_job_id, origin_hunt_id ON businesses
WHEN NEW.origin_job_id IS NOT OLD.origin_job_id OR NEW.origin_hunt_id IS NOT OLD.origin_hunt_id
BEGIN
    SELECT RAISE(ABORT, 'Business origin is immutable');
END;
