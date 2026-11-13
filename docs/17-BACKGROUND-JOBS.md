# 17 — Background jobs and hunting

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

This document specifies the lifecycle, execution budgets and recovery rules for R10–R12. It relies on [database transactions](04-DATABASE-SCHEMA.md), [provider gates](10-AI-PROVIDER-INTEGRATION.md), and [bounded discovery](08-BUSINESS-DISCOVERY.md). The non-AI MVP uses the scheduler for discovery, Phase 4a website research, output and CRM work. Autonomous hunt admission remains disabled until its provider passes L02 and the Phase 5 gate passes.

## Hunt state machine

| State | Allowed transition | Trigger |
|---|---|---|
| RUNNING | PAUSING, STOPPING, COMPLETED, FAILED, INTERRUPTED | A pause or stop request, exact quota completion, failure or interruption occurs. |
| PAUSING | PAUSED, STOPPING, FAILED, INTERRUPTED | In-flight work settles, a stop is requested, or work fails or is interrupted. |
| PAUSED | RUNNING, STOPPING, FAILED, INTERRUPTED | An operator resumes or stops, a budget or absolute-age check fails, or the application restarts. |
| INTERRUPTED | RUNNING, STOPPING, FAILED | An operator resumes or stops, or a budget or absolute-age check fails. |
| STOPPING | STOPPED, FAILED, INTERRUPTED | Cancellation settles, cancellation or safety checks fail, or the application is interrupted. |
| COMPLETED, STOPPED, FAILED | none | These states are terminal. A new hunt requires a new authorized start. |

Admission creates RUNNING atomically after all checks; it does not persist a NEW hunt. COMPLETED means the exact quota was reached. STOPPED means the operator stopped the hunt or its bounded source plan was exhausted, with partial counts retained. FAILED means an allowance, safety, source or critical-error stopping condition occurred. Every terminal state and interruption requires a stop reason. The reason enum is QUOTA_REACHED, OPERATOR_STOP, SOURCE_EXHAUSTED, SOURCE_UNAVAILABLE, ALLOWANCE_EXHAUSTED, ALLOWANCE_UNKNOWN, AUTH_REQUIRED, VERIFICATION_INVALID, SAFETY_LIMIT, CRITICAL_ERROR, AUTHORIZATION_LOST, RESTART_INTERRUPTION or CANCEL_FAILED. PAUSED is not terminal. INTERRUPTED retains the hunt slot until an explicit resume/stop or a safety-only expiry check resolves it. A local expiry check may mark an aged PAUSED/INTERRUPTED hunt FAILED/SAFETY_LIMIT without launching external work; it never resumes a job. Expired pause/resume checks may also enter FAILED without launching external work.

## Job state machine

A QUEUED job may enter RUNNING or CANCELLED. A RUNNING job may enter SUCCEEDED, FAILED, CANCELLED, RETRY_WAIT or INTERRUPTED. A RETRY_WAIT job may enter QUEUED or CANCELLED. An INTERRUPTED job may return to QUEUED only after an explicit authorized hunt resume or an approved safe non-AI recovery decision; otherwise it enters CANCELLED. SUCCEEDED, FAILED and CANCELLED are terminal. Retrying a terminal failed job creates a new job and an audit link rather than rewriting its history.

The job kinds are DISCOVER, RESEARCH, QUALIFY, DRAFT, PUBLISH, REMINDER, BACKUP, EXPORT and VERIFY_PROVIDER. Recovering a provider-verification job must never launch an AI task automatically. RESEARCH collection jobs with analyze:false are enabled in the non-AI release and never invoke providers. QUALIFY, AI DRAFT and the optional analyze:true branch remain disabled; manual draft saves use CRM transactions without an AI DRAFT job.

A claim transaction compares state, next_attempt_at and cancellation status, then sets RUNNING with a random lease token and a 30-second expiry. The worker sends a heartbeat every ten seconds. Progress and result commits require the same unexpired token. An expired lease becomes INTERRUPTED and is not immediately reclaimed for hunting. The scheduler owns claims, but database guards protect against accidental overlap. It never holds a transaction open during an external operation.

## Admission and execution loop

`start(actor, campaign, quota)` validates the configured guild, actor, action, channel, readiness, quota, targeting, source policies and provider. It requires fresh allowance and an unused hunt slot. It then snapshots the campaign, rubric, provider, policies and effective limits and inserts the hunt and its first discovery job in one transaction. Admission does not replace the fresh allowance check before each actual AI task.

