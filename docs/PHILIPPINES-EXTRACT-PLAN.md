# Approved Philippines extract source direction

Owner decision: 2026-11-14. The owner approved a local Philippines OpenStreetMap extract as the Phase 3 discovery source direction. This supersedes the unresolved choice between a local extract and a dedicated Overpass endpoint. It does **not** mark L03 or Phase 3 complete, enable discovery, or change the runtime AI gates.

## Feasibility review

- Selected provider: Geofabrik's public Philippines regional extract, `philippines-latest.osm.pbf`, from the [official region page](https://download.geofabrik.de/asia/philippines.html). The page currently lists approximately 585 MB and a data timestamp of 2026-11-13T21:22:20Z. Actual size, snapshot time and checksum must be captured at download rather than assumed from this note.
- The [official download service](https://download.geofabrik.de/) offers free regional OSM extracts. Retain OpenStreetMap contributor attribution and the [ODbL notice](https://www.openstreetmap.org/copyright) in imported provenance and output. Do not download restricted contributor metadata/history files.
- Proposed parser dependency: optional `osmium==4.3.2` (PyOsmium). Official PyPI metadata lists a `cp314-cp314-win_amd64` wheel, matching the verified interpreter, and Python >=3.8. PyOsmium uses the BSD 2-Clause license. See [project/license](https://osmcode.org/pyosmium/) and [streaming documentation](https://docs.osmcode.org/pyosmium/latest/user_manual/01-First-Steps/).
- The dependency has not been installed and the regional file has not been downloaded as part of this approval record. A published wheel establishes availability, not successful installation or parser compatibility. Do not silently compile a native dependency or change Python versions if installation fails.
- No paid service, Nominatim harvesting, OSM editing API or public Overpass endpoint is approved by this decision.

## Next implementation task for Antigravity

Read the local AGENTS.md, current [development handoff](../DEVELOPMENT-HANDOFF.md), [source contract](08-BUSINESS-DISCOVERY.md), [schema](04-DATABASE-SCHEMA.md), [storage](05-LOCAL-STORAGE.md), [jobs](17-BACKGROUND-JOBS.md) and [configuration](23-IMPLEMENTATION-GUIDELINES.md) before implementation. Preserve existing uncommitted changes and coordinate file ownership with other development tools.

1. Update the source decision log and component specifications to distinguish **owner-approved source direction** from **unpassed implementation/live verification**. Keep history entries as historical evidence. No more source-choice confirmation is needed for this approved direction.
2. Justify and pin the parser as an optional discovery dependency. Prove installation/import on the verified Windows/Python interpreter and add it to the appropriate lock/dependency documentation without introducing unrelated packages.
3. Implement an explicitly invoked, bounded download/import workflow. Use the fixed official provider URL, reviewed redirect policy, TLS verification, finite attempts/timeouts/size and free-space checks, source-wide rate limiting, atomic temporary-file handling and cancellation. Keep datasets, caches and credentials outside Git. Never replace the active verified snapshot with a partial or failed download.
4. Record provider URL, download time, extract data timestamp, byte size, available provider checksum, locally calculated SHA-256, parser/version, attribution and limitations. A provider MD5 may detect download errors; do not describe it as a security signature. Do not silently update the dataset on bot launch or reconnect.
5. Parse in bounded isolation with tested cancellation/shutdown and disk/memory budgets. Do not load all Philippine OSM objects into a Python list or use an unbounded node-location cache. PyOsmium objects are transient views; copy required fields before advancing the iterator.
6. Preserve distinct OSM node/way/relation identities and published tags. State supported geometry/entity coverage accurately. Missing/incomplete geometry, unsupported relations, skipped objects and import truncation must be recorded; they cannot establish complete geographic coverage. Approximate derived coordinates must be labelled as such.
7. Query the verified local snapshot by bounded campaign cells and allowlisted categories. Preserve provenance and route observations through the existing global registry, current job leases, cancellation, query history and fresh Discord authorization. Searching must not refetch the national extract per command. Distinguish original snapshot observation time from the later local search time.
8. Ensure resumable/capped local results do not repeatedly return the same first page while claiming progress or complete coverage. Test stable pagination/checkpoints or conservatively report the limitation. Existing/ambiguous/invalid observations never become new-lead quota credit.
9. Keep the optional source fail-closed until verified. Scope configuration enablement to the approved, verified local source only; do not generally unlock HTTP sources or any AI provider.

The initial live fixture remains the small Quezon City restaurant/cafe area already recorded in doc 08. The source is nationwide, so this fixture is not a permanent geographic restriction. Owner-controlled later targeting may expand without changing duplicate-prevention or evidence rules.

## Acceptance and reporting

Use small synthetic OSM fixtures for ordinary tests: valid and malformed PBF input, missing/truncated/corrupt files, checksum mismatch, nodes/ways/relations, unsupported/incomplete geometry, output caps, repeated imports, duplicate-only results, snapshots that change, cancellation, exhausted budgets, restart and no startup execution. Verify that failed refresh/import retains the previously verified snapshot.

Separately perform L03 against the actual downloaded public extract using a disposable SQLite database. Record download/import/query durations, dataset/hash identity, attribution, accurate partial/complete counts, registry dispositions and duplicate results on a repeated search. Do not import fixture businesses into the owner's production registry without the normal explicit operation.

Run the appropriate automated suite and dependency checks, then update docs 08/21/22/23, the decision log and development handoff with actual results. Report any blocked mandatory behavior before proposing a requirement change. Full Phase 3 and later phases remain unaccepted until their required evidence exists. AI execution, scoring and autonomous hunting remain disabled regardless of importer success.

This file records approval and the next implementation scope. It is not an execution report or a claim that the importer exists.
