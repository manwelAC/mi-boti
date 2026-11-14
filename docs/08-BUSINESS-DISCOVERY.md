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

## Quezon City fixture and Phase 3 core — 2026-11-14

The owner selected Quezon City restaurants and cafes as the first fixture, not a permanent market restriction. The bounded connectivity check used a small test box (south 14.648, west 121.047, north 14.657, east 121.061), not the full city or an administrative boundary guarantee. Its query used restaurant/cafe amenities, a ten-second server timeout, 16 MiB server memory ceiling, five output elements, a 1 MiB decoded response cap and a 20-second total client deadline. Query SHA-256: 17f5fe5005595b4a3674d99d28bc931d32398ace2f7df6fb1b8eefea770a0b34. One direct HTTPS request with environment proxies disabled raised ReadTimeout after 18.70 seconds. No successful response or business count was obtained, no endpoint rotation occurred, and no production records were imported. The cause of the delay is undiagnosed. L03 remains unpassed and D12 remains OPEN.

The first Phase 3 code increment supplies pure observation normalization, bounded query planning, an offline Overpass JSON parser and a transactional registry repository. No network adapter, source enablement, campaign Discord workflow or discovery worker is wired yet. The registry requires a pre-existing RUNNING DISCOVER job with matching unexpired lease, uncancelled state and RUNNING discovery query with a reserved attempt. The query source is the data namespace (osm for this parser); its policy version must match the observation. Source endpoint/transport approval is a separate future dispatch gate.

The registry preserves bounded JSON observations, rejects oversized/non-JSON payloads before write and records invalid name/provenance candidates without reserving a business. The initial observation cap is 65,536 UTF-8 bytes. Unicode names, structured addresses, full IDNA hostnames, published phones and emails supply signals. Email local-part spelling and full email-domain labels remain intact. A name/address strong claim conservatively requires country, city, street, house number, postcode and explicit unit; missing fields do not create this claim. Website/phone/email signals remain supporting and nonunique. None are fetched during normalization.

All dispositions participate in matching. A consistent strong claim can attach another observation; conflicting claims, addresses or plausible weak matches are held for review. Explicit branches with distinct known street/house locations can retain separate IDs despite shared brand signals. Identical unresolved observations across queries point to the same open review while preserving each candidate; operator resolution UI and parent-link management remain unimplemented. The repository never creates research, leads, scores, AI work or quota credit. Candidate observations and discovery business events retain source and attribution, without asserting independent verification.

The planner accepts only the approved fixture categories, finite boxes no larger than the documented one-degree-per-axis envelope, integer limits 1–100 and a positive target version. Coordinates are canonicalized to eight decimal places; collapsed boxes are rejected. It generates fixed query templates and deterministic fingerprints, with no arbitrary query interpolation or live permission implied. The parser retains distinct OSM node/way/relation identifiers, copies only published fields, reports missing coordinates and flags remarks or output-cap hits as incomplete. It does not mark geographic coverage complete.

Remaining Phase 3 work includes approved safe transport, source/daily request reservations, query history/coverage lifecycle, campaign commands, bounded background dispatch with fresh authorization/cancellation, identity-review workflows and real L03 validation. Do not describe this code increment as completed or enabled discovery.

## Source policy review and SSRF-pinned transport — 2026-11-14

