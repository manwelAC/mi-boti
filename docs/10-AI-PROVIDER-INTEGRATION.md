# 10 — AI provider integration

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and compatibility status

Specify R08/R09 and the fail-closed execution gate used by [research intelligence](12-AI-LEAD-INTELLIGENCE.md), [drafts](15-OUTREACH-MANAGEMENT.md), and [hunts](17-BACKGROUND-JOBS.md). No provider capability is asserted without real validation.

| Candidate | Installation/auth | Subscription allowance | Autonomous status |
|---|---|---|---|
| Codex CLI | UNVERIFIED | UNVERIFIED | BLOCKED pending Phase 0 |
| Claude Code CLI | UNVERIFIED | UNVERIFIED | BLOCKED pending Phase 0 |
| Antigravity CLI (AGY) | Local agy.exe detected; model-list request succeeded; authentication/billing/version verification incomplete | Structured `/usage` JSON observed; freshness, scope and task-reserve compatibility unverified | BLOCKED pending remaining L02 checks |
| OpenCode CLI | UNVERIFIED; backend and billing mode must be identified | UNVERIFIED | BLOCKED pending Phase 0 |

A CLI wrapper or successful login does not prove subscription billing, capacity, or safe execution. No guessed CLI flags, invented usage endpoint, screen-scraped percentage, or API-key fallback is specified. Phase 0 determines whether supported permitted mechanisms exist. If not, mark BLOCKED with evidence and keep autonomous execution disabled.

## Initial local AGY feasibility observation — 2026-11-14

The operator identified AGY as an installed candidate. Local inspection resolved `C:\Users\micro\AppData\Local\agy\bin\agy.exe`; `--help` and the documented help subcommands succeeded. The executable's Windows ProductName, CompanyName and FileVersion metadata were empty, so its installed version and distribution integrity are not yet established. `agy models` successfully returned a model inventory, but that is not independent proof of subscription billing or execution eligibility.

