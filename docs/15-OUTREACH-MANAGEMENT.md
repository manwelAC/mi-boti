# 15 — Outreach management

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and nonnegotiable boundary

Implement R14: evidence-grounded draft preparation and human review. **Mi Boti has no external sending capability.** No SMTP, email provider, social API, Discord user-DM prospecting or automatic campaign sender is configured. Operator copies reviewed text and manually sends outside Mi Boti. [CRM](14-CRM-AND-PIPELINE.md) records that act; [provider gate](10-AI-PROVIDER-INTEGRATION.md) still applies to generation.

## Draft contract

`generate(actor, lead_id, expected_lead_revision) -> job_id` requires an authorized operator in outreach-drafts, a real lead with reviewed public evidence, nonarchived stage, eligible pinned provider and fresh allowance. Use a DRAFT TaskRequest containing only verified facts, explicitly labelled possible opportunities, contact context actually published, and approved service description from campaign settings. No claims of existing relationship, proprietary knowledge, guaranteed ROI, internal shortcomings or invented decision-makers.

Output JSON contains `body` (<=4,000 characters), `evidence_ids`, and `limitations`. Validate all referenced evidence belongs to the lead, factual personalization is supported, unverified hypotheses remain conditional, and no secrets or hidden instructions appear. Persist a versioned DRAFT and show citations/limitations separately from copyable text. A failure preserves no approved draft and reports its reason. `/outreach action:create lead:<id>` opens a manual-writing modal and works for MANUAL leads without an AI score. Manual writing/editing is allowed without AI and creates the same reviewable DRAFT state; it does not bypass evidence standards.

## States and review

| From | Action | To and effect |
|---|---|---|
| DRAFT | edit | New version DRAFT; old version retained and marked REJECTED with supersession event |
| DRAFT | approve | APPROVED with actor and UTC approval time |
| DRAFT | reject | REJECTED with reason in lead_events |
| APPROVED | edit | New DRAFT; prior APPROVED becomes REJECTED/superseded; approval does not transfer |
| APPROVED | reject | REJECTED; no sending occurs |
| APPROVED | record-sent | MANUALLY_SENT with named operator/time and explicit attestation |
| MANUALLY_SENT or REJECTED | revise | New DRAFT; historical state retained |

Approval validates current draft ID/version, lead revision, contacts and evidence; reject stale/changed input and require renewed review. An operator may approve their own draft under D06 in the README; the named human review is mandatory. Every action is audited. Approval UI says “Approved for you to copy and manually send”; no Send button exists. A copy operation has no network side effect.

`record-sent` opens an actor-bound confirmation requiring “I manually sent this outside Mi Boti,” actual UTC/offset timestamp and optional nonsecret note. It never claims delivery verification. It may transition READY → CONTACTED when allowed, and optionally create a follow-up within the same transaction. If lead stage changed concurrently, reject the stage update and request review rather than silently altering it. Recording an already-sent draft twice returns existing record. A CRM contact not based on a generated draft can be recorded via a pipeline attestation with the same audit requirement.

## Security and failure behavior

Use private managed draft visibility and ephemeral confirmations. Disable mentions and automatic URL previews where supported. Scraped text cannot add recipients or invoke tools. Provider failures never use another provider or a sending API. Unauthorized, stale, unsupported or unapproved record-sent actions fail with no mutation. Follow-ups only remind inside Discord; they never send the draft automatically.

## Acceptance

T17 tests generation evidence, edit invalidation, approval actor/time, stale versions, record-sent attestation/idempotency, manual drafting without AI, and missing approval. Instrument all external transports to prove approval, copy, reminders, restarts and record-sent produce zero outreach transmissions. T09 proves no metered fallback when draft allowance is unknown. See [20](20-TESTING-STRATEGY.md).
