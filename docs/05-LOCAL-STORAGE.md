# 05 — Local storage

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and ownership

Specify filesystem behavior supporting [SQLite](04-DATABASE-SCHEMA.md), [research](09-WEB-RESEARCH-ENGINE.md), [privacy](18-SECURITY-AND-PRIVACY.md), and [recovery](17-BACKGROUND-JOBS.md). Structured truth remains in SQLite; artifacts cannot override database records.

```text
<data_dir>/
  mi_boti.sqlite3               # SQLite plus associated WAL/SHM
  deployment.lock
  datasets/philippines/         # active_generation.json, publish.lock, cursors.sqlite3, and immutable generations/<snapshot_id>/{snapshot.sqlite3, manifest.json}
  artifacts/<uuid>/<uuid>.txt   # bounded sanitized extracts, not executable HTML
  exports/<uuid>.csv            # operator-requested CRM export
  backups/<uuid>/               # verified copy; expanded manifest is post-MVP
  logs/mi-boti.log              # redacted rotating diagnostics
  verification/<uuid>/         # sanitized real-provider/source test evidence
  tmp/<job_uuid>/               # isolated short-lived CLI/fetch workspace
```

## Interfaces and integrity

`ArtifactStore.put(bytes, media_type, retention_class) -> ArtifactRef(id, relative_path, sha256, bytes)` writes a random temporary file under the same volume, flushes, atomically renames, and then records metadata. Crash before metadata leaves an orphan for a bounded cleanup scan; crash after record but missing file sets artifact MISSING and surfaces a limitation. No fetched filename, business name, or AI value becomes a path. Resolve and verify every access remains beneath data_dir, reject `..`, absolute inputs, symlink/junction escapes and reparse points. Never execute stored content.

Exports escape spreadsheet formula-leading `=`, `+`, `-`, `@`, tab and CR by prefixing a literal apostrophe, quote CSV fields, use UTF-8, include UTC timestamps and provenance/attribution columns, and exclude secrets and internal CLI transcripts. Exports are delivered only through authorized ephemeral attachments in the mapped command channel; if too large, report a local relative path to the owner without public upload. A command option triggers an export job, never a new web endpoint.

## Backup and restore

### MVP: basic verified copy

`/backup create` is administrator-only and enqueues a bounded maintenance job. Obtain a consistent SQLite online backup while coordinating writers; never copy only the live database file during WAL writes. Reopen the copy, run integrity_check and foreign_key_check, verify supported schema and guild binding, and record its path, size, SHA-256, creation time and successful verification time in existing artifacts/backups records. Only then mark it VERIFIED. A failed check marks FAILED and never replaces the last verified copy. This is a basic verified backup, not merely an unchecked file copy.

The non-AI MVP keeps required discovery facts, Phase 4a website evidence/provenance and manual CRM/draft content in SQLite, so the basic copy contains the authoritative data. Sanitized website text artifacts remain optional supplements; any extract required to support a persisted finding must instead be included and verified under the mandatory-artifact rule below. Phase 4a cannot bypass that backup obligation merely because expanded manifests are post-MVP. If any mandatory artifact is introduced before expanded backup support exists, it must also be copied and verified before the backup can be called complete; do not defer protection of data that is already required. Credentials and arbitrary home directories remain excluded.

### Post-MVP: expanded verification manifests

After the MVP works, add a manifest containing schema/app versions, UTC timestamps and per-file hashes/sizes, snapshot all referenced retained artifacts, and validate the manifest and every included hash before VERIFIED. Missing mandatory evidence artifacts fail verification. Retained factual evidence in SQLite remains usable when optional extracts have expired. The full manifest contract remains required for the artifact-rich release; its sequencing does not remove integrity checks from basic copies.

### Restore

Restore is a local owner maintenance operation with the bot stopped. Preserve current data and check path safety, backup metadata/hash, schema, integrity and foreign keys. For expanded backups, also validate the manifest and every referenced artifact hash. Restore into a new data root, verify the guild binding, and only then switch the configured path. Recover unfinished jobs as INTERRUPTED before connecting Discord. Never resume a hunt or restore provider auth secrets. Exercise this procedure in a disposable directory before replacing live data. `/backup verify` checks an existing basic or expanded backup; no destructive Discord restore command exists.

## Retention, permissions and failures

Defaults: temporary workspaces deleted after completion or within 24 hours after startup cleanup; extracts and exports expire after 30 and 7 days; logs rotate at 5 MiB with five retained files; backups retain the newest seven VERIFIED snapshots. Keep structured identity, evidence metadata/facts, research decisions and quota history indefinitely unless an owner-approved privacy procedure supersedes it. Never purge the last verified backup automatically. Provider verification manifests persist while referenced; raw sanitized transcripts may expire after 30 days.

Use OS permissions limited to the local service account/owner. Warn before disk space falls below configured minimum; refuse new artifact/backup work at the floor and stop affected hunt safely. Cleanup marks PURGED metadata and preserves hashes/source references; it never deletes referenced structured records. Logs and backups can contain public contact data and require the same protection as the live database. Backups exclude bot token, CLI credentials, environment files and arbitrary home directories.

## Acceptance

T14 attempts traversal/junction escapes and CSV formulas; T16 kills artifact writes and verifies orphan cleanup, full-disk behavior, consistent WAL backup, restore checks, retained identity, and no startup hunt. Backup files alone do not count as validated recovery until a restore exercise passes; see [20](20-TESTING-STRATEGY.md).
