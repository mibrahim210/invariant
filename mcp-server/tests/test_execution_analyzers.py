"""Unit tests for execution analyser internals: partition validation and junit parsing.

All tests use in-memory fixtures only – no subprocess execution.
Integration tests requiring INVARIANT_DEMO_REPO are skipped when the env var is not set.
"""
from __future__ import annotations

import json
import os
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from analyzers.verify_overlap import _validate_partition
from analyzers.run_tests import _parse_junit


# ─────────────────────────────────────────────────────────────────────────────
# _validate_partition helpers
# ─────────────────────────────────────────────────────────────────────────────

def _simple_meta(row_ids: list[str], group_key: str = "patient_id") -> tuple[list[str], dict[str, str]]:
    """Build ordered_ids and row_to_group from a list of (row_id, group) pairs or bare ids."""
    ordered = row_ids
    # Assign alternating groups for convenience
    groups = ["G1", "G2", "G3"]
    row_to_group = {rid: groups[i % len(groups)] for i, rid in enumerate(row_ids)}
    return ordered, row_to_group


def _vp(train, test, ordered=None, r2g=None):
    """Shorthand: validate_partition with simple defaults."""
    if ordered is None:
        ordered = train + test
    if r2g is None:
        _, r2g = _simple_meta(ordered)
    return _validate_partition(train, test, ordered, r2g)


class TestValidatePartition:

    # ── valid partition ───────────────────────────────────────────────────────

    def test_valid_partition(self):
        ordered = ["r1", "r2", "r3", "r4"]
        r2g = {"r1": "G1", "r2": "G1", "r3": "G2", "r4": "G2"}
        state, errors, overlap, *_ = _validate_partition(["r1", "r2"], ["r3", "r4"], ordered, r2g)
        assert state == "valid"
        assert errors == []
        assert overlap == 0

    def test_valid_group_counts(self):
        ordered = ["r1", "r2", "r3", "r4"]
        r2g = {"r1": "G1", "r2": "G1", "r3": "G2", "r4": "G3"}
        state, errors, overlap, n_train, n_test, overlap_ex, n_rows = _validate_partition(
            ["r1", "r2"], ["r3", "r4"], ordered, r2g
        )
        assert state == "valid" and errors == []
        assert n_train == 1  # only G1
        assert n_test == 2   # G2, G3
        assert overlap == 0 and overlap_ex == []
        assert n_rows == 4

    def test_group_overlap_is_counted_on_groups(self):
        ordered = ["r1", "r2", "r3", "r4"]
        r2g = {"r1": "G1", "r2": "G2", "r3": "G1", "r4": "G3"}   # G1 on both sides
        state, errors, overlap, _, _, overlap_ex, _ = _validate_partition(
            ["r1", "r2"], ["r3", "r4"], ordered, r2g
        )
        assert state == "valid" and errors == []
        assert overlap == 1 and overlap_ex == ["G1"]

    # ── empty split ───────────────────────────────────────────────────────────

    def test_empty_train_is_invalid(self):
        state, errors, *_ = _vp([], ["r1"])
        assert state == "invalid_partition"
        assert any("train" in e and "empty" in e for e in errors)

    def test_empty_test_is_invalid(self):
        state, errors, *_ = _vp(["r1"], [])
        assert state == "invalid_partition"
        assert any("test" in e and "empty" in e for e in errors)

    # ── duplicate IDs ─────────────────────────────────────────────────────────

    def test_duplicate_in_train(self):
        state, errors, *_ = _vp(["r1", "r1"], ["r2"], ordered=["r1", "r2"])
        assert state == "invalid_partition"
        assert any("duplicate" in e and "train" in e for e in errors)

    def test_duplicate_in_test(self):
        state, errors, *_ = _vp(["r1"], ["r2", "r2"], ordered=["r1", "r2"])
        assert state == "invalid_partition"
        assert any("duplicate" in e and "test" in e for e in errors)

    # ── unknown IDs ───────────────────────────────────────────────────────────

    def test_unknown_in_train(self):
        state, errors, *_ = _vp(["r1", "UNKNOWN"], ["r2"], ordered=["r1", "r2"])
        assert state == "invalid_partition"
        assert any("unknown" in e and "train" in e for e in errors)

    def test_unknown_in_test(self):
        state, errors, *_ = _vp(["r1"], ["r2", "UNKNOWN"], ordered=["r1", "r2"])
        assert state == "invalid_partition"
        assert any("unknown" in e and "test" in e for e in errors)

    # ── shared rows (overlap) ─────────────────────────────────────────────────

    def test_shared_row_is_invalid_without_overlap_count(self):
        state, errors, overlap, *_ = _vp(["r1", "r2"], ["r2", "r3"],
                                          ordered=["r1", "r2", "r3"])
        assert state == "invalid_partition"
        assert overlap is None
        assert any("shared row IDs" in e for e in errors)

    def test_invalid_partition_never_reports_an_overlap_count(self):
        """Invalid partitions carry errors and no count, so they can never read as zero overlap."""
        state, errors, overlap, *_ = _vp(["r1", "r2"], ["r2"], ordered=["r1", "r2"])
        assert state == "invalid_partition"
        assert errors
        assert overlap is None

    # ── omitted rows ─────────────────────────────────────────────────────────

    def test_omitted_row_is_invalid(self):
        # "r3" exists in metadata but is in neither split
        state, errors, *_ = _vp(["r1"], ["r2"], ordered=["r1", "r2", "r3"])
        assert state == "invalid_partition"
        assert any("omit" in e for e in errors)

    # ── missing group ID ─────────────────────────────────────────────────────

    def test_missing_group_id_in_train(self):
        ordered = ["r1", "r2"]
        r2g = {"r1": "", "r2": "G1"}  # r1 has no group
        state, errors, *_ = _validate_partition(["r1"], ["r2"], ordered, r2g)
        assert state == "invalid_partition"
        assert any("missing group" in e and "train" in e for e in errors)

    def test_missing_group_id_in_test(self):
        ordered = ["r1", "r2"]
        r2g = {"r1": "G1", "r2": ""}
        state, errors, *_ = _validate_partition(["r1"], ["r2"], ordered, r2g)
        assert state == "invalid_partition"
        assert any("missing group" in e and "test" in e for e in errors)

    # ── error list length cap ─────────────────────────────────────────────────

    def test_errors_capped_at_10(self):
        # Create many violations at once (many unknowns)
        train = [f"X{i}" for i in range(20)]
        test = [f"Y{i}" for i in range(20)]
        ordered = [f"r{i}" for i in range(5)]
        r2g = {r: "G1" for r in ordered}
        _, errors, *_ = _validate_partition(train, test, ordered, r2g)
        assert len(errors) <= 10