After reviewing the official [headless command behavior](https://antigravity.google/docs/cli/headless) and [quota documentation](https://antigravity.google/docs/cli/commands/usage), the bounded status invocation `agy --print /usage --output-format json --print-timeout 15s` returned exit code 0 and status SUCCESS. Its command payload identified usage and included model-group buckets with IDs, windows, remaining_fraction and reset_time. The observed groups included Gemini, Claude/GPT, and a separate Argon bucket. The response reported num_turns=0 and all token-usage counters zero. No generative prompt, authentication flow, provider switch, or application code was executed.

This establishes an observed structured quota-status surface on this installation, not a completed L02 pass. Remaining checks include version/distribution verification, account and subscription-versus-credit billing, freshness/cache failure behavior, exact model-to-bucket mapping, enforceable task reserves, exhausted/unverifiable handling, task/tool isolation and process-tree cancellation. Reported percentages alone cannot establish a safe task bound. No current allowance snapshot or account identifiers are persisted in this specification, and no provider is enabled. The other candidate providers remain untested.

## Additional AGY status checks — 2026-11-14

The local executable's SHA-256 was `064e65195b6e4fd2fc8033a02d9b50721d9f5b93754ea7691bfe453efbd5aa2f`. This fingerprints the observed file; it does not verify its provenance or version. The official [CLI reference](https://antigravity.google/docs/cli/reference) documents useG1Credits as allowing credit use after plan quota exhaustion and a separate modelProvider option for direct Gemini API access. Both routes require explicit exclusion in any eventual Mi Boti execution profile.

Read-only `/config` and `/help` requests were made with structured JSON output, a 15-second print timeout and a 22-second outer process timeout. A session-only settings override set useG1Credits=false and disableSlashCommands=false; no persistent user settings were changed. Both commands returned exit code 0, status SUCCESS, num_turns=0 and zero token counters. Only allowlisted nonsecret settings were retained in the probe summary; raw settings/auth data were not printed or added to the documentation.

The effective `/config` response reported useG1Credits=false, disableSlashCommands=false, an empty modelProvider, allowNonWorkspaceAccess=false, agentMode=auto and enableTerminalSandbox=false. These observations confirm that the status invocation accepted the no-credit override, not that all possible billing routes or generated tasks are safely constrained. No generation was attempted. The current sandbox configuration does not demonstrate the required task isolation, and the exact version, subscription/account mode, live quota freshness/negative paths, per-model governing buckets and safe task reserves remain unverified. L02 remains BLOCKED; the non-AI MVP path is unaffected.

## Adapter contract

```python
class ProviderAdapter(Protocol):
    async def detect(self) -> Installation: ...
    async def auth_status(self) -> Authentication: ...
    async def allowance(self) -> AllowanceSnapshot: ...
    async def eligibility(self, task: TaskRequest,
                          allowance: AllowanceSnapshot) -> Eligibility: ...
    async def execute(self, task: TaskRequest,
                      cancellation: Cancellation) -> TaskResult: ...
    async def cancel(self, execution_id: str) -> CancellationResult: ...
```

`Installation`: provider_id, resolved executable path, hash, CLI version, adapter version, supported operations and reason. `Authentication`: AUTHENTICATED/UNAUTHENTICATED/UNKNOWN, nonsecret account fingerprint, billing mode SUBSCRIPTION/METERED/UNKNOWN, checked_at. No credentials returned.

`AllowanceSnapshot`: provider_id, account_fingerprint, observed_at, expires_at, state AVAILABLE/EXHAUSTED/UNKNOWN, source_kind, evidence_ref, windows[]. Each window has scope/model identifier, unit, remaining, limit if actually reported, reset_at if actually reported, and required task reserve. Nullable quantities stay null; do not synthesize percentages or reset times. AVAILABLE requires every relevant limit be understood and sufficient for a bounded task. If units cannot be mapped to safe task eligibility or a hidden governing window exists, UNKNOWN. A bare “logged in” or absence of rate-limit error is UNKNOWN.

`TaskRequest`: task_id, kind QUALIFY/DRAFT, provider_id pinned by snapshot/request, input_schema_version, sanitized evidence records, output_schema, maximum runtime, maximum input/output sizes, and execution workspace ID. No arbitrary command, working directory, URL-fetch request, tool definition or credential can come from research text. `TaskResult`: execution_id, SUCCEEDED/FAILED/CANCELLED/INTERRUPTED, structured output, measured usage if available, limitation/error code, start/finish times. Raw stdout/stderr are capped and redacted. `Eligibility`: ALLOWED/DENIED, reason code, verification ID and allowance check ID.

## Verification procedure and proof

For each adapter/version/account/model combination, an authorized administrator performs:

1. Identify official distribution and current documentation, permitted automation, subscription access terms and billing behavior. Record versions, executable hash, date and sanitized evidence. Do not automate prohibited login; owner authenticates manually using the provider's own supported process.
2. Prove installation and noninteractive authentication checks without exposing credentials. Prove subscription mode is selected and metered credentials/routes cannot be used; if backend mode cannot be established, block.
3. Test the documented allowance mechanism against a known real account state. Determine all relevant windows/units, freshness, model scope and reset semantics. Demonstrate expired/malformed/unavailable output returns UNKNOWN and exhausted capacity returns EXHAUSTED. Simulation may supplement negative tests but cannot substitute for evidence that the real mechanism exposes usable capacity.
4. Prove the bounded task's reserve fits known capacity. If capacity cannot support an enforceable bounded execution or ongoing enforcement, block. Where a provider cannot cap work safely, no arbitrary percentage estimate may replace the proof.
5. Execute a small permitted task only after the gate passes; verify output schema, absence of external tool side effects, timeout/process-tree cancellation, output cap and usage reporting. Capture sanitized before/after checks. If real exhausted-state testing is unavailable, record that gap and keep the autonomous gate blocked until the critical path is verified by a permitted method.
6. Store VERIFIED only after required live cases pass. Verification validity is seven days, invalidated immediately by CLI binary/version, adapter, auth account, model/billing configuration or relevant policy changes. Reverify before enabling autonomous work. A mocked success never changes verification status to VERIFIED.

## Gate and execution sequence

Every AI call, including manual research and draft generation, takes the single provider execution lock, checks current verification tuple/expiry, detects installation/version, checks auth and subscription billing, obtains fresh allowance (maximum age 30 seconds), validates all scopes/reserves, persists allowance_checks and ai_executions, then starts fixed argv with shell disabled. An internal gate token binds task ID, provider, account and check; adapters cannot execute without it. No gap may release the lock between check and launch.

Maximum runtime is 120 seconds, output 256 KiB, input 64 KiB; provider-specific lower limits win. Execute in an isolated tmp workspace, with approved environment allowlist and no unrelated secrets. CLI must not gain general shell, network or filesystem tools through task content. If that capability cannot be constrained/verified for the selected CLI, block its use. Credential access needed by the official subscription mechanism is a documented exception scoped to that provider; never pass bot token or application DB.

For longer work, provider-enforced bounds must ensure the admitted task cannot exceed verified capacity. Recheck allowance after execution and before any next task. An exhausted/error response during execution is authoritative even if admission succeeded. UNKNOWN/EXHAUSTED stops the hunt immediately at a safe cancellation point and prevents future tasks; never switch provider. Resume cannot change provider; a changed provider needs a new session. Partial valid evidence may persist without quota credit if execution failed.

## Failure and acceptance

Stable reasons include NOT_INSTALLED, AUTH_REQUIRED, BILLING_UNVERIFIED, VERIFICATION_EXPIRED, ALLOWANCE_UNKNOWN, ALLOWANCE_EXHAUSTED, UNSUPPORTED_CAPABILITY, OUTPUT_INVALID, TIMEOUT and CANCEL_FAILED. Render known capacity or `Unknown`, with observation time and reason; never invent remaining percentages. Do not log auth output. T08 verifies the full gate matrix with fakes; T09 proves zero provider-switch/API calls on failures; L02 is the mandatory real compatibility test. See [20](20-TESTING-STRATEGY.md). If no provider passes L02, affected AI features remain visibly disabled and autonomous hunting remains unreleased. The owner has already authorized the non-AI fallback in README D10 and roadmap Phase 0; no further scope decision is needed to deliver that slice. Any relaxation of the subscription safeguards still requires an explicit new owner decision.

## Phase 0 assessment checkpoint — 2026-11-14

A further bounded `/usage` request with session-only useG1Credits=false and disableSlashCommands=false returned SUCCESS, exit 0, zero model turns and zero token counters. It exposed the five expected Gemini/Claude-GPT/Argon bucket identifiers with remaining fractions and reset timestamps. No generation was attempted: task reserves, billing isolation, version/provenance, quota freshness/negative paths and safe tool/process execution are not established. L02 remains BLOCKED; no alternate provider or metered API is selected. This is a recorded assessment, not an adapter or L02 pass. Independent non-AI Phase 1 development proceeds under the approved fallback.