For each iteration, the worker checks authorization, hunt state, both clocks and remaining budgets. It plans one approved query and reserves its request budget before dispatch. It resolves each returned observation transactionally, skips existing businesses, and holds ambiguous identities. For a new business, it collects permitted evidence, runs a freshly gated qualification task, validates the result and calculates the score. Only the atomic qualification transaction may create quota credit. Publication occurs after that transaction, and the loop then checks its limits again.

The worker never uses previously registered businesses to replace a shortfall. A reserved business that remains incomplete when its hunt terminates stays in the registry. Researching it later requires explicit refresh and cannot make it new again.

## Clocks and quota-scaled safety envelope

The configuration defaults and formulas below are declared in [23](23-IMPLEMENTATION-GUIDELINES.md). `hunt.max_active_seconds` defaults to 3600 as the base budget for one quota block. `hunt.quota_block_size` defaults to 5. For quota q, let B = max(1, ceil(q / hunt.quota_block_size)). The effective active budget is min(hunt.max_active_cap_seconds, hunt.max_active_seconds * B). The default active cap is 86400 seconds. Thus quota 25 has five blocks and 18000 active seconds; this scaling is the D04 technical recommendation, not a hidden increase to the base setting.

Only RUNNING, PAUSING and STOPPING consume active time. PAUSED and INTERRUPTED consume none. Separately, `hunt.max_age_seconds` defaults to 604800 seconds and measures absolute age from created_at, including pauses and offline periods. A resume must have time left on both clocks as well as every resource budget. Neither clock nor any resource counter resets on resume. Exhausting either clock produces FAILED/SAFETY_LIMIT with an accurate partial summary.

Persist active_milliseconds, active_checkpoint_at and active_lease_expires_at in the hunt record. Measure live elapsed intervals with a monotonic clock, and persist accounting at state transitions and worker heartbeats. Reserve at most one 30-second active lease before work so an abrupt crash cannot erase dispatched active work. Recovery charges at most that already-reserved lease interval, never the entire time until restart. Report any conservative reserved-time charge as such. Before entering PAUSED, settle active leases and record the final accumulator. Wall-clock rollback must not increase remaining age: retain a persisted maximum observed UTC instant, and reject a resume if clock consistency cannot be established.

| Limit | Formula / default | Quota 25 example |
|---|---|---:|
| Qualified quota | The operator chooses 1–100. | 25 |
| Hunt slots | One slot includes running, paused and interrupted hunts. | 1 |
| Background jobs and AI | Two jobs may run, with one AI process globally. | 2 / 1 |
| Discovery requests | min(200, max(20, 2*q)); retries count. | 50 |
| Candidates examined | min(2000, max(200, 20*q)); duplicates and invalids count. | 500 |
| HTTP requests | min(16000, max(800, 160*q)); policy, redirects and retries count. | 4000 |
| AI task executions | min(2000, max(100, 20*q)); repair tasks count. | 500 |
| Base active budget | hunt.max_active_seconds = 3600; only RUNNING/PAUSING/STOPPING count. | 3600 seconds per block |
| Effective active budget | min(86400, 3600*B) at default settings. | 18000 seconds / 5 hours |
| Absolute age ceiling | hunt.max_age_seconds = 604800 from creation. | 7 days |
| Per-business pages | Five pages, with at most two attempts per page. | 5 / 2 |
| Job attempts | At most three total; stricter source/task limits win. | 3 |
| Retry delays | Two/four seconds plus 0–1 second jitter; applicable clocks keep running. | Bounded |
| AI task limits | 120 seconds, 64 KiB input and 256 KiB output. | Bounded |
| Disk free floor | New artifact-heavy work requires at least 500 MiB free. | 500 MiB |

The four resource formulas use the configured base, per-lead factor and cap keys in doc 23 rather than hardcoded duplicate constants. Source daily budgets, policy throttles and provider capacity can only lower available work; scaling never raises those external entitlements. A running hunt retains its snapshotted formulas and effective ceilings even if local settings change.

The worker reserves budgets before dispatch, and a dispatched request is not refunded after cancellation or crash. Counters distinguish seen, new, existing, ambiguous, invalid, researched, unqualified and qualified observations, plus request and task attempts. A source request consumes both source and HTTP budgets where applicable. Reaching a resource or clock limit ends the hunt with SAFETY_LIMIT and its exact partial count. Pauses, retries and restarts never reset these counters.

## Expected throughput

This is an estimate to validate in Phase 5, not a performance or qualification promise. Serial AI at up to 120 seconds per task, plus up to five pages with at least two seconds between starts on a host, suggests roughly 30–60 researched candidates per active hour under ordinary conditions. At 120 seconds per task, the AI-only ceiling is 3600/120 = 30 candidates per hour; faster tasks can approach 60, while page latency, retries, repairs and throttles can lower throughput below 30. Strict qualification gates mean qualified leads will be a fraction of researched candidates.

