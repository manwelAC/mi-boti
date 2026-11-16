# 07 — Discord commands and interactions

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and common contract

This is the single canonical command/channel registry for R03 and the user interface in [16](16-DISCORD-UI-UX.md). Names are defaults; authorization uses `command_channels.resource_id` joined to persisted snowflakes, never channel names. [06](06-DISCORD-SERVER-ARCHITECTURE.md) alone defines the `/setup` exception.

For every command/component: reject DMs and foreign guilds → obtain current member → validate role/action permission → lookup mapped channel → require exact channel ID (threads do not inherit permission) → validate configuration/resources → validate typed arguments → acknowledge/defer privately before long work → enqueue idempotently. Target acknowledgment within two seconds and verify the actual platform deadline in the live Discord test. No network research, CLI execution or slow database maintenance in handlers. Wrong channel: ephemeral `Use <#channel_id> for this command.` If unavailable/unmapped: `Command is not configured; ask an administrator to run /setup.` No job is created.

## Canonical registry

`O` = operator; `A` = owner/administrator. Subactions inherit the root mapping except hunt commands, which have explicit keys.

| Command key | Default channel | Permission | Arguments and behavior |
|---|---|---|---|
| guide | guide | O | `/guide`; private tool guide with mapped channels, usage, result explanations and unavailable-feature labels; creates no jobs |
| hunt.start | bot-control | O | `/hunt start quota:<int> campaign:<id?>`; default active campaign from config; start bounded session |
| hunt.pause | bot-control | O | `/hunt pause session:<id?>`; request checkpoint pause |
| hunt.resume | bot-control | O | `/hunt resume session:<id?>`; fresh eligibility, resume PAUSED/INTERRUPTED |
| hunt.stop | bot-control | O | `/hunt stop session:<id?>`; cancel and summarize |
| hunt.status | bot-control | O | `/hunt status session:<id?>`; current/last session counters and reason |
| campaign.create | campaigns | O | `/campaign create name:<text>`; modal targeting and geography; provider/rubric inputs are optional or disabled for non-AI campaigns |
| campaign.list | campaigns | O | `/campaign list`; private paginated summaries |
| campaign.edit | campaigns | O | `/campaign edit campaign:<id>`; versioned modal, archive option |
| discover | lead-discovery | O | `/discover campaign:<id> limit:<int?>`; discovery-only job, no AI |
| research | business-research | O | `/research business:<id> refresh:<bool> analyze:<bool?>`; existing record requires true; default analyze:false collects evidence without AI; analyze:true requires Phase 4b/provider gates |
| qualified | qualified-leads | O | `/qualified campaign:<id?> page:<int?>`; evidence-linked qualified leads |
| leads | lead-pipeline | O | `/leads stage:<enum?> page:<int?> export:<bool?>`; export option enqueues CSV job |
| lead | lead-pipeline | O | `/lead id:<lead-or-business-id>`; detail, history, notes, identity review and manual-qualification actions |
| pipeline | lead-pipeline | O | `/pipeline lead:<id> stage:<enum> expected_revision:<int>`; validated transition |
| outreach | outreach-drafts | O | `/outreach action:<create|generate|view|edit|approve|reject|record-sent> lead:<id> draft:<id?>`; edit via modal |
| followup | follow-ups | O | `/followup action:<create|list|complete|cancel> lead:<id?> id:<id?> due:<ISO8601?>`; note modal |
| usage | subscription-usage | O | `/usage provider:<id?>`; explicit bounded allowance-status probe, no AI task |
| connections | subscription-usage | O/A | `/connections action:<status|verify> provider:<id?>`; status O, verify A; real verification never automated auth |
| config | bot-settings | A | `/config action:<view|set> key:<enum?> value:<text?>`; allowlisted mutable settings only |
| setup | bot-settings | A | `/setup`; preview then confirmation, restricted bootstrap/recovery exception |
| backup | bot-settings | A | `/backup action:<create|verify|list> id:<id?>`; no restore/destructive download by arbitrary path |

`dashboard` and `activity-logs` have no operational slash commands. Every key above must have a persisted mapping before READY. Per-action permissions apply to `/connections verify` despite sharing its root mapping.

## Non-AI research behavior

In the MVP, `/research business:<id> refresh:true` enqueues a bounded RESEARCH collection job in business-research with analyze defaulting to false. It validates identity, source permission/robots, safe URL/DNS transport, resource budgets and cancellation, then stores immutable evidence and returns a source-linked research card. It requires neither a selected provider nor authentication/allowance checks. It never calls a CLI, creates AI findings/scores, automatically qualifies a lead, or awards quota credit. Operators can use the stored evidence for manual CRM review and manual drafts.

`analyze:true` is an explicit post-collection Phase 4b request. In the non-AI release, reject that option privately before enqueueing it and explain that AI analysis is disabled; suggest retrying with analyze:false. In an AI-enabled release, collection and evaluation remain separate checkpoints. If allowance verification or AI analysis later fails, retain the successfully collected evidence and report analysis as blocked/failed without trying another provider. Both modes require the same mapped channel and authorization checks. Missing official website or unsafe/disallowed access returns a limitation; the command never guesses a URL or bypasses access policy.