# ─────────────────────────────────────────────────────────────────────────────
# _parse_junit helpers
# ─────────────────────────────────────────────────────────────────────────────

def _write_junit(tmp_path: Path, xml: str) -> Path:
    p = tmp_path / "junit.xml"
    p.write_text(textwrap.dedent(xml), encoding="utf-8")
    return p


class TestParseJunit:

    def test_all_passed(self, tmp_path):
        p = _write_junit(tmp_path, """
            <testsuite tests="3" failures="0" errors="0" skipped="0">
              <testcase name="t1"/><testcase name="t2"/><testcase name="t3"/>
            </testsuite>
        """)
        r = _parse_junit(p)
        assert r == {"passed": 3, "failed": 0, "errors": 0, "skipped": 0, "collected": 3}

    def test_some_failed(self, tmp_path):
        p = _write_junit(tmp_path, """
            <testsuite tests="4" failures="2" errors="0" skipped="0">
              <testcase name="t1"/>
              <testcase name="t2"><failure message="oops"/></testcase>
              <testcase name="t3"><failure message="bad"/></testcase>
              <testcase name="t4"/>
            </testsuite>
        """)
        r = _parse_junit(p)
        assert r["failed"] == 2
        assert r["passed"] == 2
        assert r["collected"] == 4

    def test_with_errors(self, tmp_path):
        p = _write_junit(tmp_path, """
            <testsuite tests="2" failures="0" errors="1" skipped="0">
              <testcase name="t1"><error message="boom"/></testcase>
              <testcase name="t2"/>
            </testsuite>
        """)
        r = _parse_junit(p)
        assert r["errors"] == 1
        assert r["passed"] == 1

    def test_zero_collected(self, tmp_path):
        p = _write_junit(tmp_path, """
            <testsuite tests="0" failures="0" errors="0" skipped="0"/>
        """)
        r = _parse_junit(p)
        assert r["collected"] == 0
        assert r["passed"] == 0

    def test_missing_file_returns_parse_error(self, tmp_path):
        r = _parse_junit(tmp_path / "no_such_file.xml")
        assert "_parse_error" in r

    def test_malformed_xml_returns_parse_error(self, tmp_path):
        p = tmp_path / "bad.xml"
        p.write_text("this is not xml <<<", encoding="utf-8")
        r = _parse_junit(p)
        assert "_parse_error" in r

    def test_testsuites_wrapper(self, tmp_path):
        p = _write_junit(tmp_path, """
            <testsuites>
              <testsuite tests="2" failures="1" errors="0" skipped="0">
                <testcase name="t1"/><testcase name="t2"><failure/></testcase>
              </testsuite>
              <testsuite tests="1" failures="0" errors="0" skipped="0">
                <testcase name="t3"/>
              </testsuite>
            </testsuites>
        """)
        r = _parse_junit(p)
        assert r["collected"] == 3
        assert r["failed"] == 1
        assert r["passed"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Integration test (requires INVARIANT_DEMO_REPO env var)
# ─────────────────────────────────────────────────────────────────────────────

_DEMO_REPO = os.environ.get("INVARIANT_DEMO_REPO")

@pytest.mark.skipif(not _DEMO_REPO, reason="INVARIANT_DEMO_REPO not set")
def test_integration_verify_overlap_valid():
    """Integration: the demo repo's row-level split must be valid and leak patients."""
    import analyzers.verify_overlap as verify_overlap
    result = verify_overlap.run(Path(_DEMO_REPO))
    assert result["state"] == "valid", f"unexpected state: {result}"
    assert result["overlap_count"] > 0, f"expected patient overlap on the buggy split: {result}"
    assert result["split_seed"] == 0
