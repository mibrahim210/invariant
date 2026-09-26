"""Regression tests: overlap is measured on groups, and invalid partitions never read as zero."""
import os
from pathlib import Path

import pytest

from analyzers import run_tests, verify_overlap

ROWS = [f"P{p}_S{s}" for p in range(4) for s in range(2)]          # 4 patients x 2 slices
GROUPS = {r: r.split("_")[0] for r in ROWS}


def validate(train, test, groups=GROUPS):
    return verify_overlap._validate_partition(train, test, ROWS, groups)


def test_row_level_partition_measures_patient_overlap():
    # A valid row partition in which every patient has one slice on each side.
    train = [r for r in ROWS if r.endswith("_S0")]
    test = [r for r in ROWS if r.endswith("_S1")]
    state, errors, overlap, n_train, n_test, examples, n_rows = validate(train, test)
    assert state == "valid" and errors == []
    assert overlap == 4 and examples == ["P0", "P1", "P2", "P3"]
    assert (n_train, n_test, n_rows) == (4, 4, 8)


def test_grouped_partition_has_zero_overlap():
    train = [r for r in ROWS if r < "P2"]
    test = [r for r in ROWS if r >= "P2"]
    state, _, overlap, _, _, examples, _ = validate(train, test)
    assert state == "valid" and overlap == 0 and examples == []


@pytest.mark.parametrize("train, test", [
    (ROWS, []),                                   # empty test set
    (ROWS[:5], ROWS[4:]),                         # shared row
    (ROWS[:3], ROWS[4:]),                         # omitted row
    (ROWS[:4] + ["X"], ROWS[4:]),                 # unknown row
])
def test_invalid_partition_never_reports_an_overlap_count(train, test):
    state, errors, overlap, *_ = validate(train, test)
    assert state == "invalid_partition" and errors
    assert overlap is None


def test_exit_2_without_failures_is_a_collection_error(tmp_path, monkeypatch):
    target = tmp_path
    (target / "invariant.toml").write_text('[checks]\nregression_tests = ["tests/t.py"]\n', encoding="utf-8")
    (target / "tests").mkdir()
    (target / "tests" / "t.py").write_text("import nonexistent_module\n", encoding="utf-8")

    class Done:
        returncode, stdout, stderr = 2, "", ""

    def fake_run_proc(cmd, cwd=None, timeout=0):
        junit = next(a.split("=", 1)[1] for a in cmd if a.startswith("--junitxml="))
        Path(junit).write_text('<testsuite tests="0" failures="0" errors="1" skipped="0"/>', encoding="utf-8")
        return Done()

    monkeypatch.setattr(run_tests, "run_proc", fake_run_proc)
    assert run_tests.run(target)["state"] == "collection_error"


@pytest.mark.skipif(not os.environ.get("INVARIANT_DEMO_REPO"), reason="INVARIANT_DEMO_REPO not set")
def test_demo_repo_uses_configured_seed_and_measures_patients():
    out = verify_overlap.run(Path(os.environ["INVARIANT_DEMO_REPO"]))
    assert out["state"] == "valid" and out["overlap_count"] > 0
    assert out["split_seed"] == 0