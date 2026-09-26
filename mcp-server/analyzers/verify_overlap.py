"""Execution analyser: run the split function and validate the partition contract.

Target code is executed exclusively via subprocess (split_runner.py in the target env).
Partition validation uses only the stdlib csv module – no pandas in this module.
"""
from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import tomllib
from pathlib import Path

from proc import log, run_proc

_RUNNER = Path(__file__).parent / "split_runner.py"
_RUNNER_TIMEOUT = 120


def _load_config(target: Path) -> dict:
    with open(target / "invariant.toml", "rb") as f:
        return tomllib.load(f)


def _read_metadata(target: Path, cfg: dict) -> tuple[list[str], dict[str, str]]:
    """Return (ordered_row_ids, row_id_to_group_key) using csv module only."""
    tcfg = cfg.get("target", {})
    metadata: str = tcfg.get("metadata") or cfg.get("metadata", "")
    row_id_col: str = tcfg.get("row_id") or cfg.get("row_id", "row_id")
    group_key: str = tcfg.get("group_key") or cfg.get("group_key", "")

    csv_path = target / metadata
    ordered_ids: list[str] = []
    row_to_group: dict[str, str] = {}

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = str(row.get(row_id_col, "")).strip()
            gid = str(row.get(group_key, "")).strip() if group_key else ""
            ordered_ids.append(rid)
            row_to_group[rid] = gid

    return ordered_ids, row_to_group


def _validate_partition(
    train_ids: list[str],
    test_ids: list[str],
    ordered_ids: list[str],
    row_to_group: dict[str, str],
) -> tuple[str, list[str], int | None, int, int, list[str], int]:
    """Validate the partition contract.

    Returns:
        state: "valid" | "invalid_partition"
        errors: list of human-readable error messages (max 10)
        overlap_count: number of GROUPS present in both train and test; None if invalid
        train_group_count: distinct group IDs in train
        test_group_count: distinct group IDs in test
        overlap_examples: up to 5 overlapping group IDs (empty if invalid)
        rows_partitioned: number of row IDs returned by the split
    """
    errors: list[str] = []
    known = set(ordered_ids)

    train_set = set(train_ids)
    test_set = set(test_ids)

    # Unique row IDs (no duplicates within each split)
    if len(train_ids) != len(train_set):
        dups = [rid for rid in train_ids if train_ids.count(rid) > 1]
        errors.append(f"duplicate row IDs in train: {list(dict.fromkeys(dups))[:5]}")
    if len(test_ids) != len(test_set):
        dups = [rid for rid in test_ids if test_ids.count(rid) > 1]
        errors.append(f"duplicate row IDs in test: {list(dict.fromkeys(dups))[:5]}")

    # Non-empty splits
    if not train_set:
        errors.append("train split is empty")
    if not test_set:
        errors.append("test split is empty")

    # No unknown IDs
    unknown_train = train_set - known
    unknown_test = test_set - known
    if unknown_train:
        errors.append(f"unknown row IDs in train: {sorted(unknown_train)[:5]}")
    if unknown_test:
        errors.append(f"unknown row IDs in test: {sorted(unknown_test)[:5]}")

    # No shared rows (a partition error, distinct from group overlap)
    shared_rows = train_set & test_set
    if shared_rows:
        errors.append(f"shared row IDs ({len(shared_rows)}): {sorted(shared_rows)[:5]}")

    # Union covers every row exactly once (no omissions)
    covered = train_set | test_set
    omitted = known - covered
    if omitted:
        errors.append(f"rows omitted from partition ({len(omitted)}): {sorted(omitted)[:5]}")

    # Non-missing group IDs
    missing_group_train = [r for r in train_ids if r in row_to_group and not row_to_group[r]]
    missing_group_test = [r for r in test_ids if r in row_to_group and not row_to_group[r]]
    if missing_group_train:
        errors.append(f"missing group_key in train rows: {missing_group_train[:5]}")
    if missing_group_test:
        errors.append(f"missing group_key in test rows: {missing_group_test[:5]}")

    train_group_set = {row_to_group[r] for r in train_set if row_to_group.get(r)}
    test_group_set = {row_to_group[r] for r in test_set if row_to_group.get(r)}
    # The measured quantity: groups (patients) present in both train and test.
    group_overlap = sorted(train_group_set & test_group_set)

    state = "valid" if not errors else "invalid_partition"
    return (
        state,
        errors[:10],
        # Never report a count for an invalid partition: it must not read as zero overlap.
        len(group_overlap) if state == "valid" else None,
        len(train_group_set),
        len(test_group_set),
        group_overlap[:5] if state == "valid" else [],
        len(train_set) + len(test_set),
    )


def run(target: Path) -> dict:
    try:
        cfg = _load_config(target)
    except Exception as exc:
        return {"state": "error", "error": f"cannot read invariant.toml: {exc}"}

    tcfg = cfg.get("target", {})
    split_function = tcfg.get("split_function") or cfg.get("split_function", "")
    metadata = tcfg.get("metadata") or cfg.get("metadata", "")

    if not split_function:
        return {"state": "error", "error": "split_function not configured in invariant.toml"}
    if not metadata:
        return {"state": "error", "error": "metadata not configured in invariant.toml"}

    # Run the split in the target's own environment via a temp file for output.
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", encoding="utf-8"
    ) as tf:
        out_path = Path(tf.name)

    try:
        cmd = [
            "uv", "run", "--locked", "--directory", str(target),
            "python", str(_RUNNER),
            str(out_path),
            str(target),
            str(target / "invariant.toml"),
        ]
        log(f"verify_overlap: launching runner for {target}")
        result = run_proc(cmd, timeout=_RUNNER_TIMEOUT)

        if result.returncode != 0:
            # Keep the tail: the exception type and message are on the last lines.
            stderr = result.stderr.strip()[-600:]
            log(f"verify_overlap: runner exit {result.returncode}: {stderr}")
            return {
                "state": "error",
                "error": f"split runner failed (exit {result.returncode})",
                "detail": stderr,
            }

        # Parse runner output (written to file, not stdout).
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"state": "error", "error": f"runner output unreadable: {exc}"}

        train_ids: list[str] = data.get("train", [])
        test_ids: list[str] = data.get("test", [])

    except subprocess.TimeoutExpired:
        log("verify_overlap: runner timed out")
        return {"state": "error", "error": "split runner timed out"}
    except FileNotFoundError as exc:
        return {"state": "error", "error": f"uv not found: {exc}"}
    finally:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass

    # Validate the partition using only the stdlib csv module.
    try:
        ordered_ids, row_to_group = _read_metadata(target, cfg)
    except Exception as exc:
        return {"state": "error", "error": f"cannot read metadata: {exc}"}

    state, errors, overlap_count, n_train_groups, n_test_groups, overlap_ex, n_rows = (
        _validate_partition(train_ids, test_ids, ordered_ids, row_to_group)
    )

    tcfg = cfg.get("target", {})
    result_dict: dict = {
        "state": state,
        "partition_errors": errors,
        "overlap_count": overlap_count,
        "overlap_examples": overlap_ex,
        "train_group_count": n_train_groups,
        "test_group_count": n_test_groups,
        "rows_partitioned": n_rows,
        "split_seed": tcfg.get("split_seed", cfg.get("split_seed")),
    }
    return result_dict