Direct socket/TLS diagnostics against `overpass-api.de` and `z.overpass-api.de` established that the earlier timeouts were caused by server-side saturation (`HTTP 502 Bad Gateway: This Overpass API server is currently at capacity. All query workers are busy and the request queue is full`). A single diagnostic request to `https://api.openstreetmap.org/api/0.6/map.json` returned HTTP 200 in 2.19 seconds, but the [OpenStreetMap API Usage Policy](https://operations.osmfoundation.org/policies/api/) explicitly states that the v0.6 editing API is provided for editing the map and is **not** provided for read-only projects or third-party data consumers. Consequently:

1. `OverpassDiscoveryAdapter` explicitly rejects `api.openstreetmap.org` and `/api/0.6/map.json` endpoints (`POLICY_UNKNOWN`), and `config.py` rejects `enabled = true` on all discovery sources while **D12** and **L03** remain **OPEN**.
2. [discovery/overpass.py](../src/mi_boti/discovery/overpass.py) implements full SSRF IP pinning (`format_pinned_url` + `Host` header + `extensions={"sni_hostname": ascii_host}`), rejecting any mixed public/private DNS answers, IPv4-mapped IPv6 non-global addresses, or redirects, and enforces process-wide rate limiting (`min_interval_seconds >= 10`, `max_concurrency = 1`, and `Retry-After` preservation across adapter instances).
3. Proposed permitted source paths for owner decision (**D12**):
   - **Option A — Regional Geofabrik Philippines OSM extract (`philippines-latest.osm.pbf`):** Explicitly permitted by Geofabrik and OSM ODbL for bulk/read-only regional querying without burdening public interactive APIs; requires owner approval to add a bounded local PBF/GeoJSON extract importer.
   - **Option B — Self-hosted / dedicated Overpass instance or owner-approved Overpass mirror with explicit automated-query permission:** Uses `OverpassDiscoveryAdapter` once its operator policy and live `L03` Quezon City probe pass.

## Approved Philippines extract importer and live L03 verification — 2026-11-14

Following the source policy review above, the project owner approved **Option A** ([docs/PHILIPPINES-EXTRACT-PLAN.md](PHILIPPINES-EXTRACT-PLAN.md)): Geofabrik's public Philippines regional OpenStreetMap extract (`https://download.geofabrik.de/asia/philippines-latest.osm.pbf`, official region page `https://download.geofabrik.de/asia/philippines.html`, ODbL license `https://www.openstreetmap.org/copyright`). No paid discovery service, Nominatim harvesting, OSM editing API, or public Overpass backend is approved by this decision.

### Dependency and parser verification

- Pinned `osmium==4.3.2` (PyOsmium, BSD 2-Clause license) under `[project.optional-dependencies] discovery = ["osmium==4.3.2"]` in [pyproject.toml](../pyproject.toml) and [requirements-py314-windows.txt](../requirements-py314-windows.txt).
- Verified binary wheel installation (`osmium-4.3.2-cp314-cp314-win_amd64.whl`) on Windows / CPython 3.14.6 via `--only-binary=:all:` without compiling native code.

### Bounded download, import, and local snapshot architecture ([discovery/philippines_extract.py](../src/mi_boti/discovery/philippines_extract.py))

1. **Explicit offline CLI workflow (`import-ph-extract` and `verify-ph-extract` in [`__main__.py`](../src/mi_boti/__main__.py)):**
   - Never downloads or updates the dataset on bot startup, reconnect, or `/discover` execution.
   - Validates `[sources.philippines_extract]` policy: fixed official URL (`https://download.geofabrik.de/asia/philippines-latest.osm.pbf`), allowlisted HTTPS hosts (`download.geofabrik.de`), reviewed redirect hops (`<=3`, verifying HTTPS and host allowlist on every hop), SSRF IP pinning (`resolve_public_host` + `format_pinned_url` + `Host` header + `sni_hostname`), process-wide rate limiting (`min_interval_seconds >= 10`, `max_concurrency = 1`), finite attempts (`<=3`), timeout (`<=600s`), byte ceiling (`<=1 GiB`), and free disk space check (`minimum_free_mib`).
   - Downloads the `.md5` sidecar and `.osm.pbf` into an isolated `tmp/extract_import_<uuid>/` directory, verifies the provider MD5 (explicitly documented as download error detection, **not** a cryptographic security signature) and computes the local SHA-256 (`pbf_sha256`).
2. **Bounded subprocess-isolated streaming PBF import (`import_pbf_to_snapshot`) and immutable generation publication:**
   - Serializes concurrent import/publication operations via an exclusive OS file lock (`datasets/philippines/publish.lock` using `DeploymentLock`).
   - Enforces a finite monotonic deadline on both download imports and `--pbf-file` CLI imports (`monotonic() + max(policy["timeout_seconds"], 1.0)` when not explicitly supplied).
   - Runs native PyOsmium (`osmium==4.3.2`) PBF parsing inside a bounded child subprocess (`_parse_pbf_in_isolated_subprocess`, `isolate_process=True`) with a disk-backed temporary SQLite scratch workspace under `tmp/extract_import_<uuid>/`, killing the child process (`proc.kill()`) immediately if `deadline_monotonic` expires or `is_cancelled()` fires.
   - Inspects the PBF header (`osmium.io.File(..., "pbf")`), rejecting `osh.pbf` historical/internal extracts, and streams matching `amenity=cafe|restaurant` objects using `osmium.FileProcessor` with `TagFilter`, copying all required fields from transient PyOsmium views before advancing the iterator.
   - Preserves distinct `node/<id>`, `way/<id>`, and `relation/<id>` identities. Derived `way`/`relation` centroids are explicitly marked `"approximate": True` in `coordinates` and carry a limitation note (`Derived approximate centroid from OSM way/relation geometry`).
   - Records `incomplete_geometry`, `unsupported_relations`, `skipped_invalid_tags`, and `truncated_by_cap` counts and limitations. Any non-zero incomplete/unsupported/truncated count sets `incomplete_snapshot = True`, preventing local queries from marking geographic coverage `EXHAUSTED`.
   - Publishes each verified snapshot into its own immutable generation directory `datasets/philippines/generations/<snapshot_id>/` containing its matching `snapshot.sqlite3` and `manifest.json`, verifies the generation directory (`_verify_generation_dir`: SQLite `PRAGMA quick_check`, byte size, SHA-256, and `snapshot_meta`), and only then atomically switches the single active-generation pointer `datasets/philippines/active_generation.json` via `_replace_file_with_sharing_retry` (handling transient Windows `PermissionError` / `WinError 5` / `32` / `33` sharing conflicts from concurrent readers with bounded retry while preserving the previous verified generation on failure).
3. **Local snapshot querying and deferred cross-database cursor acknowledgement (`PhilippinesExtractAdapter` and `jobs/discovery.py`):**
   - Resolves `datasets/philippines/active_generation.json` (`resolve_active_snapshot_generation` using `_read_text_with_sharing_retry`), verifies the referenced immutable generation directory (`generations/<snapshot_id>/snapshot.sqlite3` + `manifest.json`), and opens `snapshot.sqlite3` in read-only URI mode (`?mode=ro`).
   - Distinguishes the extract's data timestamp (`observed_at`, e.g. `2026-11-13T21:22:20.000000Z`) from the local query execution timestamp (`local_queried_at` in `raw_tags["mi_boti:local_queried_at"]`).
   - Binds durable cursors (`datasets/philippines/cursors.sqlite3`) and `checkpoint_token`s to both the immutable generation ID (`snapshot_id`) and `snapshot_sha256`. Does **not** advance the durable cursor inside `PhilippinesExtractAdapter.discover()`. Instead, `discover()` reads the current cursor (resetting `last_ord` to `0` whenever `snapshot_id` or `snapshot_sha256` changes, even if identical PBF bytes were reimported with changed filtering or index caps) and returns `DiscoveryBatch(..., checkpoint_token=checkpoint_token)`.
   - `execute_manual_discovery_job` and `execute_manual_discovery_job_async` call `source.acknowledge_checkpoint(checkpoint_token)` **only after** candidate/registry resolutions (`resolve()`), `finish_discovery_query()`, and `jobs.progress_json` are durably committed in `mi_boti.sqlite3` and after re-verifying that the job remains `RUNNING`, uncancelled, holds the active `lease_token`, has an unexpired lease, and passes fresh `authorize_dispatch`.
   - `acknowledge_checkpoint()` coordinates with `datasets/philippines/publish.lock` so a checkpoint acknowledgement cannot race an in-flight generation publication, verifies `active_manifest.snapshot_id == checkpoint_token["snapshot_id"]` and `active_manifest.pbf_sha256 == checkpoint_token["snapshot_sha256"]`, and uses `BEGIN IMMEDIATE` to advance `last_ord` monotonically. If a cancellation, authorization loss, or process crash occurs between `discover()`, the `mi_boti.sqlite3` result commit, and `acknowledge_checkpoint()`, the unacknowledged page is replayed on the next run and safely deduplicated by the global registry (`existing` count incremented, zero records skipped or duplicated).
   - Production discovery remains disabled in configuration (`src/mi_boti/config.py` rejects `enabled = true` on all sources and providers, and `config.example.toml` keeps `enabled = false`).

### Executed live L03 verification record — 2026-11-14

Executed against the live Geofabrik Philippines extract (`https://download.geofabrik.de/asia/philippines-latest.osm.pbf`) using an isolated disposable SQLite workspace (`.pytest_cache/l03_geofabrik_ph_live`, cleaned up after verification; production `data/mi_boti.sqlite3` remained untouched with `jobs=0, hunts=0`):

```json
{
  "gate": "L03_DISCOVERY_EXTRACT",
  "provider_url": "https://download.geofabrik.de/asia/philippines-latest.osm.pbf",
  "final_download_url": "https://download.geofabrik.de/asia/philippines-261113.osm.pbf",
  "downloaded_at": "2026-11-14T12:23:11.897895Z",
  "snapshot_observed_at": "2026-11-13T21:22:20.000000Z",
  "pbf_bytes": 613918681,
  "provider_md5": "690772965227a78819ee413182ee38ba",
  "pbf_sha256": "aaf01a39336ff80a049935c66199f3786f2ece65a2f056e9ebf350f60ec191c7",
  "snapshot_db_bytes": 10465280,
  "snapshot_db_sha256": "daa61c85ac37f29d679ba69d28c374620ddfddf66f410b9406bc215eeb3b1871",
  "parser": "pyosmium==4.3.2",
  "policy_version": "geofabrik-ph-2026-11",
  "attribution": "© OpenStreetMap contributors — ODbL; https://www.openstreetmap.org/copyright",
  "download_seconds": 69.79,
  "import_seconds": 35.25,
  "national_counts": {
    "nodes_indexed": 22486,
    "ways_indexed": 3563,
    "relations_indexed": 48,
    "approximate_centroids": 3611,
    "incomplete_geometry": 1,
    "unsupported_relations": 0,
    "skipped_invalid_tags": 0,
    "truncated_by_cap": 0
  },
  "incomplete_snapshot": true,
  "limitations": [
    "1 OSM element(s) had missing or incomplete geometry."
  ],
  "qc_fixture_bbox": [14.648, 121.047, 14.657, 121.061],
  "query_1_page_1": {
    "state": "SUCCEEDED",
    "elapsed_seconds": 0.4917,
    "dispositions": {
      "seen": 25,
      "new": 24,
      "existing": 0,
      "ambiguous": 0,
      "invalid": 1,
      "discovery_requests": 1,
      "phase": "COMPLETED"
    }
  },
  "query_2_page_2_cursor": {
    "state": "SUCCEEDED",
    "elapsed_seconds": 0.1949,
    "dispositions": {
      "seen": 7,
      "new": 6,
      "existing": 0,
      "ambiguous": 0,
      "invalid": 1,
      "discovery_requests": 1,
      "phase": "COMPLETED"
    }
  },
  "query_3_repeat_page_1": {
    "state": "SUCCEEDED",
    "elapsed_seconds": 0.3548,
    "dispositions": {
      "seen": 25,
      "new": 0,
      "existing": 24,
      "ambiguous": 0,
      "invalid": 1,
      "discovery_requests": 1,
      "phase": "COMPLETED"
    }
  },
  "disposable_db_totals": {
    "businesses": 30,
    "open_identity_reviews": 0,
    "hunt_credits": 0,
    "coverage_state": "PARTIAL"
  }
}
```

Because one nationwide OSM element had incomplete geometry (`incomplete_geometry = 1`), the snapshot conservatively recorded `incomplete_snapshot = true` and kept the Quezon City cell coverage state `PARTIAL` rather than claiming complete `EXHAUSTED` coverage. Across Page 1 (`limit=25`) and Page 2 (`limit=25`, resumed via durable cursor), 32 OSM observations in the Quezon City fixture bounding box were processed into 30 distinct registered businesses and 2 nameless `INVALID` candidate observations, with 0 new businesses created on the repeated Page 1 search (`existing=24, invalid=1, new=0`) and 0 hunt credits awarded.
