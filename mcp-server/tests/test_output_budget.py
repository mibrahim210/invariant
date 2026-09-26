"""Output budget: all tool results must be < 2 KB of compact JSON."""
from __future__ import annotations

import json
from pathlib import Path

import analyzers.inspect_split as inspect_split
import analyzers.coverage as coverage
from analyzers.verify_overlap import _validate_partition
from analyzers.run_tests import _parse_junit
import textwrap

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

    def test_verify_overlap_valid_under_2kb(self):
        ordered = [f"r{i}" for i in range(100)]
        r2g = {r: f"G{i%10}" for i, r in enumerate(ordered)}
        train = ordered[:80]
        test = ordered[80:]
        state, errors, overlap, n_tr, n_te, tr_ex, te_ex = _validate_partition(
            train, test, ordered, r2g
        )
        result = {
            "state": state,
            "partition_errors": errors,
            "overlap_count": overlap,
            "train_group_count": n_tr,
            "test_group_count": n_te,
            "train_group_examples": tr_ex,
            "test_group_examples": te_ex,
        }
        assert _json_bytes(result) < 2048

    def test_verify_overlap_invalid_under_2kb(self):
        ordered = [f"r{i}" for i in range(20)]
        r2g = {r: f"G{i%3}" for i, r in enumerate(ordered)}
        # many errors: duplicates, unknown, overlap, omissions
        train = [f"r{i}" for i in range(10)] + ["X1", "X2"]
        test = [f"r{i}" for i in range(9, 15)] + ["Y1"]
        state, errors, overlap, n_tr, n_te, tr_ex, te_ex = _validate_partition(
            train, test, ordered, r2g
        )
        result = {
            "state": state,
            "partition_errors": errors,
            "overlap_count": overlap,
            "train_group_count": n_tr,
            "test_group_count": n_te,
            "train_group_examples": tr_ex,
            "test_group_examples": te_ex,
        }
        assert _json_bytes(result) < 2048

    def test_run_tests_result_under_2kb(self, tmp_path):
        xml = textwrap.dedent("""
            <testsuite tests="5" failures="1" errors="0" skipped="0">
              <testcase name="t1"/><testcase name="t2"/><testcase name="t3"/>
              <testcase name="t4"/><testcase name="t5"><failure message="bad"/></testcase>
            </testsuite>
        """)
        p = tmp_path / "junit.xml"
        p.write_text(xml, encoding="utf-8")
        counts = _parse_junit(p)
        result = {
            "state": "failed",
            "passed": counts["passed"],
            "failed": counts["failed"],
            "errors": counts["errors"],
            "skipped": counts["skipped"],
            "collected": counts["collected"],
        }
        assert _json_bytes(result) < 2048
