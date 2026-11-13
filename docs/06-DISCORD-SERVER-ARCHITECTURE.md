# 06 — Discord server architecture

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

Define administrator-confirmed server setup for R02/R03. [07](07-DISCORD-COMMANDS-AND-INTERACTIONS.md) is the canonical command mapping, [16](16-DISCORD-UI-UX.md) defines controls, and [04](04-DATABASE-SCHEMA.md) persists every resource.

## Resource manifest

Names are display defaults only. Stable keys map to persisted snowflake IDs.

| Category key / display name | Channel keys / default names |
|---|---|
| control_center / Control Center | dashboard, bot-control, subscription-usage |
| lead_hunting / Lead Hunting | campaigns, lead-discovery, business-research, qualified-leads |
| sales_crm / Sales & CRM | lead-pipeline, outreach-drafts, follow-ups |
| system / System | bot-settings, activity-logs |

All channels are guild text channels. `dashboard` is output/persistent-control only; `activity-logs` is read-only for humans. `qualified-leads` is bot-output with permitted slash use. `bot-settings` is administrator-only. Other channels permit operator slash use, with ordinary text sending disabled by default to reduce noise; modals handle notes. Deny @everyone View Channel on managed categories by default; grant owner/admin/operator visibility as appropriate. The bot needs View Channel, Send Messages, Embed Links, Attach Files, Read Message History, Manage Channels and Manage Roles (for channel permission overwrites). Never request Administrator merely to avoid permission analysis. No guild-role assignment or unrelated role/channel management is implemented. Guild administrators retain platform privileges, but service checks still apply. Real permission behavior remains subject to L01.

## Setup plan contract

`SetupPlan(id, guild_id, actor_id, expires_at, config_revision, changes[], permissions[], warnings[], hash)` lists create-category, create-channel, overwrite-change, mapping-change, and panel-publication actions. Each action has a stable resource key and expected prior state. The confirmation TTL is five minutes. Confirm/cancel buttons bind actor, guild, plan ID and hash. Confirming as another member, after expiration, after revision change, or after permission/resource drift rejects with a new-preview instruction. No partial reuse of stale approval.

Initial `/setup` accepts only configured-guild owner/admin in a guild text channel; operational readiness is exempt solely for this bootstrap/recovery command. After READY it belongs in mapped bot-settings. If bot-settings is deleted/inaccessible, owner/admin may invoke recovery elsewhere in the configured guild; the response is private and grants no other command exception.

## Idempotency and reconciliation

Inspect persisted resources by ID, existing guild structure, permissions and bot-owned markers. A renamed mapped channel remains valid. A same-named unrelated channel is not authoritative: show conflict in preview and offer explicit adoption by ID with overwrite differences, or approved creation of a distinctly identified managed resource. Never silently adopt by name or modify an unrelated category.

After confirmation, persist plan CONFIRMED then APPLYING. Journal each step before Discord mutation; persist resulting ID immediately afterward. Create categories before children. Repeating setup skips confirmed existing resources. On a crash after creation but before ID storage, reconcile an opaque setup marker in channel topic/category metadata where possible plus plan journal; if ownership cannot be proven, mark UNCERTAIN and ask administrator to select the correct resource in a fresh preview. Do not guess or duplicate.

Deleted mapped resources become MISSING, invalidate readiness for affected commands and block dispatch to them. Runtime monitoring never recreates them. A recovery preview explicitly lists deleted resources, proposed replacements, overwrite changes, destination changes and panel republishing; administrator confirmation is required. A permission loss yields PARTIAL with completed resources retained. Retrying produces a new plan for outstanding actions. No automatic rollback deletes already-created channels that may now contain operator work.

## Mapping and output configuration

`command_channels` uses canonical command keys; `output_destinations` uses dashboard, hunt_progress, research, qualified_leads, pipeline, drafts, followups, usage, activity. Defaults map respectively to dashboard, bot-control, business-research, qualified-leads, lead-pipeline, outreach-drafts, follow-ups, subscription-usage, activity-logs. Destination and command mappings can differ after explicit admin configuration. Validate selected IDs exist in the configured guild, are text channels, have required bot permissions, and comply with visibility policy. Persist revision, audit change, invalidate stale controls, and require jobs to resolve current destinations at dispatch. Never expose private drafts to a newly public channel without rejecting the unsafe mapping.

## Acceptance

T02 runs initial setup, repeated setup, rename, unrelated name collision, deleted channel, permission failure, stale confirmation and mid-provision crash. Expected: no unapproved mutations, no duplicates, IDs persisted, correct partial recovery, unrelated resources untouched. T01 confirms readiness failures enqueue no work. Real sandbox-guild verification is separately required in [20](20-TESTING-STRATEGY.md).

## Phase 2 implementation and recovery controls

The initial manifest is four categories and twelve text channels. Four mandatory panels are published in dashboard, bot-control, subscription-usage and bot-settings. The implementation preserves custom ID mappings, and `/config set` stages role/mapping changes as an administrator-confirmed setup preview rather than applying permission changes silently. Up to ten configured owner IDs and ten existing operator-role IDs are supported by the current permission profile; @everyone cannot be an operator grant.

`/setup` accepts optional resource_key/resource_id for explicit adoption, resolution=recreate for reviewed uncertain-resource recovery, and operator_roles as comma-separated IDs or none. For an uncertain panel, resource_key is panel.dashboard, panel.hunt_progress, panel.usage or panel.settings. Recreate is an explicit operator assertion that the prior resource/message is absent after inspection; the bot never infers absence from an unconfirmed response. Adopting a category that contains unmanaged children is blocked so its overwrite changes cannot affect unrelated channels. Name conflicts create a distinctly identified new resource, without adopting the existing name match.

Previews bind actor, guild, invocation channel, configuration revision, snapshot fingerprint and hash, with the configured five-minute expiry. A change to roles, bot permissions, channels or configuration invalidates a pending approval. Provisioning is a single bounded worker, limited to 180 seconds with 15-second individual Discord requests. The setup_plans/setup_steps journal is its durable state; it does not enqueue a generic hunting job or add an undocumented job kind. Each external mutation is journaled first. Authorization is rechecked before resources, panels and final readiness; an interruption records PARTIAL/UNCERTAIN and never restarts automatically. Final resource, parent and overwrite checks precede an atomic READY/COMPLETED commit.

Local fake-transport/real-SQLite tests cover this behavior. The actual guild overwrite hierarchy, command synchronization, live component behavior and rate limits are not verified until L01 is executed with a regenerated local token.
