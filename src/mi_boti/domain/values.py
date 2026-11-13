"""Canonical persisted values; Discord snowflakes are strings, never signed ints."""

from datetime import datetime, timezone
import re

from .errors import ConfigurationError


def snowflake(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ConfigurationError("Expected a canonical positive Discord identifier.")
    if int(value) > 2**64 - 1:
        raise ConfigurationError("Discord identifier exceeds its supported range.")
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
