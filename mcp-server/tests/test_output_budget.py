"""Output budget: both tool results must be < 2 KB of compact JSON."""
from __future__ import annotations

import json
from pathlib import Path

import analyzers.inspect_split as inspect_split
import analyzers.coverage as coverage

FIXTURES = Path(__file__).parent / "fixtures"

REPOS = [
    "row_level_repo",
    "grouped_repo",
    "groups_kwarg_repo",
    "guard_test_repo",
    "rowid_guard_repo",
    "unparsable_test_repo",
]


def _json_bytes(obj: dict) -> int:
    return len(json.dumps(obj, separators=(",", ":")).encode())


class TestOutputBudget:
    def test_inspect_split_under_2kb_row_level(self):
        result = inspect_split.run(FIXTURES / "row_level_repo")
        assert _json_bytes(result) < 2048, f"inspect_split result too large: {_json_bytes(result)} bytes"

    def test_inspect_split_under_2kb_grouped(self):
        result = inspect_split.run(FIXTURES / "grouped_repo")
        assert _json_bytes(result) < 2048

    def test_inspect_split_under_2kb_groups_kwarg(self):
        result = inspect_split.run(FIXTURES / "groups_kwarg_repo")
        assert _json_bytes(result) < 2048

    def test_coverage_under_2kb_guard_test(self):
        result = coverage.run(FIXTURES / "guard_test_repo")
        assert _json_bytes(result) < 2048

    def test_coverage_under_2kb_rowid_guard(self):
        result = coverage.run(FIXTURES / "rowid_guard_repo")
        assert _json_bytes(result) < 2048

    def test_coverage_under_2kb_unparsable(self):
        result = coverage.run(FIXTURES / "unparsable_test_repo")
        assert _json_bytes(result) < 2048
