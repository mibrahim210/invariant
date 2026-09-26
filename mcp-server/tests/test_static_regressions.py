"""Regression tests for the static analyzers against realistic target layouts."""
from pathlib import Path

from analyzers import coverage, inspect_split

TOML = '''[target]
metadata = "data/metadata.csv"
row_id = "slice_id"
group_key = "patient_id"
split_function = "demo_repo.splits:make_split"
'''
ROW_LEVEL = '''from sklearn.model_selection import train_test_split


def make_split(df, seed=0, test_size=0.2):
    train_ids, test_ids = train_test_split(
        df.index.to_numpy(), test_size=test_size, random_state=seed,
        shuffle=True, stratify=df["label"],
    )
    return train_ids, test_ids
'''
GROUPED = '''from sklearn.model_selection import GroupShuffleSplit


def make_split(df, seed=0, test_size=0.2):
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(gss.split(df, groups=df["patient_id"]))
    return df.index[train_idx], df.index[test_idx]
'''
HELPER_GUARD = '''from demo_repo.splits import make_split


def patient_overlap(df, train_idx, test_idx):
    return set(df.loc[train_idx, "patient_id"]) & set(df.loc[test_idx, "patient_id"])


def test_no_overlap():
    df = None
    train_idx, test_idx = make_split(df, seed=0)
    overlap = patient_overlap(df, train_idx, test_idx)
    assert not overlap, "leak"
'''
ROW_ID_ONLY = '''from demo_repo.splits import make_split


def test_rows_disjoint():
    train_ids, test_ids = make_split(None, seed=0)
    assert not set(train_ids) & set(test_ids)
'''


def make_target(tmp: Path, split_src: str, tests: dict[str, str], bom: bool = False) -> Path:
    (tmp / "demo_repo").mkdir(parents=True)
    (tmp / "demo_repo" / "splits.py").write_text(split_src, encoding="utf-8")
    (tmp / "data").mkdir()
    (tmp / "data" / "metadata.csv").write_text(
        "slice_id,patient_id,study_id,slice_index,array_path,label,generator_version\n", encoding="utf-8")
    (tmp / "invariant.toml").write_text(TOML, encoding="utf-8")
    (tmp / "tests").mkdir()
    for name, src in tests.items():
        (tmp / "tests" / name).write_text(src, encoding="utf-8-sig" if bom else "utf-8")
    return tmp


def test_row_level_split_reports_call_line_and_stratify(tmp_path):
    out = inspect_split.run(make_target(tmp_path, ROW_LEVEL, {}))
    assert out["calls"] == [{"line": 5, "call": "train_test_split", "stratify": "label"}]
    assert out["stratify_col"] == "label" and out["group_aware"] is False
    assert out["identity_columns"] == ["slice_id", "patient_id", "study_id"]
    assert "row_level_split_with_group_key_in_metadata" in out["risk_indicators"]


def test_grouped_split_is_group_aware_without_risk(tmp_path):
    out = inspect_split.run(make_target(tmp_path, GROUPED, {}))
    assert out["group_aware"] is True and out["risk_indicators"] == []
    assert [c["call"] for c in out["calls"]] == ["GroupShuffleSplit", "split"]


def test_helper_based_guard_is_recognized(tmp_path):
    out = coverage.run(make_target(tmp_path, GROUPED, {"test_split_invariants.py": HELPER_GUARD}))
    assert out["state"] == "recognized_guard"
    assert out["evidence"] == ["tests/test_split_invariants.py:8"]


def test_bom_encoded_test_file_still_parses(tmp_path):
    out = coverage.run(make_target(tmp_path, GROUPED, {"test_split_invariants.py": HELPER_GUARD}, bom=True))
    assert out["state"] == "recognized_guard"


def test_row_id_disjointness_is_not_a_guard(tmp_path):
    out = coverage.run(make_target(tmp_path, ROW_LEVEL, {"test_split_shapes.py": ROW_ID_ONLY}))
    assert out["state"] == "no_recognized_guard" and out["evidence"] == []


def test_unparsable_file_reports_relative_path_and_line(tmp_path):
    out = coverage.run(make_target(tmp_path, ROW_LEVEL, {"test_broken.py": "def test_x(:\n"}))
    assert out["state"] == "unknown"
    assert out["evidence"] == ["tests/test_broken.py:1"]