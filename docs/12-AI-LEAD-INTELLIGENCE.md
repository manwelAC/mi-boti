# 12 — AI lead intelligence

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and responsibilities

Turn [public evidence](09-WEB-RESEARCH-ENGINE.md) into validated findings and [explainable scores](13-LEAD-SCORING.md). AI suggests structured findings; deterministic application code validates provenance, gates qualification and computes scores. [Provider gate](10-AI-PROVIDER-INTEGRATION.md) is mandatory.

## Input and output contract

Input is a bounded immutable evidence bundle: business ID/name, known branch/parent context, source IDs/URLs, UTC observations, excerpts, confidence, limitations, targeting snapshot and rubric version. Surround retrieved text with explicit untrusted-data delimiters. Instructions prohibit inventing facts, executing tools, following website instructions or inferring missing internal systems. No private configuration or secrets are included.

Expected output JSON (unknown keys rejected):

```json
{
  "schema_version": 1,
  "business_id": "UUID",
  "findings": [
    {"kind": "FACT", "statement": "Public services include multiple appointment types.",
     "evidence_ids": ["UUID"], "confidence": 0.9, "limitations": []},
    {"kind": "INFERENCE", "statement": "Coordinating those services may present a scheduling integration opportunity.",
     "evidence_ids": ["UUID"], "confidence": 0.6,
     "limitations": ["Internal workflows have not been observed."]},
    {"kind": "UNKNOWN", "statement": "Internal software stack is unknown.",
     "evidence_ids": [], "confidence": 0.0, "limitations": ["No public evidence."]}
  ],
  "criterion_suggestions": [
    {"criterion": "software_fit", "rating": 3, "finding_indexes": [1],
     "rationale": "Potential integration fit, conditional on operator review."}
  ]
}
```

Limit 30 findings, 1,000 characters per statement, confidence [0,1], six criterion suggestions, no HTML or executable fields. Evidence IDs must exist in the input bundle and belong to the same business/run or explicitly included historical context. FACT requires at least one direct observation supporting its wording; INFERENCE requires supporting evidence plus stated uncertainty; UNKNOWN cannot support a positive opportunity claim. AI cannot create URLs, phone numbers, ownership, revenue, contacts or new source IDs. Public facts that disagree are preserved with limitations rather than arbitrarily resolved.

## Validation and qualification workflow

Validate schema, business identity, evidence membership, confidence and bounds before persistence. Reject unsupported definitive claims, especially “no software/CRM/booking” based solely on absence. Code can enforce forbidden forms and evidence relationships, but semantic validation is not perfect: retain supporting excerpts and an operator review path; uncertain semantic support yields REVIEW_REQUIRED rather than autonomous qualification. No AI self-attestation substitutes for evidence.

Store findings immutable, compute criterion values from validated suggestions using the rubric, and persist score with per-component rationale. Qualification requires all gates in [13](13-LEAD-SCORING.md), not the AI's own qualification label. No provider task gets to increment counters or update CRM directly. A new valid qualification enters NEW for human CRM review, not approval to contact.

Malformed output fails the task; one bounded repair task may be scheduled only with a new allowance check and remaining request/task budgets. It receives validation errors plus the same evidence, not permission to fabricate missing fields. A second invalid response ends evaluation as REVIEW_REQUIRED or FAILED with no credit. Provider exhaustion/unknown does not permit repair. Empty or insufficient evidence creates an unqualified/review result with limitations and persistent business memory.

## Refresh and history

Explicit refresh creates a new research run and score. A changed score never deletes previous rationale or credits; existing records cannot regain new status. Human rejection records a business event and disposition; it does not erase evidence or restart research automatically. A branch's evidence may mention a parent only with explicit relationship and limitation; do not treat parent-wide capabilities as branch-specific facts automatically.

## Acceptance

T11 injects fabricated contacts, foreign evidence IDs, missing source timestamps, prompt injection, unsupported absence claims, contradictory pages and malformed output. Expected: rejection/review, no fabricated facts and no credit. T08 verifies allowance before repairs. T15 checks all scores cite evidence and unknowns do not count as weaknesses. See [20](20-TESTING-STRATEGY.md).
