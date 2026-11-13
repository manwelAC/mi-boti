# 11 — MCP integration

Decision status: see the [README decisions table](../README.md#decisions).

## Purpose and scope

The requested package includes this topic, but finalized context does not require an MCP server, client or external tool. **MCP is disabled and unnecessary for the initial release**. Core discovery, research, CLI integration, storage and Discord operate directly through documented adapters. This document defines the boundary for a future explicitly authorized integration, not a promise of current provider MCP support. See [architecture](02-TECHNICAL-ARCHITECTURE.md), [providers](10-AI-PROVIDER-INTEGRATION.md), and [security](18-SECURITY-AND-PRIVACY.md).

## Current implementation contract

`mcp.enabled=false` is the only supported release value. Startup rejects true with UNSUPPORTED_CAPABILITY; it does not install servers or discover tools automatically. No MCP daemon, endpoint, access token, tool registry, data mirroring or network listener is provisioned. Provider CLI execution must disable undeclared inherited MCP integrations or fail eligibility if isolation cannot be verified. Existing global CLI configuration is not assumed harmless.

MCP cannot be used to bypass allowance verification, invoke a paid API, fetch unsafe URLs, broaden CLI filesystem access, send outreach or skip Discord policy checks. A user's available desktop MCP tools are not application architecture dependencies.

## Future extension interface — post-MVP, conditional on authorization

This interface is post-MVP and is not needed to complete the non-AI slice. If requirements are explicitly revised, use an allowlisted `ToolBroker.invoke(actor, job_id, tool_key, validated_arguments) -> ToolResult` boundary. A tool manifest must state immutable tool key, server identity/version/hash, transport, argument/output JSON schemas, permitted data scope, read/write effects, timeout, result size, cancellation behavior and credential scope. Each call requires the same guild/action authorization, job lease, budget and audit checks as native adapters. Discovered descriptions and results are untrusted data; a server cannot authorize its own operations.

Prefer an explicitly configured local transport with shell disabled and a minimal environment. Remote transports need a separately reviewed authentication, privacy, network and trust design. No generic arbitrary-tool forwarding from AI output. Side effects must be idempotent or held for a human-controlled operation; external outreach remains excluded even if a server offers it. Subscription checks continue through verified provider adapters, never an unverifiable MCP claim.

## Validation and failures

No extension is enabled before per-server compatibility tests, schema/error handling, timeout/cancellation, SSRF/command injection analysis and secret redaction review. Unknown tools/servers, expired verification, malformed output, transport failure and insufficient permissions fail closed. A tool failure must not select another provider or sending route. Store approved configuration in versioned nonsecret local settings; credentials use provider-owned secure storage, not ordinary SQLite records.

## Acceptance

T09/T14 prove initial-release startup makes no MCP connections and rejects enablement, CLI profiles cannot inherit unreviewed tools, and no tool path bypasses provider or authorization gates. A future feature needs new requirements, schema/config updates, tests and explicit approval; this document alone is not that authorization. The current disabled policy has no third-party feasibility dependency.
