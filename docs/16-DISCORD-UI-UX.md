# 16 — Discord UI/UX

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and ownership

Specify native Discord presentation for [commands](07-DISCORD-COMMANDS-AND-INTERACTIONS.md), [setup](06-DISCORD-SERVER-ARCHITECTURE.md), [hunting](17-BACKGROUND-JOBS.md), and [CRM](14-CRM-AND-PIPELINE.md). Discord is the entire interface; no web dashboard or public admin link.

## Panels and cards

| Destination key | Default channel | Contents |
|---|---|---|
| dashboard | dashboard | Readiness, active campaign, last hunt, queued work, links to assigned command channels |
| hunt_progress | bot-control | Session ID, state, quota credit, seen/new/duplicate/ambiguous/unqualified counts, remaining resource budgets, active time, absolute age and stop reason |
| usage | subscription-usage | Provider/version, verification state, allowance observation/expiry, actual reported windows or Unknown |
| research | business-research | Phase 4a source-linked observations, confidence, limitations and run ID; Phase 4b adds labelled AI inferences/unknowns only after explicit gated analysis |
| qualified_leads | qualified-leads | Business/branch, score plus coverage, rationale, evidence, lead ID, originating session |
| pipeline | lead-pipeline | Stage, next action, review status, notes/history navigation |
| drafts | outreach-drafts | Versioned copyable draft, evidence, Review/Approve/Reject/Record manual sending |
| followups | follow-ups | Due time, lead reference, Complete/Cancel, manual-action reminder |
| activity | activity-logs | Redacted setup, job, security, lifecycle and CRM events |

Default destinations can be changed by authorized administrators using persisted IDs. An action is executed only in its assigned command channel; cards elsewhere provide a channel link instead. Dashboard navigation never bypasses bot-control checks.

## Interaction behavior

Slash handlers defer privately for jobs and immediately return job/session IDs with a status route. Do not wait for a CLI or fetch to finish. Setup embeds show precise proposed resources, overwrites, adoptions, mapping changes and warnings, with actor-bound Confirm/Cancel expiring after five minutes. Hunt controls reflect RUNNING/PAUSING/PAUSED/INTERRUPTED/terminal state, and stop requires confirmation showing retained count. Start previews the quota-scaled effective limits. Resume states its fresh allowance check and remaining active/age budgets; paused time is not displayed as active use. Disabled controls explain why in text.

Persistent custom IDs use a versioned opaque form `mb:v1:<action>:<record_uuid>:<revision>` with an action allowlist and no secrets. Register views on startup from panels/publications records. IDs are routing hints, not authority; live member/guild/channel/resource/state/revision checks run again. Modal submissions include a server-side stored request context with expiry and actor binding. Deleted panel messages are reported MISSING and republished only through authorized recovery, not by channel recreation.

CRM detail uses pages for overview/evidence/history/notes. Select menus contain bounded options and pagination. Long evidence is summarized with a source link and stored full text, never silently truncated in persistence. The page size is <=10 items; all generated messages are tested against current Discord component/embed/message limits during L01. Renderer splits content before sending and falls back to a sanitized attachment for authorized users, never public external hosting.

## Safety, accessibility and update policy

Use plain labels plus text state, not color alone. Include observation dates and distinguish Unknown from zero. Show score with evidence coverage and limitations. Escape Markdown control content as needed, disable allowed mentions, and treat page titles/business names as untrusted. Do not expose filesystem absolute paths, auth transcripts, private config or raw exceptions. Draft and contact cards remain in managed private channels.

The progress edit interval is >=10 seconds; coalesce intermediate changes, respect library rate limits, and send a final summary after terminal state. Never count messages as leads. Permission/API failures with known safe-to-retry outcomes persist notification jobs with bounded retries; show degraded notification status in local logs and next authorized status response. An uncertain send is held FAILED/DELIVERY_REVIEW_REQUIRED for operator inspection in the MVP; marker-based reconciliation/UNCERTAIN delivery is post-MVP. Lost interaction token does not lose the persistent job; completion publishes to its configured destination.

## Acceptance

T03 validates persistent controls after restart, actor-bound confirmations, expired modals, forged IDs, revision conflicts and correct-channel routing. T01 ensures components reject unauthorized work. L01 inspects actual private responses, pagination, mentions, message limits, setup preview and progress. T13 verifies restart restores controls without resuming hunting. See [testing](20-TESTING-STRATEGY.md).

## Tool guide channel

The owner requested a persistent place to learn every tool. The guide panel lists each command, its purpose, assigned channel, current availability and usage. It explains record IDs, duplicates, invalid observations, incomplete coverage and manual outreach. The dashboard has a Tool guide link; the guide offers a persistent Read tool guide button and /guide for a private copy. No walkthrough starts discovery, qualifications or hunting. Public channel provisioning remains subject to the confirmed setup contract in doc 06.

The guide's existing saved message can be explicitly refreshed by an authorized owner/administrator with /guide refresh:true. Only that bot-owned managed message may be edited; missing/unowned targets are not recreated. Normal reads remain private, and startup remains free of publication side effects. Saved research results have an evidence dropdown and 1,200-character excerpt pages. Native embed size limits, mention escaping, actor/expiry binding and fresh channel/member authorization apply on every page. Source links refer to actual observed URLs; excerpts are immutable and browsing starts no network work.
