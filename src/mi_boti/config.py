"""Strict, offline environment/TOML configuration. No provider is enabled here."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import ipaddress
import os
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
import tomllib
from urllib.parse import urlsplit

from .defaults import DEFAULTS
from .domain.errors import ConfigurationError
from .domain.values import snowflake

ENV_KEYS = frozenset({
    "MI_BOTI_DISCORD_TOKEN", "MI_BOTI_GUILD_ID", "MI_BOTI_OWNER_IDS",
    "MI_BOTI_CONFIG_FILE", "MI_BOTI_DATA_DIR", "MI_BOTI_APPLICATION_ID",
})
PROVIDER_KEYS = frozenset({"enabled", "executable_path", "expected_backend", "model_scope", "profile_id"})
SOURCE_KEYS = frozenset({
    "enabled", "endpoint", "allowed_hosts", "permission_url", "license_url", "attribution",
    "policy_version", "reviewed_at", "review_expires_at", "user_agent", "allowed_tags",
    "min_interval_seconds", "max_concurrency", "timeout_seconds", "max_response_bytes",
    "max_attempts", "max_requests_per_day",
})


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class Settings:
    config_file: Path
    data_dir: Path
    values: Mapping[str, object] = field(repr=False)
    providers: Mapping[str, object] = field(repr=False)
    sources: Mapping[str, object] = field(repr=False)
    guild_id: str | None = None
    owner_ids: tuple[str, ...] = ()
    discord_token: str | None = field(default=None, repr=False)
    application_id: str | None = None

    def require_identity(self, *, token: bool = False) -> None:
        if not self.guild_id or not self.owner_ids:
            raise ConfigurationError("Set MI_BOTI_GUILD_ID and MI_BOTI_OWNER_IDS before database initialization.")
        if token and not self.discord_token:
            raise ConfigurationError("Set MI_BOTI_DISCORD_TOKEN before connecting Discord.")

    def safe_summary(self) -> dict:
        return {
            "configuration": "valid", "guild_configured": self.guild_id is not None,
            "owners_configured": bool(self.owner_ids), "token_configured": bool(self.discord_token),
            "ai_enabled": False, "discovery_enabled": False, "hunting_enabled": False,
        }

    def hunt_limits(self, quota: int) -> dict[str, int]:
        if type(quota) is not int or not 1 <= quota <= self.values["hunt.max_quota"]:
            raise ConfigurationError("Quota must be an integer within the configured range.")
        v = self.values
        blocks = max(1, math.ceil(quota / v["hunt.quota_block_size"]))
        result = {
            "active_seconds": min(v["hunt.max_active_cap_seconds"], v["hunt.max_active_seconds"] * blocks),
            "age_seconds": v["hunt.max_age_seconds"],
        }
        for resource in ("discovery_requests", "candidates", "http_requests", "ai_tasks"):
            result[resource] = min(v[f"hunt.max_{resource}"], max(
                v[f"hunt.base_{resource}"], quota * v[f"hunt.{resource}_per_lead"]
            ))
        return result


def _validate_values(values: dict) -> None:
    for key, default in DEFAULTS.items():
        value = values[key]
        if isinstance(default, tuple):
            if not isinstance(value, (list, tuple)) or any(type(x) is not int for x in value):
                raise ConfigurationError(f"Invalid type for {key}.")
        elif type(value) is not type(default):
            raise ConfigurationError(f"Invalid type for {key}.")
        if type(value) in (int, float) and (not math.isfinite(value) or value <= 0):
            raise ConfigurationError(f"Expected a finite positive value for {key}.")
    if values["runtime.log_level"] not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ConfigurationError("Invalid runtime.log_level.")
    if values["jobs.ai_concurrency"] != 1 or values["jobs.max_concurrency"] > 2:
        raise ConfigurationError("Phase 1 permits at most two workers and exactly one future AI slot.")
    if values["jobs.heartbeat_seconds"] >= values["jobs.lease_seconds"] / 2:
        raise ConfigurationError("Job heartbeat must be less than half its lease.")
    for resource in ("discovery_requests", "candidates", "http_requests", "ai_tasks"):
        if values[f"hunt.base_{resource}"] > values[f"hunt.max_{resource}"]:
            raise ConfigurationError("Hunt base budget exceeds its cap.")
    if not values["hunt.max_active_seconds"] <= values["hunt.max_active_cap_seconds"] <= values["hunt.max_age_seconds"]:
        raise ConfigurationError("Active-time budgets must fit within the absolute age ceiling.")
    if values["hunt.max_quota"] > 100:
        raise ConfigurationError("Initial-release quota cannot exceed 100.")
    if not 0 < values["discovery.similarity_review_threshold"] <= 1:
        raise ConfigurationError("Similarity threshold must be within (0, 1].")
    if values["discovery.manual_default_limit"] > values["discovery.manual_max_limit"] or values["discovery.manual_max_limit"] > 100:
        raise ConfigurationError("Invalid manual discovery limits.")
    if values["discovery.max_bbox_degrees"] > 1 or values["discovery.max_tags"] > 100:
        raise ConfigurationError("Discovery targeting exceeds the reviewed bounds.")
    if set(values["research.allowed_ports"]) != {80, 443}:
        raise ConfigurationError("Only HTTP/HTTPS standard ports are supported.")
    if values["mcp.enabled"] or values["research.playwright_enabled"] or values["research.trust_env_proxy"]:
        raise ConfigurationError("MCP, browser fetching and proxy overrides are not verified or implemented.")
    if values["jobs.max_attempts"] > 3 or values["research.max_attempts"] > 2 or values["providers.max_output_repairs"] > 1:
        raise ConfigurationError("Retry or repair limit exceeds the documented safety envelope.")
    if values["ui.page_size"] > 10:
        raise ConfigurationError("UI page size cannot exceed ten.")
    if any(c in values["research.user_agent"] for c in "\r\n\x00"):
        raise ConfigurationError("User-agent contains a forbidden control character.")


def _dynamic(section: dict, allowed: frozenset, *, source: bool) -> Mapping:
    result = {}
    for identifier, options in section.items():
        if not isinstance(identifier, str) or not identifier or not isinstance(options, dict) or set(options) - allowed:
            raise ConfigurationError("Unknown provider/source configuration structure.")
        if type(options.get("enabled", False)) is not bool:
            raise ConfigurationError("Provider/source enabled must be boolean.")
        for key, value in options.items():
            if key == "enabled":
                continue
            if key in {"allowed_hosts", "allowed_tags"}:
                if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x for x in value):
                    raise ConfigurationError("Source allowlists must contain nonempty strings.")
            elif key in {"min_interval_seconds", "max_concurrency", "timeout_seconds", "max_response_bytes", "max_attempts", "max_requests_per_day"}:
                if type(value) is not int or value <= 0:
                    raise ConfigurationError("Source limits must be positive integers.")
            elif not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\x00"):
                raise ConfigurationError("Invalid provider/source setting value.")
            if key == "executable_path" and not Path(value).is_absolute():
                raise ConfigurationError("Provider executable paths must be absolute.")
            if key in {"endpoint", "permission_url", "license_url"}:
                try:
                    parsed = urlsplit(value)
                    port = parsed.port
                except ValueError:
                    raise ConfigurationError("Invalid source URL port.") from None
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or port not in (None, 443):
                    raise ConfigurationError("Source policy URLs require plain HTTPS without credentials.")
                host = parsed.hostname.lower().rstrip(".")
                if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                    raise ConfigurationError("Local source hosts are not allowed.")
                try:
                    address = ipaddress.ip_address(host)
                except ValueError:
                    pass
                else:
                    if not address.is_global:
                        raise ConfigurationError("Nonpublic source addresses are not allowed.")
            if key in {"reviewed_at", "review_expires_at"}:
                try:
                    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        raise ValueError
                except ValueError:
                    raise ConfigurationError("Source policy dates require timezone-aware ISO timestamps.") from None
        if source and options.get("endpoint") and options.get("allowed_hosts"):
            if urlsplit(options["endpoint"]).hostname not in options["allowed_hosts"]:
                raise ConfigurationError("Source endpoint is outside its host allowlist.")
        if options.get("enabled"):
            raise ConfigurationError("Provider/source execution is not implemented or verified; keep enabled=false.")
        result[identifier] = _freeze(options)
    return MappingProxyType(result)


def load_settings(environ: Mapping[str, str] | None = None, *, cwd: Path | None = None) -> Settings:
    env = os.environ if environ is None else environ
    cwd = Path.cwd() if cwd is None else cwd
    if any(k.startswith("MI_BOTI_") and k not in ENV_KEYS for k in env):
        raise ConfigurationError("Unknown MI_BOTI environment variable.")
    config_file = Path(env.get("MI_BOTI_CONFIG_FILE", "config.toml"))
    data_dir = Path(env.get("MI_BOTI_DATA_DIR", "data"))
    if not config_file.is_absolute():
        config_file = cwd / config_file
    if not data_dir.is_absolute():
        data_dir = cwd / data_dir
    try:
        if config_file.stat().st_size > 65536:
            raise ConfigurationError("Configuration exceeds the 64 KiB limit.")
        raw = tomllib.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        raise ConfigurationError("Cannot read valid local TOML configuration; use config.example.toml as a starting point.") from None
    values = dict(DEFAULTS)
    providers, sources = {}, {}
    known_sections = {k.split(".")[0] for k in DEFAULTS} | {"sources"}
    if set(raw) - known_sections:
        raise ConfigurationError("Unknown configuration section.")
    for section, content in raw.items():
        if not isinstance(content, dict):
            raise ConfigurationError("Configuration sections must be TOML tables.")
        for key, value in content.items():
            qualified = section + "." + key
            if qualified in DEFAULTS:
                values[qualified] = value
            elif section in {"providers", "sources"} and isinstance(value, dict):
                (providers if section == "providers" else sources)[key] = value
            else:
                raise ConfigurationError("Unknown configuration key.")
    _validate_values(values)
    token = env.get("MI_BOTI_DISCORD_TOKEN") or None
    if token is not None and (not token.strip() or any(c.isspace() for c in token)):
        raise ConfigurationError("Bot token must be a nonempty opaque value without whitespace.")
    guild = snowflake(env["MI_BOTI_GUILD_ID"]) if env.get("MI_BOTI_GUILD_ID") else None
    owners = tuple(snowflake(x.strip()) for x in env.get("MI_BOTI_OWNER_IDS", "").split(",") if x.strip())
    if len(owners) != len(set(owners)):
        raise ConfigurationError("Owner IDs must be unique.")
    return Settings(config_file.absolute(), data_dir.absolute(), _freeze(values),
                    _dynamic(providers, PROVIDER_KEYS, source=False),
                    _dynamic(sources, SOURCE_KEYS, source=True), guild, owners, token,
                    snowflake(env["MI_BOTI_APPLICATION_ID"]) if env.get("MI_BOTI_APPLICATION_ID") else None)