## Argument and component rules

UUIDs must identify existing records in this deployment; return a private not-found message without leaking foreign data. Quota 1–100, manual discovery limit 1–100 (default 25), names 1–80 Unicode characters, notes <=2,000 characters, pagination 1-based with <=10 records per page. Campaign geographic bounds must be finite valid latitude/longitude ranges with a maximum 1-degree-square bounding box and at most 100 approved source tags; larger work requires explicit configuration review. Reject newline/control-character executable paths and any free-form query language. Follow-up times need timezone offsets and must be future instants, converted to UTC. Reject unknown enum keys rather than accepting free-form config or SQL.

Buttons/selects/modals carry opaque IDs and revisions, not trusted authorization. Recheck guild/channel/member/record/state on submit. A panel in dashboard links users to the correct command channel; it does not execute bot-control operations from dashboard. Stale revisions return current status and require retry. Confirmation is actor-bound and expires. Replayed interaction ID returns existing job/status, not a duplicate.

`/lead` manual-qualification action requires source-linked public facts, explicit review rationale, expected business revision and confirmation; it creates one MANUAL CRM lead with no AI score or quota credit. `/outreach action:create` opens a manual-draft modal and works with AI disabled. The generate action alone requires a verified provider. Disabled AI actions explain the missing L02 gate. `/lead` identity review actions choose existing business or create separate entity after inspecting signals; they never merge two persistent businesses automatically and never earn quota. Refresh options are explicit and display the no-credit warning. `/config set` supports mapping/destination IDs, active campaign, operator roles and safe policy/rubric settings under [23](23-IMPLEMENTATION-GUIDELINES.md); executable paths, tokens, guild binding, and arbitrary files are local-only.

## Failure and acceptance

All denials are ephemeral and include actionable guidance without secrets. Busy hunt, unknown allowance, invalid quota, stale revision, permission loss and missing mappings produce no prohibited work. Long-running results go to configured private managed destinations and a private job receipt. T01/T03 enumerate every registry key and test wrong guild/channel/role/DM/thread, stale component, incomplete config, and replay; T02 separately tests setup exceptions. See [20](20-TESTING-STRATEGY.md).

## Current Phase 2 command surface

Phase 3 adds `/lead id:<review-or-business-or-lead-UUID?> page:<int=1> action:<inspect|link|separate=inspect> target:<business-UUID?> rationale:<text?>` in lead-pipeline. Without an ID it lists up to ten open identity reviews per page. Inspection shows source assertions, observation time, address, possible matches and current revisions; business inspection lists up to ten related open reviews. A link or separate action requires an OPEN review ID and a 1–1,000-character rationale. Linking also requires a target business ID. Both return a private decision preview and actor-bound confirmation expiring after five minutes. Confirmation repeats live authorization and resource checks; linking checks the previewed target revision inside the transaction. Duplicate clicks cannot resolve twice. These transient confirmations expire on restart; rerun /lead to obtain a new preview. No persistent businesses are merged, and no lead, research run, score or quota credit is created. CRM notes/history/manual qualification remain later-phase work.

All 22 canonical keys are registered as guild-scoped slash commands and share the policy boundary. The implemented actions are setup previews/confirmations, config view, confirmed role/channel-mapping configuration, and truthful disabled-state responses for usage, connections status and hunt status. `/connections verify` additionally checks administrator authority but performs no CLI task. Other workflows are explicit placeholders: their eventual arguments/actions above remain contracts for later phases, and the current placeholders do not enqueue jobs or expose an execution bypass.

`/setup resource_key:<key?> resource_id:<snowflake?> resolution:<inspect|recreate> operator_roles:<IDs|none?>` provides reviewed adoption/recovery. `/config action:<view|set> key:<string?> value:<string?>` currently supports operator_role_ids, command_channel.<canonical_key> and output_destination.<output_key>. Channel targets must already be active managed text channels; adopting an unrelated resource requires `/setup` and its own preview. Unsupported config keys, tokens and executable paths are rejected before persistence. Other mutable settings remain later-phase work.

The transport privately defers before metadata/database work, then reloads membership, role permissions, resource IDs, channel overwrites and control-panel availability. Wrong guild/channel/member/permission or incomplete configuration never creates operational jobs or mutates operational records. A separate redacted denial audit is permitted and required by the security contract. Actor-bound confirmation is the only path to the durable setup worker. A lost response does not replay a confirmed job. All unimplemented discovery, research, CRM, backup-command and AI workflows remain disabled.

The owner-requested guide adds a 22nd canonical command key. Its channel is private and read-only for ordinary text, while /guide and the persistent Read tool guide button remain usable by authorized operators. The help catalog must cover every canonical key and fit native Discord embed limits. Future workflows are labelled unavailable; help examples do not authorize or enable them.
