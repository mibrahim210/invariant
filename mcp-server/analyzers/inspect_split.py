"""Static analyser: inspect the configured split function without executing it."""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path

# Splitter names that are group-aware by design.
_GROUP_AWARE_CLASSES = {
    "GroupShuffleSplit",
    "GroupKFold",
    "StratifiedGroupKFold",
    "LeaveOneGroupOut",
}
# Row-level splitters: they partition rows and ignore groups.
_ROW_LEVEL_SPLITTERS = {
    "train_test_split",
    "ShuffleSplit",
    "StratifiedShuffleSplit",
    "KFold",
    "StratifiedKFold",
    "RepeatedKFold",
    "RepeatedStratifiedKFold",
}
_SPLITTERS = _GROUP_AWARE_CLASSES | _ROW_LEVEL_SPLITTERS


def _load_config(target: Path) -> dict:
    with open(target / "invariant.toml", "rb") as f:
        return tomllib.load(f)


def _resolve_split_module(target: Path, split_function: str) -> Path:
    """'demo_repo.splits:make_split' -> <target>/demo_repo/splits.py"""
    module_part = split_function.split(":")[0]          # e.g. demo_repo.splits
    rel = Path(module_part.replace(".", "/") + ".py")   # demo_repo/splits.py
    return target / rel


def _identity_columns(target: Path, cfg: dict) -> list[str]:
    """Identifier columns in the metadata CSV header: row_id, group_key and *_id columns."""
    tcfg = cfg.get("target", {})
    meta = tcfg.get("metadata") or cfg.get("metadata")
    if not meta:
        return []
    try:
        with open(target / meta, encoding="utf-8-sig", errors="replace") as f:
            first_line = f.readline()
    except OSError:
        return []
    header = [c.strip().strip('"').strip("'") for c in first_line.split(",") if c.strip()]
    keys = {tcfg.get("row_id"), tcfg.get("group_key")}
    return [c for c in header if c in keys or c.endswith("_id")]


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _column_of(expr: ast.expr) -> str:
    """df["label"] -> "label"; anything else -> its source text (short)."""
    if isinstance(expr, ast.Subscript) and isinstance(expr.slice, ast.Constant):
        return str(expr.slice.value)
    return ast.unparse(expr)[:60]


class _SplitCallVisitor(ast.NodeVisitor):
    """Collect the splitter calls made inside the configured split function's body."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.group_aware = False
        self.stratify_col: str | None = None

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _call_name(node)
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        if name in _GROUP_AWARE_CLASSES or "groups" in kwargs:
            self.group_aware = True
        if name in _SPLITTERS or (name == "split" and isinstance(node.func, ast.Attribute)):
            entry: dict = {"line": node.lineno, "call": name}
            if "groups" in kwargs:
                entry["groups"] = _column_of(kwargs["groups"])
            if "stratify" in kwargs:
                entry["stratify"] = _column_of(kwargs["stratify"])
                self.stratify_col = entry["stratify"]
            self.calls.append(entry)
        self.generic_visit(node)


def _find_function(tree: ast.Module, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def run(target: Path) -> dict:
    cfg = _load_config(target)
    split_function: str = (
        cfg.get("target", {}).get("split_function")
        or cfg.get("split_function", "")
    )
    group_key: str = (
        cfg.get("target", {}).get("group_key")
        or cfg.get("group_key", "")
    )

    if not split_function:
        return {"error": "split_function not configured in invariant.toml"}

    func_name = split_function.split(":")[-1] if ":" in split_function else split_function
    module_path = _resolve_split_module(target, split_function)

    try:
        source = module_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return {"error": f"cannot read split module: {exc}"}

    try:
        tree = ast.parse(source, filename=str(module_path))
    except SyntaxError as exc:
        return {"error": f"syntax error in split module: {exc}"}

    func_node = _find_function(tree, func_name)
    if func_node is None:
        return {"error": f"split function {func_name!r} not found in {module_path.name}"}
    visitor = _SplitCallVisitor()
    visitor.visit(func_node)

    calls = visitor.calls[:10]
    truncated = len(visitor.calls) > 10

    identity_cols = _identity_columns(target, cfg)[:10]

    risk_indicators: list[str] = []
    if group_key and group_key in identity_cols and not visitor.group_aware:
        risk_indicators.append("row_level_split_with_group_key_in_metadata")
    if not visitor.calls:
        risk_indicators.append("no_recognized_splitter_call")

    result: dict = {
        "file": module_path.relative_to(target).as_posix(),
        "split_function": split_function,
        "group_key": group_key,
        "function_line": func_node.lineno,
        "calls": calls,
        "group_aware": visitor.group_aware,
        "stratify_col": visitor.stratify_col,
        "identity_columns": identity_cols,
        "risk_indicators": risk_indicators,
    }
    if truncated:
        result["truncated"] = True
    return result