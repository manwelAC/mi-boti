# 14 — CRM and pipeline

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and records

Implement R13 using [leads, notes and events](04-DATABASE-SCHEMA.md), [commands](07-DISCORD-COMMANDS-AND-INTERACTIONS.md), and [outreach](15-OUTREACH-MANAGEMENT.md). One lead per business globally; campaign membership is derived from scores/hunt credits, never duplicate lead rows. Businesses remain in the registry even without a lead.

Lead detail shows current stage and revision, business/parent/branch identity, public contacts with source/time, current and historical scores, facts/inferences/unknowns, notes, research runs, originating hunt and credit if any, drafts and follow-ups. `/lead id:<business-id>` may show a nonlead registry record and pending identity review without inventing a CRM qualification.

## Non-AI MVP qualification

An operator may first use provider-free `/research business:<id> refresh:true` to preserve website observations in the evidence store. The same stored evidence IDs and source timestamps can support manual review and later drafts. An operator uses the manual-qualification action on `/lead id:<business-id>` to review the discovered public evidence and contact route. `LeadService.qualify_manual(actor, business_id, expected_revision, evidence_ids, rationale)` validates identity, same-business evidence, current authorization and a nonempty rationale, then creates a MANUAL lead in NEW and appends a named review event transactionally. It rejects unresolved identity and conflicting revisions. No score is fabricated: current_score_id is null until an actual automatic evaluation exists. The action may mark the business QUALIFIED as a recorded human decision, but it never inserts hunt_credits or advances any hunt. This path makes CRM and manual drafts usable after non-AI Phase 4a and before AI Phase 4b/Phase 5.

## State machine

| Current | Allowed destinations | Required condition |
|---|---|---|
| NEW | REVIEWING, ARCHIVED | Authorized operator |
| REVIEWING | READY, LOST, ARCHIVED | READY requires evidence reviewed and contact route present |
| READY | CONTACTED, REVIEWING, LOST, ARCHIVED | CONTACTED requires explicit manual-send record or operator attestation of an external manual contact |
| CONTACTED | FOLLOW_UP, WON, LOST, ARCHIVED | Follow-up requires a due time; outcome requires note |
| FOLLOW_UP | CONTACTED, WON, LOST, ARCHIVED | Operator action, no automatic sending |
| WON, LOST, ARCHIVED | REVIEWING | Explicit reopen with rationale |

No other transitions are accepted. CRM stages do not rewrite business qualification disposition. Archived leads can retain QUALIFIED evidence while CRM is ARCHIVED; identity checks consider both. Rejected/unqualified businesses remain queryable via business detail. Human rejection updates disposition and business_events, not deletion. Do not auto-reopen or recontact old leads on rediscovery.

## Mutation contracts

`LeadService.transition(actor, lead_id, expected_revision, target_stage, note, attestation?) -> updated_lead` validates current authorization/channel, record scope, legal transition, prerequisites and revision within one transaction. Increment revision and append lead_events atomically. Stale writes return CONFLICT with current version; do not last-write-win. Notes are append-only <=2,000 characters, plain text, author/time recorded; corrections create a new note with supersedes_id. Strip mention effects when rendering, not source provenance.

Identity review selects a known existing business or confirms a distinct business/branch with rationale and optional parent. Persist resolution and new strong claims transactionally; conflicting claim aborts and reloads review. No automatic merging of already-persistent businesses; a future merge workflow requires a separate reviewed migration plan. Review resolution never awards old quota credit.

## Follow-up workflow

`create(lead_id, due_at_utc, note)` stores PENDING, author and revision. A bounded reminder job publishes to configured followups destination when due, transitions to NOTIFIED only after known delivery, and remains open until operator complete/cancel. PENDING/NOTIFIED → DONE or CANCELLED; DONE/CANCELLED are terminal. No automatic external contact or stage advance. A CONTACTED → FOLLOW_UP transaction creates a due item atomically. Completed/cancelled lead follow-ups stay in history.

On restart, recover notification jobs conservatively; safe non-AI reminders may be newly scheduled from due database records after authorization/configuration checks, but research/hunting never resumes. Unique publication keys prevent duplicate reminders. In the MVP, an uncertain send becomes FAILED/DELIVERY_REVIEW_REQUIRED and waits for operator inspection before any resend; marker reconciliation is post-MVP. Future reminders use stored UTC and display operator timezone via Discord timestamps. Timezone-less dates are rejected, not guessed.

## Failure and acceptance

Missing contacts, insufficient evidence and invalid transitions return private actionable errors. Lost channel permissions retain CRM changes and queue bounded output retry; no rollback of verified records because a card failed. Exports are authorized and sanitized under [05](05-LOCAL-STORAGE.md). T12 verifies all transition edges, stale updates, notes/history, nonlead registry details, manual-contact attestation, reminder persistence, reopen and restart without external sends. T06 ensures archives/rejections remain duplicates; T17 verifies outreach restrictions. See [20](20-TESTING-STRATEGY.md).

## Isolated manual CRM core — 2026-11-16

The owner approved isolated unreleased work under README decision D16 while the Phase 4a successful live-Discord check remains open. Domain/crm.py defines the documented graph and bounded UUID/revision/text/due-time validation. Repositories/crm.py implements manual qualification, transitions, append-only note corrections and ten-record pages. Services/crm.py provides ManualCrmService with an injected fresh asynchronous authorizer and transaction-time checks of guild readiness, exact channel/resource mapping and current operator role grants. The trusted authorizer must bind the current actor and verify real membership/resources; returning an arbitrary actor is not production authorization.

Qualification requires an explicit confirmed service call, a current business revision, no unresolved identity hold, one to ten distinct same-business public evidence references and a nonempty human rationale (at most 2,000 characters). Evidence must contain nonempty source-linked facts with positive declared confidence, an observation not in the future, consistent run/candidate provenance and valid excerpt hash metadata when present. This is validation of the operator's evidence review, not an automatic judgment that a business needs software. Old evidence is not silently made fresh; its timestamps remain preserved for human review. It creates one MANUAL/NEW lead with null score, records the named evidence/rationale, marks the business QUALIFIED as a human decision and increments its revision. Origin fields and scores/quota tables are unchanged. Repeated/concurrent qualification cannot create a second lead.

Transition expected_revision refers to the lead revision; manual qualification's expected_revision refers to the business revision. READY requires explicit reviewed evidence and an existing source-backed same-business contact ID. CONTACTED requires a manual-contact attestation; this core never sends anything. CONTACTED to FOLLOW_UP atomically creates a PENDING follow-up with a future offset-aware due time converted to UTC. WON/LOST need outcome notes, and terminal-stage reopen needs rationale. Stale writes/invalid edges/prerequisites roll back completely. Stage changes leave business qualification disposition untouched. Notes are append-only, capped at 2,000 characters and advance the lead revision; corrections refer only to notes on the same lead and retain the original text and author.

This increment is not wired into the bot. The confirmed flag represents an explicit trusted service call in tests; actor-bound Discord preview/confirmation is still required before exposing qualification or pipeline changes. Contact capture/UI, notifications, manual drafts, reminders and exports are not implemented by this core. Pending follow-up rows do not dispatch a reminder or resume any external work on startup. No migration, dependency, provider or configuration-enable switch was added.
