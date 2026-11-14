import pytest

from mi_boti.domain.campaigns import (
    CampaignError,
    DEFAULT_RUBRIC,
    DiscoveryLifecycleError,
    is_coverage_fresh,
    plan_campaign_queries,
    validate_campaign_config,
    validate_campaign_name,
    validate_rationale,
)


def valid_config(**overrides):
    base = {
        "schema_version": 1,
        "target_categories": ["restaurant", "cafe"],
        "geography": {
            "country_code": "PH",
            "locality": "Quezon City",
            "bbox": [14.648, 121.047, 14.657, 121.061],
        },
        "exclusions": ["  Fast Food  ", "fast-food"],
        "provider_id": None,
        "service_description": "Custom ordering and kitchen workflow software",
    }
    base.update(overrides)
    return base


def test_campaign_name_and_default_rubric_validation():
    assert validate_campaign_name("  Quezon City Cafes  ") == "Quezon City Cafes"
    cfg = validate_campaign_config(valid_config())
    assert cfg["target_categories"] == ["cafe", "restaurant"]
    assert cfg["exclusions"] == ["fast food"]
    assert cfg["provider_id"] is None
    assert cfg["rubric"] == DEFAULT_RUBRIC
    assert cfg["geography"]["cells"] == [
        {"cell_id": "default", "bbox": [14.648, 121.047, 14.657, 121.061]}
    ]


@pytest.mark.parametrize(
    "bad_name",
    ["", "   ", "---", "a" * 81, "bad\nname", "bad\x00name", 123],
)
def test_invalid_campaign_names_rejected(bad_name):
    with pytest.raises(CampaignError):
        validate_campaign_name(bad_name)


@pytest.mark.parametrize(
    "override",
    [
        {"schema_version": 2},
        {"unknown_key": True},
        {"target_categories": []},
        {"target_categories": ["hotel"]},
        {"provider_id": "agy"},
        {"service_description": "x" * 2001},
        {"geography": {"country_code": "SG", "bbox": [1.3, 103.8, 1.35, 103.85]}},
        {"geography": {"country_code": "PH", "bbox": [14.0, 121.0, 15.5, 121.5]}},
        {"geography": {"country_code": "PH", "bbox": [14.6, 121.0, 14.5, 121.5]}},
        {
            "rubric": {
                "version": "v1",
                "weights": {
                    "business_fit": 10,
                    "software_fit": 25,
                    "operational_complexity": 15,
                    "evidence_quality": 20,
                    "contactability": 10,
                    "opportunity_confidence": 10,
                },
            }
        },
        {
            "rubric": {
                "version": "v1",
                "weights": {
                    "business_fit": 0,
                    "software_fit": 45,
                    "operational_complexity": 15,
                    "evidence_quality": 20,
                    "contactability": 10,
                    "opportunity_confidence": 10,
                },
            }
        },
    ],
)
def test_invalid_campaign_configurations_fail_closed(override):
    with pytest.raises(CampaignError):
        validate_campaign_config(valid_config(**override))


def test_plan_campaign_queries_skips_fresh_cells_only_for_matching_fingerprint():
    cfg = valid_config(
        geography={
            "country_code": "PH",
            "locality": "Quezon City",
            "cells": [
                {"cell_id": "qc-north", "bbox": [14.650, 121.047, 14.657, 121.061]},
                {"cell_id": "qc-south", "bbox": [14.640, 121.047, 14.649, 121.061]},
            ],
        }
    )
    all_planned = plan_campaign_queries(cfg, campaign_version=1, policy_version="osm-v1", limit=25)
    assert [p.geographic_cell for p in all_planned] == ["qc-north", "qc-south"]
    filtered = plan_campaign_queries(
        cfg,
        campaign_version=1,
        policy_version="osm-v1",
        limit=25,
        fresh_hashes_by_cell={"qc-north": {all_planned[0].spec.fingerprint}},
    )
    assert [p.geographic_cell for p in filtered] == ["qc-south"]
    # A new campaign version changes query fingerprint so prior cell is planned again.
    re_planned = plan_campaign_queries(
        cfg,
        campaign_version=2,
        policy_version="osm-v1",
        limit=25,
        fresh_hashes_by_cell={"qc-north": {all_planned[0].spec.fingerprint}},
    )
    assert [p.geographic_cell for p in re_planned] == ["qc-north", "qc-south"]


def test_coverage_freshness_respects_ttl_and_rejects_clock_rollback():
    observed = "2026-11-01T00:00:00.000000Z"
    assert is_coverage_fresh(observed, "2026-11-15T00:00:00.000000Z", ttl_seconds=2592000)
    assert not is_coverage_fresh(observed, "2026-12-02T00:00:00.000000Z", ttl_seconds=2592000)
    assert not is_coverage_fresh(observed, "2026-10-31T23:59:59.000000Z", ttl_seconds=2592000)
    with pytest.raises(DiscoveryLifecycleError):
        is_coverage_fresh("bad", observed)


def test_rationale_validation():
    assert validate_rationale("  Verified separate branch address. ") == "Verified separate branch address."
    for bad in ("", "   ", "x" * 1001, "bad\x00text", None):
        with pytest.raises( Exception ):
            validate_rationale(bad)
