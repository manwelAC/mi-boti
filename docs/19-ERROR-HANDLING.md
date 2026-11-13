# 19 — Error handling

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and error envelope

Define predictable external failure behavior for [jobs](17-BACKGROUND-JOBS.md), [providers](10-AI-PROVIDER-INTEGRATION.md), [Discord](06-DISCORD-SERVER-ARCHITECTURE.md), and [storage](05-LOCAL-STORAGE.md). `AppError(code, safe_message, retryable, entity_id, correlation_id, corrective_action)` crosses boundaries. Internal cause chains stay redacted in local logs. Never expose raw auth output, secrets, full private paths or exception stacks in Discord.

## Failure matrix

| Code/category | Retry and state | Operator message/action |
|---|---|---|
| WRONG_GUILD / FORBIDDEN / WRONG_CHANNEL | None, no enqueue | Private denial; correct channel only when authorized |
| CONFIG_INCOMPLETE / RESOURCE_MISSING | None; affected feature blocked | Ask administrator to preview setup recovery |
| DISCORD_FORBIDDEN | No blind retry; publication FAILED/setup PARTIAL | List missing named permissions and affected resource |
| DISCORD_RATE_LIMIT | Honor library/Retry-After within retry/time budget | Pending delivery, records already saved |
| DISCORD_UNAVAILABLE / token expired | Bounded output retry; never replay research | Return persistent job ID/status when possible |
| DB_BUSY | At most 3 short transaction attempts within 5-second busy timeout each | Busy, no confirmed change until commit |
| DB_CONSTRAINT | Identity conflict reloads winner; stale revision returns conflict | Existing record or refresh current view |
| DB_CORRUPT / unexpected FK failure | Halt affected writes and hunt CRITICAL_ERROR | Stop service, validate backup/DB locally |
| DISK_LOW / ARTIFACT_WRITE_FAILED | No new heavy work; hunt SAFETY_LIMIT or CRITICAL_ERROR | Free space/check permissions; saved records retained |
| NOT_INSTALLED / AUTH_REQUIRED | No execution retry; hunt failed | Install approved CLI or authenticate manually |
| BILLING_UNVERIFIED / VERIFICATION_EXPIRED | No AI execution; VERIFICATION_INVALID | Administrator must complete real verification |
| ALLOWANCE_UNKNOWN / ALLOWANCE_EXHAUSTED | No AI retry or fallback; hunt FAILED | Capacity cannot be verified / exhausted, with actual observation time |
| AI_TIMEOUT / EXECUTION_FAILED | Retry only known transient, idempotent failures with new allowance gate and remaining budgets | Partial results retained; task failed |
| CANCEL_FAILED | FAILED, block new AI until orphan resolved | Owner must confirm process termination |
| OUTPUT_INVALID / EVIDENCE_INVALID | At most one repair task with fresh gate; then review/fail | Unsupported findings not accepted |
| SOURCE_FORBIDDEN / POLICY_UNKNOWN | Disable source, no access retry | Review source permission/policy |
| SOURCE_RATE_LIMIT / SOURCE_TIMEOUT / SOURCE_5XX | Bounded approved retry; no endpoint evasion | Source delayed; partial summary if exhausted |
| SOURCE_SCHEMA_CHANGED | Disable adapter, no guessed parsing | Adapter needs compatibility update |
| UNSAFE_URL / BODY_TOO_LARGE / ACCESS_DENIED | No bypass; research limitation or failure | Page excluded with safe reason |
| IDENTITY_AMBIGUOUS | Hold candidate/review; no research or credit | Review matching businesses |
| SOURCE_EXHAUSTED | STOPPED with exact partial counts | Configured search plan exhausted; no recycled leads |
| RESTART_INTERRUPTION / AUTHORIZATION_LOST | INTERRUPTED, no auto-resume | Authorized operator must inspect/resume/stop |
| DELIVERY_REVIEW_REQUIRED | MVP uncertain publication is FAILED; never automatically resend | Operator inspects the channel and explicitly reauthorizes delivery if absent |
| CONFLICT / STALE_PLAN | No mutation | Reload current revision / new setup preview |

## Retry discipline

Only explicitly typed transient errors retry. Total job attempts <=3; research page <=2; output repair <=1 extra execution. A timeout after an uncertain external side effect requires operator inspection in the MVP and marker reconciliation post-MVP, never unconditional replay. Every actual retry consumes source/request/task budgets and rechecks cancellation, remaining active and absolute-age budgets (or standalone-job age), current permission and provider allowance where applicable. Retry-After beyond either remaining hunt clock ends work; backoff while RUNNING consumes active time and never suspends absolute age. Standalone jobs obey their own age ceiling. No retry invokes a different provider, paid API or prohibited source.

Audit security/eligibility failures once per event with a stable correlation ID; coalesce repeated transport failures to avoid log floods. Diagnostic logs contain record IDs, job kind, provider/source ID, safe error code, attempt and timestamps. Activity channel gets concise sanitized summaries, not raw fetched bodies. If Discord logging fails, local log remains available; logging failure must not recursively enqueue unbounded jobs.

## Recovery and reporting

Database commit is the acknowledgment boundary for durable changes. If an interaction expires after enqueue, return status through persistent job/destination when possible. If message delivery is uncertain, the MVP marks the publication FAILED/DELIVERY_REVIEW_REQUIRED and waits for operator inspection before any resend. Post-MVP marker reconciliation uses the UNCERTAIN publication state. Setup resource uncertainty is a separate mandatory reconciliation path. Failed setup preserves successful resources and prompts a new preview. Failed qualification preserves registry/evidence without credit. Restart never continues autonomous jobs without authorization. Terminal summary follows [17](17-BACKGROUND-JOBS.md).

## Acceptance

For each row, inject its failure and assert retry count, exact state, committed data, no prohibited side effect, safe message and corrective action. T18 verifies envelopes/redaction; T09 tests no fallback; T13/T16 test recovery; L01/L02 validate actual integration error behavior. See [20](20-TESTING-STRATEGY.md).

## Phase 2 Discord rate-limit diagnostics

The Discord transport distinguishes SDK RateLimited from generic outages. It reports the rounded-up retry_after duration to the operator and logs only that duration and whether the call could mutate state. It does not automatically retry setup. Read failures create no provisioning effect; mutation failures retain the conservative uncertain-outcome hold and require inspection before recovery.
