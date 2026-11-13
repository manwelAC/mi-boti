# 08 — Business discovery

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and source boundary

Implement R04/R05 with [registry schema](04-DATABASE-SCHEMA.md), [safe HTTP](09-WEB-RESEARCH-ENGINE.md) and [hunt budgets](17-BACKGROUND-JOBS.md). Sources are free and must permit intended automation. No paid discovery, billing-dependent Google Places, commercial search subscription, or systematic public Nominatim harvesting.

## Initial market and Phase 0 probe — 2026-11-14

The owner confirmed that the initial market is the Philippines (PH). Singapore is not the selected target market. Display timezone configuration is independent of discovery geography. For a technical feasibility fixture only, the manually initiated probe used restaurants in a small Makati bounding box (south 14.550, west 121.015, north 14.565, east 121.035); this does not choose the final campaign's city or industry.

The selected endpoint was `https://overpass-api.de/api/interpreter`. The [operator's public-instance guidance](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) and [OSM licensing/attribution page](https://www.openstreetmap.org/copyright) were reviewed before the probe. The guidance permits small manual queries but explicitly warns against using public instances as a general application backend. A successful small query would therefore not approve ongoing production hunting; source selection, sustainable access and limits remain OPEN under D12.

The query used JSON output, a 15-second server timeout, 16 MiB declared server memory, a maximum of ten returned elements, a 25-second client socket timeout, a 1 MiB response cap and a descriptive Mi Boti feasibility user-agent. Its SHA-256 fingerprint was `b91ed18771fe756a4777b96bfce3b8190679b836dbdf946a02c1b5147663a2cd`. It requested only nwr elements with amenity=restaurant in the stated bounding box. The probe used direct HTTPS with environment proxies disabled and made no Nominatim or paid API requests.

Actual results: attempt 1 returned HTTP 502 after 0.74 seconds; one retry, started at least ten seconds after the first, raised TimeoutError after 26.52 seconds (the 25-second socket timeout is not an exact end-to-end deadline). Both attempts used the same endpoint. The probe stopped after those two attempts without endpoint rotation. No successful response, business count, qualified lead, contact or website evidence was obtained. This is a failed live connectivity/source probe, not a passed discovery integration or proof of an empty Philippine market.

The intended attribution is © OpenStreetMap contributors, with a link to the copyright/ODbL notice. The transient probe scripts/results stay outside the application source tree; no discovery adapter, database, registry entries or autonomous hunt was created. A future small retry may occur only as a bounded explicitly tracked probe; the current failure must not be silently reported as L03 success.

## Source interface and policy

`DiscoverySource.capabilities() -> SourcePolicy`; `plan(campaign_snapshot, coverage) -> bounded QuerySpec[]`; `discover(QuerySpec, budget, cancel) -> DiscoveryBatch(observations, attribution, exhausted, partial, error?)`. `QuerySpec` contains approved source ID, bounded bounding box/cell, allowlisted OSM tags, request fingerprint and policy version. `BusinessObservation` contains source namespace/ID, name, address fields, website/phone/email if explicitly published, coordinates, observed_at UTC, source URL, attribution and limitations. Raw source values remain untrusted.

Each source policy records endpoint/host allowlist, documented permission/licensing URL, review timestamp, allowed query patterns, attribution text, request and daily budget, concurrency, max response bytes, cache TTL, retry policy and contact user-agent. Unknown/expired policy disables that source. Phase 0 reviews current policies and records evidence; this specification makes no claim that a particular public Overpass instance accepts production load.

Overpass is primary: use one configured approved endpoint, fixed templates, explicit bounded spatial predicates and allowlisted tags. Never interpolate arbitrary user query syntax. The default ceiling is one request at a time, at least ten seconds between starts, 30-second timeout, response <=5 MiB, total bounded by the hunt's snapshotted quota-scaled discovery-request budget, including retries (50 at quota 25 by default). The approved source policy may lower these limits; raising them requires reviewed policy evidence. Respect Retry-After within remaining budget, otherwise stop. Do not rotate public endpoints to evade limits. Official sites mainly enrich discovered businesses; only explicitly permitted directory adapters may expand discovery.

## Query planning and history

Normalize tag order, campaign targeting version and geographic cell into a SHA-256 query fingerprint. Persist discovery_queries before dispatch; increment attempt/request counters before each attempt. Save result count, status and source attribution even on partial responses. Store coverage_cells for successful/partial searches. The coverage freshness is 30 days; skip already fresh cells across sessions for matching target fingerprints. Broader/smaller campaigns may consult intersecting prior coverage, but do not claim complete coverage from partial results. Exhaustion means the bounded configured search plan is exhausted, not every business in a region is known.

## Identity resolution

1. Validate minimally meaningful name and source provenance; persist invalid observations with reasons. Stable source namespace/ID is a strong signal; OSM node/way/relation prefixes remain distinct.
2. Normalize domain via parsed HTTP(S) hostname, lowercase/IDNA, remove standard port and only a leading `www.`; preserve raw URL and full domain. Do not collapse hosted tenants or branches by registrable domain alone.
3. Normalize names using Unicode NFKC, casefold and whitespace/punctuation normalization; preserve legal/raw name. Normalize address fields separately, including country/postcode/unit; missing unit makes address weaker. Phone: retain published value; canonical E.164 only when country context is sufficient, otherwise supporting raw normalized digits. Email normalization preserves local-part text; domain lowercased. No guessed contacts.
4. Exact strong claim match with consistent branch/address → Existing. Source disagreement or conflicting branch/address → Ambiguous. Exact normalized full name+complete address may claim identity only with no contradictory signals. Shared domain/phone alone cannot merge.
5. The similarity rule is token Jaccard name similarity >=0.85 plus one shared address/domain/phone signal creates review, never automatic merge. All unresolved conflicting evidence creates identity_reviews and AMBIGUOUS candidate.
6. With no plausible existing match, transactionally insert business, identifiers, strong claims and immutable origin_job_id/origin_hunt_id. Recheck signals within the write transaction. Unique conflict reloads the winner and marks Existing. Records with weak identity and plausible overlap are held, not force-inserted to fill quota.

Parent and branch businesses have separate IDs and parent_id. A directory headquarters and branch with shared domain/phone are held if location is unclear. Every disposition participates in lookup. Existing records receive a new discovery event/provenance but no automatic research. Persist ambiguous candidate fingerprints and consult prior reviews across queries to avoid repeated work; a prior unresolved observation yields the same pending review rather than new research. Human resolution creates a separate business or links existing with an audit rationale; no retroactive hunt credit.

## Failure and acceptance

Retry only transient network/429/5xx failures within source and job budgets, at most three total attempts with bounded backoff; do not retry forbidden access, schema mismatch, or invalid query indefinitely. Empty/duplicate-only results advance coverage; exhausted plans end hunt with SOURCE_EXHAUSTED. Outage across remaining plan yields SOURCE_UNAVAILABLE with partial counts. T05 verifies policy, limits, provenance, coverage and no paid endpoint; T06 races identity inserts and tests shared-domain branches, archived/rejected records, changed URLs and ambiguous matches; T07 verifies discovery-only records cannot later count as new. See [20](20-TESTING-STRATEGY.md).

## Phase 0 follow-up assessment — 2026-11-14

One later, separately bounded GET probe used the same Overpass endpoint and Makati restaurant fixture, reduced to five output elements and a ten-second server timeout. Its 18-second client socket timeout expired after 18.46 seconds. There was one attempt and no endpoint rotation or retry. L03 connectivity is still FAILED, not evidence of an empty Philippine market. Production source approval remains OPEN, and no source adapter is enabled.

The official Geofabrik page confirms a Philippines OSM regional extract is available as a possible local/offline discovery source. Only the public metadata page was reviewed; no large dataset was downloaded and no importer was implemented. This remains an OSM-source feasibility option requiring policy/licensing, update-budget and parser validation before Phase 3. It is not an approved replacement silently selected for the operator. The public Overpass operator's warning about sustained general-application backends remains material even if a small future query succeeds.

Sources reviewed: [Overpass operator guidance](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html), [OSM licensing](https://www.openstreetmap.org/copyright), and [Geofabrik Philippines metadata](https://download.geofabrik.de/asia/philippines.html). No paid discovery source or Nominatim harvesting was used.

## Prerequisite policy recheck — 2026-11-14

The current official Overpass commons guidance was reviewed again. It distinguishes small manually submitted queries from sustained general-application backend use and still identifies the latter as problematic. Passing a bounded manual query would establish connectivity only, not production source approval. The official Geofabrik Philippines page lists a public regional PBF extract; its existence does not establish importer compatibility or authorize an automatic download. OSM attribution and ODbL requirements remain part of either source path. Only the policy/metadata pages were read during this checkpoint; no interpreter query or dataset download was performed and D12 remains OPEN.

Primary references: [Overpass commons](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html), [Geofabrik Philippines](https://download.geofabrik.de/asia/philippines.html), [OSM attribution and licensing](https://www.openstreetmap.org/copyright).
