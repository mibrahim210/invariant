"""Static analyser: detect invariant guard tests in the target's test suite."""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path


def _load_config(target: Path) -> dict:
    with open(target / "invariant.toml", "rb") as f:
        return tomllib.load(f)


def _split_func_name(split_function: str) -> str:
    return split_function.split(":")[-1] if ":" in split_function else split_function


def _get_group_key(cfg: dict) -> str:
    return (
        cfg.get("target", {}).get("group_key")
        or cfg.get("group_key", "")
    )


def _get_split_function(cfg: dict) -> str:
    return (
        cfg.get("target", {}).get("split_function")
        or cfg.get("split_function", "")
    )


class _GuardDetector(ast.NodeVisitor):
    """Decide whether a function body contains a recognised guard.

    A recognised guard must:
    1. Call the configured split function.
    2. Assert an *empty intersection* (or disjointness) of sets built from the
       *group_key column* of both outputs – not just row IDs / indices.
       The sets may be built inline or by a same-file helper function.
    """

    def __init__(self, split_func: str, group_key: str, helpers: set[str] | None = None) -> None:
        self.split_func = split_func
        self.group_key = group_key
        self.calls_split = False
        self.has_group_disjoint_assert = False
        # names assigned from split function return values
        self._split_result_names: set[str] = set()
        # same-file helper functions that return a group-key set intersection
        self.helpers: set[str] = helpers or set()
        # names bound to a group-key set intersection (directly or via a helper)
        self._intersection_names: set[str] = set()

    # ── detect split call ────────────────────────────────────────────────────
    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        # overlap = helper(...)  or  overlap = set(df.loc[..., key]) & set(...)
        if self._is_intersection_value(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self._intersection_names.add(t.id)
        if isinstance(node.value, ast.Call):
            if self._is_split_call(node.value):
                self.calls_split = True
                # unpack: train, test = split_fn(...)
                for t in node.targets:
                    if isinstance(t, ast.Tuple):
                        for elt in t.elts:
                            if isinstance(elt, ast.Name):
                                self._split_result_names.add(elt.id)
                    elif isinstance(t, ast.Name):
                        self._split_result_names.add(t.id)
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:  # noqa: N802
        # detect: split_fn(...)  (bare call, result unused)
        if isinstance(node.value, ast.Call) and self._is_split_call(node.value):
            self.calls_split = True
        self.generic_visit(node)

    # ── detect assert ────────────────────────────────────────────────────────
    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        if self._assert_contains_group_disjoint(node.test):
            self.has_group_disjoint_assert = True
        self.generic_visit(node)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _is_split_call(self, node: ast.Call) -> bool:
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None
        )
        return name == self.split_func

    def _node_references_group_key(self, node: ast.expr) -> bool:
        """True if *node* references self.group_key as a subscript key anywhere."""
        if not self.group_key:
            return False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and str(sub.value) == self.group_key:
                return True
        return False

    def _is_intersection_value(self, node: ast.expr) -> bool:
        """A group-key set intersection: inline expression or a call to a same-file helper."""
        if self._is_group_set_intersection(node):
            return True
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in self.helpers)

    def _is_intersection_ref(self, node: ast.expr) -> bool:
        """Intersection value, a name bound to one, or len() of either."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len" and node.args:
            node = node.args[0]
        if isinstance(node, ast.Name) and node.id in self._intersection_names:
            return True
        return self._is_intersection_value(node)

    def _assert_contains_group_disjoint(self, test: ast.expr) -> bool:
        """True when the assert establishes an empty group-key intersection or disjointness."""
        for node in ast.walk(test):
            # not overlap / not (set_a & set_b) / not helper(...)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                if self._is_intersection_ref(node.operand):
                    return True
            # overlap == set() / len(overlap) == 0 / set_a & set_b == set()
            if isinstance(node, ast.Compare) and self._is_intersection_ref(node.left):
                return True
            # set_a.isdisjoint(set_b) with a group-key set on either side
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "isdisjoint" and node.args):
                if self._is_group_set_expr(node.func.value) or self._is_group_set_expr(node.args[0]):
                    return True
        return False

    def _is_group_set_intersection(self, node: ast.expr) -> bool:
        """set_a & set_b where at least one side references group_key."""
        # Could be wrapped in len()
        inner = node
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "len"
            and inner.args
        ):
            inner = inner.args[0]
        if isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.BitAnd):
            return (
                self._is_group_set_expr(inner.left)
                or self._is_group_set_expr(inner.right)
            )
        return False

    def _is_group_set_expr(self, node: ast.expr) -> bool:
        """set(df.loc[idx, group_key]) or {df.loc[idx, group_key]} or similar."""
        # set(...) call
        if isinstance(node, ast.Call):
            func = node.func
            is_set_call = (isinstance(func, ast.Name) and func.id == "set") or (
                isinstance(func, ast.Attribute) and func.attr == "unique"
            )
            if is_set_call and self._node_references_group_key(node):
                return True
        # set comprehension / generator with group key
        if isinstance(node, (ast.SetComp, ast.GeneratorExp)):
            if self._node_references_group_key(node):
                return True
        return False


def _rel(path: Path, target: Path) -> str:
    try:
        return path.relative_to(target).as_posix()
    except ValueError:
        return path.as_posix()


def _find_helpers(tree: ast.Module, split_func: str, group_key: str) -> set[str]:
    """Module-level non-test functions that return a group-key set intersection."""
    probe = _GuardDetector(split_func, group_key)
    helpers: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("test"):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and sub.value is not None \
                        and probe._is_group_set_intersection(sub.value):
                    helpers.add(node.name)
    return helpers


def _analyse_file(
    path: Path, target: Path, split_func: str, group_key: str
) -> tuple[str, list[str]]:
    """Return (state, evidence_list) for a single test file."""
    rel = _rel(path, target)
    try:
        # utf-8-sig: files saved with a BOM (common on Windows) must still parse
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return "unknown", [f"{rel}:{exc.lineno or 0}"]
    except OSError:
        return "unknown", [rel]

    helpers = _find_helpers(tree, split_func, group_key)
    evidence: list[str] = []
    recognized = False

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        detector = _GuardDetector(split_func, group_key, helpers)
        detector.visit(node)
        if detector.calls_split and detector.has_group_disjoint_assert:
            recognized = True
            evidence.append(f"{rel}:{node.lineno}")

    return ("recognized_guard" if recognized else "no_recognized_guard"), evidence


def run(target: Path) -> dict:
    cfg = _load_config(target)
    split_function = _get_split_function(cfg)
    group_key = _get_group_key(cfg)

    if not split_function:
        return {"error": "split_function not configured in invariant.toml"}

    func_name = _split_func_name(split_function)

    test_dir = target / "tests"
    if not test_dir.is_dir():
        return {
            "state": "no_recognized_guard",
            "evidence": [],
            "note": "no tests/ directory found",
        }

    all_evidence: list[str] = []
    state = "no_recognized_guard"
    unknown_files: list[str] = []
    total = 0

    for py_file in sorted(test_dir.rglob("*.py")):
        total += 1
        file_state, file_evidence = _analyse_file(py_file, target, func_name, group_key)
        if file_state == "recognized_guard":
            state = "recognized_guard"
            all_evidence.extend(file_evidence)
        elif file_state == "unknown":
            unknown_files.extend(file_evidence)

    if state != "recognized_guard" and unknown_files:
        state = "unknown"
        all_evidence = unknown_files

    evidence = all_evidence[:10]
    result: dict = {
        "state": state,
        "evidence": evidence,
        "split_function": split_function,
        "group_key": group_key,
        "test_files_scanned": total,
    }
    if len(all_evidence) > 10:
        result["truncated"] = True
    return result