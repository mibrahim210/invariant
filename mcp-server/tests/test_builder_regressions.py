"""Check-result validation against the analyzers' real output shapes."""
from report.builder import _validate_check_result

INSPECT = {"file": "demo_repo/splits.py", "calls": [{"line": 9, "call": "train_test_split"}],
           "group_aware": False, "stratify_col": "label",
           "identity_columns": ["slice_id", "patient_id"], "risk_indicators": ["x"]}


def test_inspect_split_output_has_no_state_and_is_valid():
    assert _validate_check_result("inspect_split", INSPECT)


def test_inspect_split_missing_fields_is_invalid():
    assert not _validate_check_result("inspect_split", {"calls": []})


def test_verify_valid_requires_integer_overlap():
    assert _validate_check_result("verify_split_overlap", {"state": "valid", "overlap_count": 166})
    assert not _validate_check_result("verify_split_overlap", {"state": "valid", "overlap_count": None})
    assert _validate_check_result("verify_split_overlap", {"state": "invalid_partition", "overlap_count": None})


def test_unknown_states_are_invalid():
    assert not _validate_check_result("regression_tests", {"state": "green"})
    assert not _validate_check_result("find_invariant_tests", {"state": "maybe", "evidence": []})