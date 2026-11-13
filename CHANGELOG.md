# Changelog

Versions use MAJOR.MINOR.PATCH with annotated v tags. Releases before 1.0 are development milestones, not production-readiness claims.

## Unreleased

### Phase 3 core

- Add normalized public observations, transactional global identity reservations, ambiguity holds and cross-query review reuse with immutable origin ownership.
- Add a bounded fixture query planner and offline Overpass JSON parser; test separate-connection duplicate races, all dispositions, branch distinctions, provenance and stale-worker rejection.
- Record the Quezon City restaurant/cafe fixture and failed one-request source probe. Live discovery and AI/hunting remain disabled; source, campaign and worker integration are unfinished.

### Verification tooling

- Add a read-only Phase 2 prerequisite checker with tests for missing databases, incomplete configuration and persisted mapping validation. Record owner-confirmed persistent-button recovery and remaining Phase 3 admission requirements.

### Documentation

- Redesign the README around a personal workspace identity, with the approved wide cat-and-laptop banner, plain typography, milestone overview and compact navigation.
- Move the installation and launch walkthrough to the local operations reference.

## 0.2.0 — 2026-11-14

### Added

- Guild-scoped Discord startup and 21 canonical command keys with owner/admin/operator and channel authorization.
- Private setup previews, explicit confirmation, durable provisioning journals, idempotent resources and four persistent panels.
- Staged role/channel mapping changes, conservative partial/uncertain recovery and restored component routing after restart.
- A Windows launcher template with account-bound encrypted token caching outside the repository and a ResetToken option.
- Discord policy, SQLite setup, interaction and SDK transport regression tests; versioned documentation and acceptance records.

### Fixed

- The SDK rate-window setting that could reject available requests in a 60-second reset window.
- Missing-permission and rate-limit diagnostics, SDK log redaction and Windows import-side-effect verification.
- README Markdown presentation and Git exclusions that omitted documentation and tests.

### Verification and limitations

- Automated suite: 337 tests pass on Windows / CPython 3.14.6; 16 upstream discord.py deprecation warnings remain.
- Owner-confirmed live setup/repeat setup, correct/wrong-channel usage status and command response after restart.
- Full L01 acceptance remains pending, including independent-role denial, managed-resource deletion/rename recovery and explicit post-restart component checks.
- Discovery, research, CRM, AI execution and autonomous hunting remain unavailable. No provider has passed the full allowance gate; discovery source approval/connectivity remains unresolved.
- Credentials, operator-specific launcher, runtime SQLite databases and logs are excluded from Git.

## 0.1.0 — Foundation baseline

Python packaging, strict configuration, redacted logging, private storage, deployment locking, checksummed SQLite migrations and verified backup/restore primitives. The foundation passed 66 automated tests. This historical version was recorded in package metadata; no previous release tag is asserted.
