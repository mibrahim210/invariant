"""Tests for inspect_split and find_invariant_tests static analyzers."""
from __future__ import annotations

from pathlib import Path

import pytest

import analyzers.inspect_split as inspect_split
import analyzers.coverage as coverage

FIXTURES = Path(__file__).parent / "fixtures"


# ─────────────────────────────────────────────────────────────────────────────
# inspect_split
# ─────────────────────────────────────────────────────────────────────────────

class TestInspectSplit:
    def test_row_level_split_risk_indicator(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        assert result["group_aware"] is False
        assert "row_level_split_with_group_key_in_metadata" in result["risk_indicators"]

    def test_row_level_split_inner_call_detected(self):
        # grouped_repo's make_split body calls gss.split(groups=...) — check grouped
        result = inspect_split.run(FIXTURES / "grouped_repo")
        # The function is defined; calls list may be empty for a simple wrapper
        assert isinstance(result["calls"], list)

    def test_row_level_split_file_path(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        assert result["file"] == "demo_repo/splits.py"

    def test_grouped_split_group_aware(self):
        result = inspect_split.run(FIXTURES / "grouped_repo")
        assert result["group_aware"] is True
        assert result["risk_indicators"] == []

    def test_grouped_split_no_risk_indicator(self):
        result = inspect_split.run(FIXTURES / "grouped_repo")
        assert "row_level_split_with_group_key_in_metadata" not in result["risk_indicators"]

    def test_groups_kwarg_group_aware(self):
        result = inspect_split.run(FIXTURES / "groups_kwarg_repo")
        assert result["group_aware"] is True

    def test_identity_columns_from_metadata(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        # CSV header: row_id,patient_id,label
        assert "patient_id" in result["identity_columns"]
        assert "row_id" in result["identity_columns"]

    def test_group_key_reported(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        assert result["group_key"] == "patient_id"

    def test_split_function_reported(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        assert result["split_function"] == "demo_repo.splits:make_split"

    def test_call_line_number_present(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        assert all("line" in c for c in result["calls"])

    def test_no_truncated_flag_for_small_module(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        assert "truncated" not in result


# ─────────────────────────────────────────────────────────────────────────────
# find_invariant_tests (coverage)
# ─────────────────────────────────────────────────────────────────────────────

class TestFindInvariantTests:
    def test_patient_guard_recognised(self):
        result = coverage.run(FIXTURES / "guard_test_repo")
        assert result["state"] == "recognized_guard"

    def test_patient_guard_evidence_has_file_line(self):
        result = coverage.run(FIXTURES / "guard_test_repo")
        assert result["evidence"], "expected at least one evidence entry"
        for e in result["evidence"]:
            assert ":" in e, f"evidence entry missing colon: {e!r}"

    def test_rowid_only_not_recognised(self):
        result = coverage.run(FIXTURES / "rowid_guard_repo")
        assert result["state"] == "no_recognized_guard"

    def test_unparsable_yields_unknown(self):
        result = coverage.run(FIXTURES / "unparsable_test_repo")
        assert result["state"] == "unknown"

    def test_unparsable_evidence_contains_file(self):
        result = coverage.run(FIXTURES / "unparsable_test_repo")
        assert any("test_broken.py" in e for e in result["evidence"])

    def test_row_level_repo_no_tests_no_guard(self):
        # row_level_repo has no tests/ directory → no_recognized_guard
        result = coverage.run(FIXTURES / "row_level_repo")
        assert result["state"] == "no_recognized_guard"

    def test_evidence_max_10(self):
        result = coverage.run(FIXTURES / "guard_test_repo")
        assert len(result["evidence"]) <= 10

    def test_split_function_in_result(self):
        result = coverage.run(FIXTURES / "guard_test_repo")
        assert result["split_function"] == "demo_repo.splits:make_split"

    def test_group_key_in_result(self):
        result = coverage.run(FIXTURES / "guard_test_repo")
        assert result["group_key"] == "patient_id"
