import math

import pytest

from mi_boti.config import load_settings
from mi_boti.domain.errors import ConfigurationError
from mi_boti.domain.values import snowflake


def test_offline_config_needs_no_discord_token_and_never_echoes_it(configured):
    env, _ = configured
    env["MI_BOTI_DISCORD_TOKEN"] = "fixture-private-token"
    settings = load_settings(env)
    assert "fixture-private-token" not in repr(settings)
    assert "fixture-private-token" not in str(settings.safe_summary())
    assert settings.safe_summary()["ai_enabled"] is False
    settings.require_identity(token=True)


@pytest.mark.parametrize("text", [
    "[unknown]\nvalue=1", "[runtime]\nsecret_token='do-not-echo'", "[jobs]\nmax_attempts=true",
    "[jobs]\nmax_attempts=4", "[jobs]\nheartbeat_seconds=20", "[hunt]\nbase_candidates=3000",
    "[hunt]\nmax_age_seconds=100", "[hunt]\nmax_quota=101", "[research]\ntimeout_seconds=-1",
    "[research]\ntrust_env_proxy=true", "[research]\nallowed_ports=[80,443,8080]",
    '[research]\nuser_agent="bad\\nagent"', "[research]\ntimeout_seconds=nan",
    "[discovery]\nsimilarity_review_threshold=1.1", "[mcp]\nenabled=true",
    "[providers.agy]\nenabled=true", "[sources.overpass]\nenabled=true",
    "[sources.overpass]\nendpoint='https://user:password@example.com/api'",
    "[sources.overpass]\nmax_requests_per_day=false", "[providers.agy]\nexecutable_path='relative.exe'",
    "[providers.agy]\nunknown='secret'", "[sources.overpass]\nreviewed_at='2026-11-14'",
    "[sources.overpass]\nendpoint='https://127.0.0.1/api'",
    "[sources.overpass]\nendpoint='https://metadata.google.internal/api'",
    "[sources.overpass]\nendpoint='https://[broken/api'",
])
def test_rejects_unknown_unsafe_and_unimplemented_configuration(configured, text):
    env, path = configured
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigurationError) as error:
        load_settings(env)
    assert "do-not-echo" not in str(error.value)


def test_missing_or_malformed_file_has_safe_message(configured):
    env, path = configured
    path.write_text("private_secret = [", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="valid local TOML"):
        load_settings(env)
    path.unlink()
    with pytest.raises(ConfigurationError, match="starting point"):
        load_settings(env)


def test_environment_identity_checks_and_opaque_token(configured):
    env, _ = configured
    with pytest.raises(ConfigurationError):
        load_settings({**env, "MI_BOTI_OWNER_IDS": "1,1"})
    with pytest.raises(ConfigurationError):
        load_settings({**env, "MI_BOTI_DISCORD_TOKEN": "bad token"})
    with pytest.raises(ConfigurationError):
        load_settings({**env, "MI_BOTI_GUILD_IDS": "typo"})
    settings = load_settings({k: v for k, v in env.items() if k != "MI_BOTI_GUILD_ID"})
    with pytest.raises(ConfigurationError):
        settings.require_identity()


@pytest.mark.parametrize("value", ["0", "01", "-1", "18446744073709551616", 123, True])
def test_snowflakes_are_canonical_strings(value):
    with pytest.raises(ConfigurationError):
        snowflake(value)


def test_unsigned_snowflake_and_quota_snapshot_defaults(configured):
    assert snowflake("18446744073709551615") == "18446744073709551615"
    settings = load_settings(configured[0])
    assert settings.hunt_limits(25) == {
        "active_seconds": 18000, "age_seconds": 604800, "discovery_requests": 50,
        "candidates": 500, "http_requests": 4000, "ai_tasks": 500,
    }
    assert settings.hunt_limits(1)["active_seconds"] == 3600
    with pytest.raises(ConfigurationError):
        settings.hunt_limits(True)
    with pytest.raises(TypeError):
        settings.values["hunt.max_quota"] = 1000


def test_disabled_dynamic_profiles_remain_immutable(configured):
    env, path = configured
    path.write_text('[sources.overpass]\nenabled=false\nallowed_hosts=["overpass-api.de"]\nendpoint="https://overpass-api.de/api/interpreter"', encoding="utf-8")
    settings = load_settings(env)
    assert settings.sources["overpass"]["enabled"] is False
    with pytest.raises(TypeError):
        settings.sources["overpass"]["enabled"] = True