At that planning range, quota 25's default five active hours permits approximately 150–300 researched candidates before other limits. Reaching 25 would require about 8.3–16.7 percent to qualify; the 500-candidate, 500-task and 4000-request ceilings leave room for filtering and repairs. This makes quota 25 plausible with sufficient sources and verified allowance, but it is not guaranteed. Poor source yield, a lower qualification rate, slow tasks or exhausted capacity still produce an honest partial result. Phase 5 must measure actual latency/yield, record the effective limits and seek owner approval before changing D04. Large quotas can legitimately end at SAFETY_LIMIT, and the UI must show their budgets before start.

## Pause, stop and late results

A pause transaction sets PAUSING and blocks new claims. Workers check cancellation before and after each network or CLI phase. They cancel supported in-flight processes, retain observations and checkpoint candidate/run IDs. The hunt enters PAUSED only after all its running jobs settle and active accounting is persisted.

If a valid score arrives during PAUSING, the worker saves it as an uncredited checkpoint. On an authorized resume, a new idempotent QUALIFY commit job references that score and checks state, evidence, lease, clocks and remaining quota before granting credit. It does not revive a completed job's expired lease or rerun AI unnecessarily. Already-observed source data may be persisted during a pause, but no new external task launches.

A stop transaction sets STOPPING and flags unfinished hunt jobs for cancellation. The worker terminates owned process trees within ten seconds and enters STOPPED once cancellation settles. STOPPING consumes active time; reaching an active or age ceiling while stopping produces FAILED/SAFETY_LIMIT after cancellation. A failed process termination produces FAILED/CANCEL_FAILED and blocks all new AI execution until the orphan is confirmed dead.

A terminal hunt cannot accept late credit or schedule more autonomous work. Late evidence may remain in interrupted research history. At quota completion, the transaction marks COMPLETED, cancels remaining work and retains uncredited registry records. It never refunds credit or recycles businesses.

## Restart and summaries

At startup, the application marks RUNNING, PAUSING, PAUSED and STOPPING hunts INTERRUPTED with RESTART_INTERRUPTION. It also marks their unfinished jobs INTERRUPTED, settles only the reserved active lease, and reconciles ownership of external processes without killing unrelated processes. It must not charge offline time as active time or run discovery, research, qualification or AI drafting because a job was queued before the crash.

An explicit resume checks current member permission, provider verification and allowance, resource readiness, checkpoint integrity, counters, effective active budget and absolute age. It requeues only eligible incomplete work while preserving idempotency. It does not repeat completed tasks or credits. A resume after one day paused may proceed if active and other budgets remain; a resume after seven days fails SAFETY_LIMIT without external execution. A FAILED terminal session cannot be resumed.

Safe standalone publications and reminders may be reconstructed after configuration and authorization checks because they do not perform research or AI. In the MVP, unknown delivery outcomes require operator inspection rather than automatic resend; marker reconciliation is post-MVP. BACKUP and EXPORT failures require explicit retry. Reconnecting Discord does not run startup recovery or alter hunt state.

The final summary reports state, stop reason, quota, committed credits, candidate dispositions, requests and tasks used, accumulated active time, absolute age, any crash-reserved active charge, unfinished work, delivery status, provider and last allowance observation. It also states the operator's next action. It never presents source exhaustion or a safety-limited partial result as quota success.

## Acceptance

T07 races claims and credit commits and verifies exact quota enforcement. T08/T09 stop work on allowance failures without fallback. T13 pauses for a day with active time remaining, resumes after restart, rejects absolute-age and active-budget exhaustion independently, tests clock rollback and bounded crash accounting, and proves that no autonomous work starts automatically. It also tests process cancellation and stale leases. T05 covers duplicate-only and exhausted source plans, and T03 covers repeated lifecycle interactions. See the [testing strategy](20-TESTING-STRATEGY.md).

## Phase 2 setup worker boundary

Administrator-confirmed provisioning uses the existing setup_plans/setup_steps durable journal, not the generic jobs table or any AI/hunt worker. It admits one CONFIRMED/APPLYING plan at a time, bounds execution to 180 seconds and individual Discord requests to 15 seconds, and preserves partial state on errors, cancellation or shutdown. Restart changes unfinished provisioning to PARTIAL and in-flight steps to UNCERTAIN; it does not resume provisioning. A fresh administrator preview/confirmation is required. Cancellation of an unconfirmed preview expires it; Ctrl+C cancels in-flight local work and records recovery state. The generic job scheduler and all hunting lifecycle/credit services remain unimplemented and disabled.
