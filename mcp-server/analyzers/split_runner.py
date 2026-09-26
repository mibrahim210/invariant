"""Split runner – executed inside the TARGET's Python environment by verify_overlap.

Constraints:
- Uses only stdlib + pandas (no Invariant modules).
- Never imported by any Invariant code (run via subprocess only).
- Reads metadata CSV with pandas, preserving stored row order.
- row_id and group_key columns are read as str.
- Calls split_function(df, seed=split_seed).
- Converts both outputs to lists of str row IDs.
- Writes {"train": [...], "test": [...]} to an output path given as argv[1].

Usage:
    python split_runner.py <output_json_path> <target_root> <invariant_toml_path>
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(f"usage: split_runner.py <out.json> <target_root> <invariant.toml>")

    out_path = Path(sys.argv[1])
    target_root = Path(sys.argv[2])
    toml_path = Path(sys.argv[3])

    # Insert target root at the front of sys.path so target modules are importable.
    if str(target_root) not in sys.path:
        sys.path.insert(0, str(target_root))

    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    tcfg = cfg.get("target", {})
    split_function: str = tcfg.get("split_function") or cfg.get("split_function", "")
    metadata: str = tcfg.get("metadata") or cfg.get("metadata", "")
    row_id_col: str = tcfg.get("row_id") or cfg.get("row_id", "row_id")
    group_key: str = tcfg.get("group_key") or cfg.get("group_key", "")
    # Explicit None check: split_seed = 0 is valid and must not fall through to a default.
    split_seed = tcfg.get("split_seed", cfg.get("split_seed"))
    if split_seed is None:
        sys.exit("invariant.toml: split_seed not configured")

    if not split_function:
        sys.exit("invariant.toml: split_function not configured")
    if not metadata:
        sys.exit("invariant.toml: metadata not configured")

    import pandas as pd  # noqa: PLC0415  (deferred: only available in target env)

    csv_path = target_root / metadata
    # Only the identifier columns are forced to str; every other column keeps the dtype
    # the project itself would load, so the split sees the same data as training does.
    id_dtypes = {c: str for c in (row_id_col, group_key) if c}
    df = pd.read_csv(csv_path, dtype=id_dtypes)
    df = df.set_index(row_id_col)

    # Dynamically import and call the split function.
    module_dotted, func_name = split_function.rsplit(":", 1)
    import importlib  # noqa: PLC0415
    mod = importlib.import_module(module_dotted)
    fn = getattr(mod, func_name)

    train_out, test_out = fn(df, seed=split_seed)

    # The split contract returns index labels (array, Index or list). Accept a DataFrame
    # too, using its index. Convert to str lists, preserving order.
    def _labels(out) -> list[str]:
        if hasattr(out, "index") and hasattr(out, "columns"):
            out = out.index
        return [str(v) for v in list(out)]

    train_ids = _labels(train_out)
    test_ids = _labels(test_out)

    out_path.write_text(json.dumps({"train": train_ids, "test": test_ids}), encoding="utf-8")


if __name__ == "__main__":
    main()