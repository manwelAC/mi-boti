"""Pure campaign configuration, query/coverage and identity-review rules."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re

from ..discovery.planner import QuerySpec
from .errors import AppError
from .registry import RegistryError, encoded, normalized_text
from .values import snowflake


class CampaignError(AppError):
    code = "CAMPAIGN_INVALID"


class DiscoveryLifecycleError(AppError):
    code = "DISCOVERY_LIFECYCLE_INVALID"


RUBRIC_KEYS = (
    "business_fit",
    "software_fit",
    "operational_complexity",
    "evidence_quality",
    "contactability",
    "opportunity_confidence",
)
MANDATORY_RUBRIC_KEYS = (
    "business_fit",
    "software_fit",
    "evidence_quality",
    "opportunity_confidence",
)
DEFAULT_RUBRIC = {
    "version": "v1",
    "weights": {
        "business_fit": 20,
        "software_fit": 25,
        "operational_complexity": 15,
        "evidence_quality": 20,
        "contactability": 10,
        "opportunity_confidence": 10,
    },
    "qualification_threshold": 70.0,
    "minimum_coverage": 0.80,
    "required_minimum_ratings": {
        "business_fit": 3,
        "software_fit": 3,
        "evidence_quality": 3,
        "opportunity_confidence": 3,
    },
}


def validate_campaign_name(name: object) -> str:
    if not isinstance(name, str):
        raise CampaignError("Campaign name must be text.")
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= 80 or any(c in cleaned for c in "\r\n\x00"):
        raise CampaignError("Campaign name must be 1 to 80 characters without control characters.")
    if not normalized_text(cleaned):
        raise CampaignError("Campaign name must contain alphanumeric characters.")
    return cleaned


def _validate_cell(cell_id: object, bbox: object, max_bbox_degrees: float) -> dict:
    if not isinstance(cell_id, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,64}", cell_id):
        raise CampaignError("Geographic cell identifier is invalid.")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise CampaignError("Geographic bounds require four finite coordinates.")
    if any(type(v) not in {int, float} or not math.isfinite(v) for v in bbox):
        raise CampaignError("Geographic coordinates must be finite numbers.")
    south, west, north, east = (round(float(v), 8) for v in bbox)
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise CampaignError("Geographic coordinates are out of range or inverted.")
    if north - south > max_bbox_degrees or east - west > max_bbox_degrees:
        raise CampaignError("Geographic bounds exceed the maximum 1-degree bounding box.")
    return {"cell_id": cell_id, "bbox": [south, west, north, east]}


def _validate_rubric(rubric: object) -> dict:
    if rubric is None:
        return dict(DEFAULT_RUBRIC)
    if not isinstance(rubric, dict):
        raise CampaignError("Campaign rubric must be an object.")
    allowed = {"version", "weights", "qualification_threshold", "minimum_coverage", "required_minimum_ratings"}
    if set(rubric) - allowed:
        raise CampaignError("Campaign rubric contains unsupported fields.")
    version = rubric.get("version", "v1")
    if version != "v1":
        raise CampaignError("Only rubric version v1 is supported.")
    weights = rubric.get("weights", DEFAULT_RUBRIC["weights"])
    if not isinstance(weights, dict) or set(weights) != set(RUBRIC_KEYS):
        raise CampaignError("Campaign rubric requires all six criterion weights.")
    normalized_weights = {}
    for key in RUBRIC_KEYS:
        val = weights[key]
        if type(val) not in {int, float} or not math.isfinite(val) or val < 0:
            raise CampaignError("Rubric weights must be finite nonnegative numbers.")
        if key in MANDATORY_RUBRIC_KEYS and val <= 0:
            raise CampaignError("Mandatory rubric criteria must have positive weights.")
        normalized_weights[key] = round(float(val), 4) if isinstance(val, float) else int(val)
    if not math.isclose(sum(normalized_weights.values()), 100.0, rel_tol=0.0, abs_tol=1e-6):
        raise CampaignError("Rubric weights must sum to 100.")
    threshold = rubric.get("qualification_threshold", 70.0)
    if type(threshold) not in {int, float} or not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise CampaignError("Qualification threshold must be between 0 and 100.")
    coverage = rubric.get("minimum_coverage", 0.80)
    if type(coverage) not in {int, float} or not math.isfinite(coverage) or not 0 < coverage <= 1:
        raise CampaignError("Minimum coverage must be within (0, 1].")
    ratings = rubric.get("required_minimum_ratings", DEFAULT_RUBRIC["required_minimum_ratings"])
    if not isinstance(ratings, dict) or set(ratings) != set(MANDATORY_RUBRIC_KEYS):
        raise CampaignError("Required minimum ratings must specify the four mandatory criteria.")
    normalized_ratings = {}
    for key in MANDATORY_RUBRIC_KEYS:
        rating = ratings[key]
        if type(rating) is not int or not 0 <= rating <= 5:
            raise CampaignError("Required minimum ratings must be integers between 0 and 5.")
        normalized_ratings[key] = rating
    return {
        "version": "v1",
        "weights": normalized_weights,
        "qualification_threshold": float(threshold),
        "minimum_coverage": float(coverage),
        "required_minimum_ratings": normalized_ratings,
    }


def validate_campaign_config(
    config: object,
    *,
    max_bbox_degrees: float = 1.0,
    max_tags: int = 100,
    allowed_categories: frozenset[str] = frozenset({"cafe", "restaurant"}),
) -> dict:
    if not isinstance(config, dict):
        raise CampaignError("Campaign configuration must be a JSON object.")
    allowed_keys = {
        "schema_version",
        "target_categories",
        "geography",
        "exclusions",
        "provider_id",
        "service_description",
        "rubric",
    }
    if set(config) - allowed_keys:
        raise CampaignError("Campaign configuration contains unknown fields.")
    if config.get("schema_version", 1) != 1:
        raise CampaignError("Campaign configuration schema_version must be 1.")
    raw_categories = config.get("target_categories")
    if (
        not isinstance(raw_categories, (list, tuple))
        or not raw_categories
        or len(raw_categories) > max_tags
        or any(not isinstance(c, str) or c not in allowed_categories for c in raw_categories)
    ):
        raise CampaignError("Campaign target_categories must select approved discovery categories.")
    categories = sorted(set(raw_categories))
    geography = config.get("geography")
    if not isinstance(geography, dict) or set(geography) - {"country_code", "locality", "bbox", "cells"}:
        raise CampaignError("Campaign geography must be a valid object.")
    country_code = geography.get("country_code", "PH")
    if country_code != "PH":
        raise CampaignError("Initial target market country_code must be PH.")
    locality = geography.get("locality", "Quezon City")
    if not isinstance(locality, str) or not 1 <= len(locality.strip()) <= 80 or any(c in locality for c in "\r\n\x00"):
        raise CampaignError("Campaign locality must be 1 to 80 characters without control characters.")
    locality = locality.strip()
    raw_cells = geography.get("cells")
    raw_bbox = geography.get("bbox")
    if raw_cells is not None:
        if not isinstance(raw_cells, (list, tuple)) or not 1 <= len(raw_cells) <= 25:
            raise CampaignError("Campaign geography cells must contain 1 to 25 bounded cells.")
        cells = []
        seen_ids = set()
        for item in raw_cells:
            if not isinstance(item, dict) or set(item) != {"cell_id", "bbox"}:
                raise CampaignError("Each geographic cell requires cell_id and bbox.")
            validated = _validate_cell(item["cell_id"], item["bbox"], max_bbox_degrees)
            if validated["cell_id"] in seen_ids:
                raise CampaignError("Geographic cell identifiers must be unique within a campaign.")
            seen_ids.add(validated["cell_id"])
            cells.append(validated)
        bbox = cells[0]["bbox"] if len(cells) == 1 and raw_bbox is None else None
        if raw_bbox is not None:
            bbox = _validate_cell("envelope", raw_bbox, max_bbox_degrees)["bbox"]
    elif raw_bbox is not None:
        single = _validate_cell("default", raw_bbox, max_bbox_degrees)
        cells = [single]
        bbox = single["bbox"]
    else:
        raise CampaignError("Campaign geography requires a bounded bbox or cells list.")
    exclusions = config.get("exclusions", [])
    if (
        not isinstance(exclusions, (list, tuple))
        or len(exclusions) > 50
        or any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 120 or any(c in x for c in "\r\n\x00") for x in exclusions)
    ):
        raise CampaignError("Campaign exclusions must be up to 50 short plain-text terms.")
    normalized_exclusions = sorted({normalized_text(x) for x in exclusions if normalized_text(x)})
    provider_id = config.get("provider_id")
    if provider_id is not None:
        raise CampaignError("AI providers are not verified (L02 blocked); campaigns must omit provider_id in the non-AI release.")
    description = config.get("service_description", "")
    if not isinstance(description, str) or len(description) > 2000 or "\x00" in description:
        raise CampaignError("Service description must be at most 2,000 characters without null bytes.")
    description = description.strip()
    rubric = _validate_rubric(config.get("rubric"))
    normalized = {
        "schema_version": 1,
        "target_categories": categories,
        "geography": {
            "country_code": "PH",
            "locality": locality,
            "bbox": bbox if bbox is not None else cells[0]["bbox"],
            "cells": cells,
        },
        "exclusions": normalized_exclusions,
        "provider_id": None,
        "service_description": description,
        "rubric": rubric,
    }
    if len(encoded(normalized).encode("utf-8")) > 32768:
        raise CampaignError("Campaign configuration exceeds size limits.")
    return normalized


@dataclass(frozen=True)
class PlannedCellQuery:
    geographic_cell: str
    spec: QuerySpec


def plan_campaign_queries(
    campaign_config: dict,
    *,
    campaign_version: int,
    policy_version: str,
    limit: int = 25,
    fresh_hashes_by_cell: dict[str, set[str]] | None = None,
) -> tuple[PlannedCellQuery, ...]:
    validated = validate_campaign_config(campaign_config)
    if type(campaign_version) is not int or campaign_version < 1:
        raise DiscoveryLifecycleError("Campaign version must be a positive integer.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise DiscoveryLifecycleError("Discovery limit must be an integer between 1 and 100.")
    fresh = fresh_hashes_by_cell or {}
    planned = []
    categories = tuple(validated["target_categories"])
    for cell in validated["geography"]["cells"]:
        spec = QuerySpec(
            bbox=tuple(cell["bbox"]),
            categories=categories,
            limit=limit,
            target_version=campaign_version,
            policy_version=policy_version,
        )
        if spec.fingerprint in fresh.get(cell["cell_id"], set()):
            continue
        planned.append(PlannedCellQuery(geographic_cell=cell["cell_id"], spec=spec))
    return tuple(planned)


def parse_utc(timestamp: str) -> datetime:
    try:
        parsed = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != timestamp:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        raise DiscoveryLifecycleError("Expected a canonical UTC timestamp.") from None


def is_coverage_fresh(observed_at: str, now: str, ttl_seconds: int = 2592000) -> bool:
    if type(ttl_seconds) is not int or ttl_seconds <= 0:
        raise DiscoveryLifecycleError("Coverage TTL must be a positive integer.")
    observed = parse_utc(observed_at)
    current = parse_utc(now)
    elapsed = (current - observed).total_seconds()
    return 0 <= elapsed < ttl_seconds


def validate_rationale(rationale: object) -> str:
    if not isinstance(rationale, str):
        raise RegistryError("Resolution rationale must be text.")
    cleaned = rationale.strip()
    if not 1 <= len(cleaned) <= 1000 or "\x00" in cleaned:
        raise RegistryError("Resolution rationale must be 1 to 1,000 characters without null bytes.")
    return cleaned


def validate_actor(actor_id: object) -> str:
    return snowflake(actor_id)
