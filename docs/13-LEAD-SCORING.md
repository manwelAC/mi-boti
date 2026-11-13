# 13 — Lead scoring

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

Implement R07 as deterministic, evidence-backed scoring of [validated intelligence](12-AI-LEAD-INTELLIGENCE.md). Persist immutable scores under [04](04-DATABASE-SCHEMA.md); [17](17-BACKGROUND-JOBS.md) alone awards quota credit.

## Rubric v1

| Criterion key | Weight | Rating anchors (0–5) |
|---|---:|---|
| business_fit | 20 | 0 verified outside target; 3 partial target match; 5 explicit category/geography/service match |
| software_fit | 25 | 0 evidence contradicts proposed service fit; 3 supported integration/workflow opportunity; 5 multiple concrete public workflows fit offered services |
| operational_complexity | 15 | 0 verified simple single workflow; 3 multiple public services/locations/workflows; 5 documented interacting workflows across multiple operations |
| evidence_quality | 20 | 0 no usable evidence; 3 current official source supports key claims; 5 multiple consistent independent observations with clear attribution |
| contactability | 10 | 0 explicitly unavailable/permitted channel absent after verified restriction; 3 published generic business channel; 5 published relevant business contact route |
| opportunity_confidence | 10 | 0 contradicted opportunity; 3 inference with limitations and direct workflow support; 5 exceptionally direct public evidence of stated relevant need |

Every intermediate integer 1/2/4 requires a rationale explaining proximity to adjacent anchors. Complexity is observed public workflow complexity, not revenue, headcount, or inferred internal inefficiency. Evidence of existing software may support integration work; it does not automatically disqualify. Never treat an unknown as rating zero or invent a weak point.

## Formula and unknowns

Each component stores `criterion, weight, rating:int|null, finding_ids[], evidence_ids[], rationale, known:boolean`. Unknown values have rating null and an explicit missing-data limitation. Let K be the known criteria and W their summed weights. `total = round(100 * sum(weight * rating / 5 for K) / W, 2)` if W>0; if W=0 store total 0 with REVIEW_REQUIRED, labelled “unscorable,” not “bad business.” Store coverage W/100 separately in components_json. Display total with coverage, never total alone. Unknowns are excluded rather than scored as weaknesses; minimum coverage and required-known gates prevent inflated qualification.

Qualification requires total >=70, coverage >=0.80, business_fit >=3, software_fit >=3, evidence_quality >=3, opportunity_confidence >=3, all four known; at least one verified public business contact route with evidence; at least two nonduplicated factual observations including one official website or official source identifier with clear business attribution; no unresolved identity or critical evidence contradiction. Contactability must be known when qualifying. Qualification relies on concrete fit, not alleged absence of internal tools. A business without public website can qualify only if permitted official source evidence meets all gates; lack of site never proves lack of software.

Failure of a hard exclusion (outside approved geography/sector, prohibited access, human-rejected candidate) yields UNQUALIFIED with rationale. Missing evidence/coverage or ambiguous semantics yields REVIEW_REQUIRED. Other below-threshold scores are UNQUALIFIED. Only QUALIFIED may create a lead automatically. Manual reviewers may accept/reject a lead with audit rationale, but manual qualification or override never awards hunt quota credit. Only the automatic qualification transaction for an eligible hunt-owned new business may do so.

## Configuration and versioning

Weights must be six finite nonnegative numbers summing exactly 100; mandatory four criteria must have positive weight. Threshold 0–100, minimum coverage 0–1, per-criterion thresholds 0–5. Changing weights/gates creates campaign_versions and a new rubric_version; running hunt snapshots do not change. Persist input finding IDs, rubric and campaign versions, exact components, total, qualification and human-readable rationale. Do not silently recompute historical scores with new weights.

Example: ratings 4/4/3/4/3/3 yield weighted sum 73 and total 73 at full coverage. If contactability is unknown, W=90 and score becomes 74.44 from the remaining weighted sum 67; it still cannot qualify because the public-contact gate is missing. Unknowns affect eligibility through evidence sufficiency, not a claim of poor business performance.

## Acceptance

T15 checks the example, boundary >=70, zero known weights, rounding, invalid weights, unknown contact, missing mandatory criterion, duplicate observations, contradictions, immutable snapshots and per-component citations. T07 confirms score calculation alone cannot grant credit. See [testing](20-TESTING-STRATEGY.md) and [CRM](14-CRM-AND-PIPELINE.md).
