"""Manual CRM validation and the documented pipeline graph; no AI criteria."""

from datetime import datetime, timezone
from uuid import UUID

from .errors import AppError


class CrmError(AppError):
    code = "CRM_INVALID"


TRANSITIONS = {
    "NEW": frozenset({"REVIEWING", "ARCHIVED"}),
    "REVIEWING": frozenset({"READY", "LOST", "ARCHIVED"}),
    "READY": frozenset({"CONTACTED", "REVIEWING", "LOST", "ARCHIVED"}),
    "CONTACTED": frozenset({"FOLLOW_UP", "WON", "LOST", "ARCHIVED"}),
    "FOLLOW_UP": frozenset({"CONTACTED", "WON", "LOST", "ARCHIVED"}),
    "WON": frozenset({"REVIEWING"}),
    "LOST": frozenset({"REVIEWING"}),
    "ARCHIVED": frozenset({"REVIEWING"}),
}


def identifier(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise CrmError("Use an existing record UUID.") from None


def text(value, *, required=True):
    if value is None and not required: return ""
    if not isinstance(value, str) or "\x00" in value or len(value) > 2000:
        raise CrmError("Notes and review rationale must be plain text of at most 2,000 characters without null bytes.")
    value = value.strip()
    if required and not value: raise CrmError("A nonempty note or review rationale is required.")
    return value


def revision(value):
    if type(value) is not int or value < 1:
        raise CrmError("A positive expected revision is required.")
    return value


def evidence_ids(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 10:
        raise CrmError("Select one to ten evidence UUIDs for explicit review.")
    values = tuple(identifier(value) for value in values)
    if len(set(values)) != len(values): raise CrmError("Do not repeat evidence UUIDs.")
    return values


def due_time(value, now):
    try:
        if not isinstance(value, str) or len(value) > 64: raise ValueError
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        current = datetime.fromisoformat(now.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp <= current: raise ValueError
        return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise CrmError("Follow-up time must be a future ISO timestamp with a timezone offset.") from None
