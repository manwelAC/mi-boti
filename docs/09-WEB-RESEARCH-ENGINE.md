# 09 — Web research engine

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose

Implement evidence collection for R06/R15 between [discovery](08-BUSINESS-DISCOVERY.md) and [intelligence](12-AI-LEAD-INTELLIGENCE.md). Persist [evidence and artifacts](04-DATABASE-SCHEMA.md) independently of AI output.

## Phase 4a and Phase 4b boundary

This entire collection engine belongs to Phase 4a and the non-AI MVP. `/research` defaults to analyze:false, so it runs the collection contract below without a provider, authentication status probe, allowance check or AI execution. Phase 4b alone owns optional `analyze:true` findings, qualification and scoring under the provider gate. A provider outage must not block collection.

The RESEARCH job persists the business ID, refresh authorization and analyze option (default false) in its typed payload. On collection success, commit evidence and the research-run checkpoint before any optional Phase 4b task. In the MVP, publish only observations and limitations, not AI claims or scores. The operator can select these stored evidence IDs during manual qualification or draft review. No collection outcome changes quota credit or automatically promotes the business. Resume after interruption always requires a new explicit authorized operation, consistent with the job rules.

## Research contract

`collect(business_id, refresh, budget, cancellation) -> ResearchResult(run_id, evidence_ids, pages_attempted, pages_accepted, limitations, state)`. Existing records require explicit refresh authorization except a newly reserved hunt candidate's INITIAL research. A run contains a finite plan: official home, about/services, publicly linked contact and booking/service pages, within approved same-site domains. The default maximum is five pages per business, depth one, 2 MiB decoded body per page, 10-second request timeout, three redirects, two total attempts per page. Count requests including retries, redirects, robots and DNS-dependent fetches against budgets as applicable; no infinite link crawling. Do not log into sites, bypass CAPTCHAs/paywalls, submit forms, or inspect nonpublic internal systems.

## URL and network validation

Accept only HTTP/HTTPS with port 80/443, no userinfo, fragments, local paths or malformed IDNA. Reject localhost, numeric-IP tricks, private/loopback/link-local/multicast/reserved addresses, IPv4-mapped IPv6 private addresses, metadata endpoints and non-global DNS answers. Resolve every hostname, reject if any returned address is forbidden, and pin the validated IP for the actual connection while preserving Host/TLS name. Revalidate DNS at each new connection/redirect to resist rebinding. Reject redirects to disallowed host/port/scheme or forbidden IP; never let HTTPX follow redirects without this validation. Disable environment-derived proxies unless locally reviewed and configured through the same network policy; default no proxies.

This requires a tested resolver/transport boundary, not just a preflight DNS lookup followed by ordinary re-resolution. If safe pinning cannot be implemented reliably on the selected transport, URL fetching stays disabled until solved. Adapter and transport tests must prove the connection destination, including IPv6. Optional Playwright is disabled until all navigation, subresources, downloads and WebSocket requests have equivalent restrictions; it cannot bypass an HTTP policy failure.

## Access and extraction policy

Check source permission/terms and robots policy before retrieval; robots alone does not grant permission. The fail-closed access policy is: disallow robots rules or unavailable/unparseable access policy prevents automated fetching until reviewed. Cache robots for 24 hours; respect stricter crawl delays. Rate-limit website hosts to one active fetch and at least two seconds between starts. Respect 429/Retry-After; never retry through another identity. Send a configured descriptive user-agent/contact, not a fake browser identity. No user-supplied auth headers/cookies. TLS verification remains enabled.

Stream responses with a decoded byte cap and compression limits. Allow text/html and text/plain only initially; reject downloads, executables, archives and unsupported MIME types. BeautifulSoup removes scripts, styles, forms and hidden boilerplate; retain useful text and public links as data, with extraction limitations. Bound extracted text at 20,000 characters per page. No embedded instructions enter execution configuration. Preserve source URL, final URL, observation time, policy version and relevant excerpt hash; optional sanitized text artifacts use [05](05-LOCAL-STORAGE.md).

## Evidence contract

Each evidence record has business_id, candidate_id or research_run_id, source_url or source_identifier, observed_at UTC, extracted_fact, confidence in [0,1], limitations_json and optional artifact_id. Facts must be directly observable, such as “The public service page offers online appointment booking,” not “The company has no CRM.” Contacts require a cited public source and business attribution; inferred emails are prohibited. Multiple conflicting sources remain separate with limitations, not silently overwritten. Redirected domains and stale or undated pages lower confidence and may require identity review.

ResearchResult SUCCEEDED means the finite plan completed with usable evidence; PARTIAL retains valid observations when pages fail; FAILED means no usable result or a safety violation. An inaccessible page is an UNKNOWN limitation, not proof of missing tools. Evidence snapshots remain immutable; refresh creates a new run, never rewrites old observations.

## Failure and acceptance

Denied URLs stop before connecting. Malformed HTML produces a bounded extraction error. Timeout, source block, excessive redirects or oversized body records a limitation; a critical SSRF violation fails the run and audits sanitized host/reason. Insufficient evidence prevents qualification but preserves discovery memory. T10 tests redirects, DNS rebinding, IPv6, decompression bombs, forbidden MIME, robots and timeouts. The non-AI T11 cases test provenance, same-business evidence, timestamps, immutable refresh history, conflicting observations and the rule that an inaccessible page proves no missing internal software. T10/non-AI T11 also assert zero provider/allowance/score/credit calls for analyze:false. AI-specific T11 output validation belongs to Phase 4b. See [security](18-SECURITY-AND-PRIVACY.md) and [testing](20-TESTING-STRATEGY.md).
