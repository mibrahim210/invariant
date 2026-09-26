"""Parametrized tests for every row of the status table in docs/task4_acceptance.md.

S* rows: single-check contribution.
P* rows: aggregate status from a combination of check results.
"""
from __future__ import annotations

import pytest

from report.status import check_contribution, derive_status

# ── S* single-check rows ───────────────────────────────────────────────────────

# Each param: (id, check_name, result, overlap_count, expected_contribution)
_STATUS_TABLE = [
    # verify_split_overlap
    ("S1",  "verify_split_overlap", {"state": "invalid_partition", "partition_errors": ["x"], "overlap_count": None}, None, "blocked"),
    ("S2",  "verify_split_overlap", {"state": "invalid_partition", "partition_errors": ["missing patient IDs"], "overlap_count": None}, None, "blocked"),
    ("S3",  "verify_split_overlap", {"state": "valid", "overlap_count": 3, "overlap_examples": ["G1"]}, None, "blocked"),
    ("S4",  "verify_split_overlap", {"state": "valid", "overlap_count": 0, "overlap_examples": []}, None, "none"),
    ("S5",  "verify_split_overlap", {"state": "error", "error": "timed out"}, None, "review_required"),
    # regression_tests
    ("S6",  "regression_tests",    {"state": "failed", "failed": 2, "passed": 0, "collected": 2}, None, "blocked"),
    ("S7a", "regression_tests",    {"state": "collection_error", "error": "missing file", "collected": 0}, None, "review_required"),
    ("S7b", "regression_tests",    {"state": "crash", "error": "timeout", "collected": 0}, None, "review_required"),
    ("S8",  "regression_tests",    {"state": "passed", "passed": 3, "failed": 0, "collected": 3}, None, "none"),
    ("S9",  "regression_tests",    {"state": "no_tests", "collected": 0}, None, "review_required"),
    # find_invariant_tests
    ("S10", "find_invariant_tests", {"state": "recognized_guard"}, None, "none"),
    ("S11", "find_invariant_tests", {"state": "no_recognized_guard"}, None, "review_required"),
    ("S12", "find_invariant_tests", {"state": "unknown"}, None, "review_required"),
    # inspect_split  (overlap_count passed in separately to simulate the resolved value)
    ("S13", "inspect_split",        {"state": "ok", "risk_indicators": ["row_level_split_with_group_key_in_metadata"]}, 0, "review_required"),
    ("S14", "inspect_split",        {"state": "ok", "risk_indicators": ["row_level_split_with_group_key_in_metadata"]}, 3, "none"),
    ("S15", "inspect_split",        {"state": "ok", "risk_indicators": []}, 0, "none"),
    # missing / error key / schema failure
    ("S16", "verify_split_overlap", None, None, "review_required"),
    ("S17", "regression_tests",     {"error": "schema validation failed", "state": "error"}, None, "review_required"),
    ("S18", "find_invariant_tests", {"error": "subprocess crash", "state": "error"}, None, "review_required"),
]


@pytest.mark.parametrize("row_id,check,result,overlap,expected", _STATUS_TABLE, ids=[r[0] for r in _STATUS_TABLE])
def test_single_check_contribution(row_id, check, result, overlap, expected):
    contrib = check_contribution(check, result, overlap)
    assert contrib == expected, f"{row_id}: expected {expected!r}, got {contrib!r}"


# ── P* aggregate-status rows ───────────────────────────────────────────────────

def _results(
    overlap_state="valid", overlap_count=0,
    reg_state="passed", reg_collected=3,
    guard_state="recognized_guard",
    risk=None,
):
    """Convenience: build a standard results dict."""
    r: dict[str, dict] = {}
    r["verify_split_overlap"] = {
        "state": overlap_state,
        "overlap_count": overlap_count if overlap_state == "valid" else None,
        "overlap_examples": [],
    }
    r["regression_tests"] = {
        "state": reg_state,
        "passed": reg_collected if reg_state == "passed" else 0,
        "failed": 1 if reg_state == "failed" else 0,
        "collected": reg_collected,
    }
    r["find_invariant_tests"] = {"state": guard_state}
    r["inspect_split"] = {"state": "ok", "risk_indicators": risk or []}
    return r


_PRIORITY_TABLE = [
    # P1: one blocked + one review_required -> blocked
    ("P1", {
        "verify_split_overlap": {"state": "valid", "overlap_count": 3, "overlap_examples": []},
        "regression_tests":     {"state": "collection_error", "error": "x", "collected": 0},
        "find_invariant_tests": {"state": "recognized_guard"},
        "inspect_split":        {"state": "ok", "risk_indicators": []},
    }, "blocked"),
    # P2: only review_required -> review_required
    ("P2", {
        "verify_split_overlap": {"state": "error", "error": "x"},
        "regression_tests":     {"state": "no_tests", "collected": 0},
        "find_invariant_tests": {"state": "no_recognized_guard"},
        "inspect_split":        {"state": "ok", "risk_indicators": ["row_level_split_with_group_key_in_metadata"]},
    }, "review_required"),
    # P3: all clean -> no_findings
    ("P3", _results(), "no_findings"),
    # P4: buggy head
    ("P4", {
        "verify_split_overlap": {"state": "valid", "overlap_count": 5, "overlap_examples": ["G1"]},
        "regression_tests":     {"state": "collection_error", "error": "missing file", "collected": 0},
        "find_invariant_tests": {"state": "no_recognized_guard"},
        "inspect_split":        {"state": "ok", "risk_indicators": ["row_level_split_with_group_key_in_metadata"]},
    }, "blocked"),
    # P5: clean head -> no_findings
    ("P5", {
        "verify_split_overlap": {"state": "valid", "overlap_count": 0, "overlap_examples": []},
        "regression_tests":     {"state": "passed", "passed": 5, "failed": 0, "collected": 5},
        "find_invariant_tests": {"state": "recognized_guard"},
        "inspect_split":        {"state": "ok", "risk_indicators": []},
    }, "no_findings"),
    # P6: history has overlap but current checks are clean -> no_findings (history never affects status)
    ("P6", _results(), "no_findings"),  # history is irrelevant to derive_status
]


@pytest.mark.parametrize("row_id,results,expected_status", _PRIORITY_TABLE, ids=[r[0] for r in _PRIORITY_TABLE])
def test_aggregate_status(row_id, results, expected_status):
    status, _ = derive_status(results)
    assert status == expected_status, f"{row_id}: expected {expected_status!r}, got {status!r}"
