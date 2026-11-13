# 02 — Technical architecture

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

This document assigns component responsibilities for [R01–R16](01-PRODUCT-REQUIREMENTS.md). The [project structure](03-PROJECT-STRUCTURE.md) maps those responsibilities to modules, and the [database contract](04-DATABASE-SCHEMA.md) defines their persistent records.

## Components

One local process runs Discord, application services, a SQLite write coordinator and bounded asynchronous workers. Blocking database and process operations must run without blocking the event loop. A deployment lock prevents two processes from sharing one data root, while transactional guards protect invariants even if an overlapping writer appears.

| Component | Responsibility | Prohibited responsibility |
|---|---|---|
| Discord transport | It parses requests, acknowledges interactions and renders results. | It must not run research or CLI execution inline. |
| Policy service | It validates the guild, member, action, channel and configuration. | It must not authorize channels by name. |
| Setup service | It previews changes and journals confirmed provisioning. | It must not modify unmanaged resources without explicit adoption approval. |
| Registry | It resolves identity and assigns candidate ownership. | It must not merge ambiguous businesses automatically. |
| Discovery and research | They enforce source policies, fetch safely and preserve evidence. | They must not treat retrieved text as instructions. |
| Provider adapter and gate | They verify compatibility and allowance before executing fixed tasks. | They must not switch providers or select metered fallback. |
| Intelligence and scoring | They validate findings and calculate deterministic scores. | They must not invent missing facts. |
| Hunt orchestrator | It enforces budgets, lifecycle and quota. | It must not count Discord messages as leads. |
| CRM and outreach | They preserve review history and human-reviewed drafts. | They must not send external communications. |
| Scheduler | It claims jobs and enforces leases, retries, cancellation and recovery. | It must not resume hunting at startup. |

The MVP wires the non-AI paths, including Phase 4a safe website collection and evidence persistence. Disabled AI commands report their actual verification blocker. Manual CRM qualification and manual drafts do not require a CLI or a synthetic score.

## Service contracts

The transport builds `ActorContext(guild_id, channel_id, user_id, role_ids, administrator, interaction_id)` from live Discord context. The policy service returns `AuthorizedAction` or `Denial(code, correct_channel_id?)` from `authorize(context, command_key)` before enqueueing work and before delayed privileged execution. Component callbacks use that same policy.

The scheduler's `enqueue(action, idempotency_key, payload, hunt_id?) -> job_id` validates a typed payload. Commands use interaction IDs for idempotency, while publications use semantic keys such as `publish-lead:<lead_id>:<destination_id>:<revision>`. The registry's transactional `resolve(observation, origin)` returns Existing, NewReservation or Ambiguous. `Research.collect(business_id, refresh, budget) -> evidence_ids` never starts hunting. `Intelligence.evaluate(run_id, provider_id, campaign_snapshot) -> score_id` uses the [provider gate](10-AI-PROVIDER-INTEGRATION.md).

Service errors contain stable codes and redacted messages. Job payloads contain record IDs and validated options, and they exclude credentials and arbitrary executable instructions. Domain IDs are UUIDs, and Discord snowflakes are canonical decimal strings.

## Atomic operations and external effects

External network and CLI calls must not occur inside SQLite transactions. First, the service reserves work and commits that reservation. Second, it performs the external operation without holding a database transaction. Third, it opens a new transaction and commits validated results only if the worker's lease and expected revisions still match. An expired worker cannot commit.

The registry inserts identity and origin ownership atomically. The qualification transaction checks that the hunt is RUNNING, quota remains, evidence is valid, the business belongs to the hunt, and the lease is current. It then creates the lead, quota credit and publication job together. When the committed count reaches quota, it marks the hunt COMPLETED before another dispatch can earn credit.

Discord delivery follows the database commit. The publication job is persisted before sending, and its message ID is stored after known success. In the MVP, a send whose outcome cannot be established is marked FAILED with a delivery-review reason. The scheduler does not automatically resend it; an authorized operator must inspect the channel before explicitly reauthorizing delivery. This preserves the lead and prevents uncontrolled duplicate sends. Marker-based recent-message reconciliation and the UNCERTAIN publication state are post-MVP improvements. Setup's separate resource-ownership reconciliation remains mandatory from the MVP.

## Startup and isolation

Before connecting Discord, startup validates settings, the data lock, schema and singleton guild binding. It marks unfinished autonomous work INTERRUPTED and restores persistent controls. It never starts or resumes a hunt. A reconnect restores transport without changing hunt execution state.

Before each privileged dispatch, the job revalidates the initiating member and current policy. Lost authorization interrupts affected work. Database integrity failures halt affected writes. Output failures never cause research or qualification to run again.

One provider execution slot is shared by AI-enabled hunts, optional Phase 4b research analysis and AI drafting. Phase 4a HTTP collection does not acquire that slot or perform allowance checks. The allowance check and process launch use that slot together so another task cannot consume the admitted capacity between them. One active, paused or interrupted hunt occupies the deployment's hunt slot. Independent discovery still obeys registry constraints. Budgets and active-time reservations are persisted before dispatch, so a crash cannot reset resource limits or charge an entire offline period as active work.

## Acceptance

T03 must show that the transport acknowledges before background execution and that replayed interactions produce one job. T07 must show that quota commits are atomic. T09 must show that prohibited providers and routes are never called. T13 must show that stale workers cannot commit and that restart starts no autonomous work. T16 must show that committed state survives recovery. The [testing strategy](20-TESTING-STRATEGY.md) defines their fixtures and expected results.
