# 18 — Security and privacy

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and threat model

Implement R15 across [Discord authorization](07-DISCORD-COMMANDS-AND-INTERACTIONS.md), [safe fetching](09-WEB-RESEARCH-ENGINE.md), [CLI execution](10-AI-PROVIDER-INTEGRATION.md), and [storage](05-LOCAL-STORAGE.md). Website text, directory records, AI output, command input, component IDs and local optional tool configuration are untrusted. Local service-account compromise is outside the application's full protection, but least privilege and secret isolation reduce exposure.

## Authorization and configuration controls

Allow one configured guild, bound to the database singleton; reject foreign guilds even for the owner. Validate live member permission, action, exact mapped channel ID, readiness and record scope on commands/components/jobs. No DMs, inherited thread access or name-based exceptions. Bootstrap/recovery applies only to administrator `/setup`. Default role grants empty; administrators explicitly choose operator roles. Audit both denials and privileged mutations with correlation ID, actor, action, entity, outcome and redacted detail. Avoid publicly disclosing correct-channel links to nonmembers; all errors are private.

Allowlist configuration keys and validate values; never expose arbitrary SQL, path, environment, executable or network endpoint mutation through Discord. Bot token comes from environment; provider credentials stay under official provider-managed secure storage. Do not copy auth tokens into SQLite, prompts, backup, artifacts, subprocess logs, Discord, or fixture files. Secret redaction covers token/password/auth-header patterns and known active secret values before formatting/serialization, including exception chains. Raw auth commands return typed states, not their original output.

## Subprocess and prompt boundaries

Launch an owner-configured resolved executable with fixed argv via shell=False. Reject writable/untrusted executable locations where practical and compare verified binary hash/version. No shell strings, AI-generated arguments, user-controlled working directories or inherited broad environment. Minimal environment permits only required runtime/provider authentication variables; excludes bot token and unrelated API credentials. Use an isolated workspace, close stdin after bounded task input, cap stdout/stderr, enforce runtime and cancel process trees. Verify behavior on target OS; never kill unrelated processes based on guessed names.

Provider CLI must not execute arbitrary tools, change workspace files or use undeclared MCP/backends. A safe profile must be demonstrated; inability to constrain it blocks compatibility. Prompt delimiters help identify data but are not security enforcement; output schema, evidence checks, hardcoded adapter behavior and absence of arbitrary tool execution are the controls. Ignore webpage instructions requesting secrets, shell commands, provider switching or external outreach.

## HTTP and filesystem boundary

Use the full URL/DNS/redirect/IP-pinning policy in [09](09-WEB-RESEARCH-ENGINE.md). Test actual connection destination and reject non-global addresses, unsafe ports and schemes. Disable trust in proxy environment by default. Cap compressed/decoded size and parsing resources. No browser fallback circumvents access restrictions.

Use generated paths beneath data root, reject traversal and junction/symlink escapes on read/write/delete/restore, sanitize CSV formulas, and never execute research artifacts. Apply restrictive OS ACLs to DB, artifacts, backups and verification evidence. No secret goes into ordinary records. Disable Discord mentions for all untrusted content and avoid unnecessary automatic previews. Private managed channels restrict contact/draft access; mapping changes recheck visibility.

## Data minimization and retention

Collect business-relevant public information only; no private home details, personal financial data, sensitive traits or guessed personal contacts. Public availability is not blanket permission: source access and intended-use policies must be reviewed and recorded. Keep contacts with source/time; do not infer a person's role/ownership without evidence. No legal compliance claim is made by this design; deployment owner reviews applicable requirements before collection.

Retain global identity memory for duplicate prevention, but avoid copying entire pages or unnecessary personal data. Artifact/log/export retention follows [05](05-LOCAL-STORAGE.md). Privacy requests are owner-controlled local maintenance: halt affected jobs, audit request without sensitive text, remove unnecessary personal contact/body/artifact data transactionally, retain only permitted minimal business identity/tombstone where justified, and document backup expiration/remediation. If identity must be fully erased, explicitly report the resulting duplicate-prevention limitation and obtain a requirement decision; do not falsely promise both complete erasure and permanent matching. No routine Discord delete-business command removes registry history.

## Incident and failure handling

On suspected token disclosure, stop affected output/work, redact stored diagnostics where feasible, instruct owner to rotate through official controls, and record incident metadata. On unsafe fetch/tool attempt, block before effect and fail affected job. On DB corruption or unkillable CLI, halt autonomous execution and require manual recovery. Repeated permission failures do not trigger privilege escalation or resource recreation. Denial reports identify corrective action without revealing credentials.

## Acceptance

T01 tests every authorization surface; T09/T14 instrument all task/subprocess/network boundaries for injection, secret leaks, tool inheritance and fallback; T10 proves SSRF defenses; T16 validates protected backups; T17 proves no external sending. Security review includes logs, crash output, prompts, exports, Discord cards and verification artifacts. Known critical gaps block affected feature release; see [22](22-ACCEPTANCE-CRITERIA.md).
