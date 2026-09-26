"""Validity Report builder.

Entry point for Bob: build_report(explanation_md, remediation_md)
CLI:  python -m report.builder --target-repo PATH [--reports-root PATH]
                                [--expected-head SHA --expected-base SHA]

The builder:
- Reads invariant.toml from the bound target.
- Derives head_sha, base_sha, and hashes from committed blobs (never working-tree files).
- Refuses if the target or (relevant) analyzer tree is dirty.
- Runs the four checks via injectable runners.
- Derives status via report.status.
- Writes validity-report.json + validity-report.md under
  reports/<target_repo_name>/<head_sha>/<run_id>/
- Returns a compact MCP summary dict (< 2 KB).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import textwrap
import time
import tomllib
import uuid
from pathlib import Path
from typing import Any, Callable

import jsonschema

import analyzers.inspect_split as _inspect_split_mod
import analyzers.coverage as _coverage_mod
import analyzers.verify_overlap as _verify_overlap_mod
import analyzers.run_tests as _run_tests_mod
from proc import log, run_cmd
from report.status import derive_status, required_checks

# ── paths ─────────────────────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent          # mcp-server/report/
_ANALYZER_ROOT = _THIS_DIR.parents[1]               # invariant/
_SCHEMA_PATH = _THIS_DIR / "schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_DEFAULT_REPORTS_ROOT = _ANALYZER_ROOT / "reports"

SCHEMA_VERSION = "1.0"

# ── hashed input paths (relative to target root) ─────────────────────────────
_HASH_PATHS = [
    "invariant.toml",
    "configs/data_generation.json",
    "data/image_manifest.json",
]


# ── public exceptions ─────────────────────────────────────────────────────────

class RefusalError(RuntimeError):
    """Raised when the builder refuses to produce a report."""


# ── git helpers ───────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> str:
    return run_cmd(["git", "-C", str(repo), *args]).strip()


def _dirty_paths(repo: Path) -> list[str]:
    """Return untracked + modified paths (relative to repo root)."""
    out = _git(repo, "status", "--porcelain", "-uall")
    lines = [ln[3:].strip() for ln in out.splitlines() if ln.strip()]
    return lines


def _blob_sha256(repo: Path, head_sha: str, rel_path: str) -> str | None:
    """SHA-256 of the committed blob at head_sha:<rel_path>; None if absent."""
    try:
        content = run_cmd(["git", "-C", str(repo), "cat-file", "blob",
                           f"{head_sha}:{rel_path}"])
        return hashlib.sha256(content.encode("utf-8", errors="surrogateescape")).hexdigest()
    except Exception:
        return None


def _resolve_base(repo: Path, cfg: dict, expected_base: str | None) -> tuple[str | None, str]:
    """Return (base_sha, source). Source is 'invariant.toml', 'cli', or 'unresolvable'."""
    if expected_base:
        return expected_base, "cli"
    base_ref = cfg.get("review", {}).get("base_ref", "")
    if not base_ref:
        return None, "unresolvable"
    try:
        sha = _git(repo, "rev-parse", "--verify", base_ref)
        return sha, "invariant.toml"
    except Exception:
        return None, "unresolvable"


def _analyzer_dirty(analyzer_root: Path) -> list[str]:
    """Return dirty paths in the analyzer repo, excluding reports/ and comparisons/."""
    try:
        out = _git(analyzer_root, "status", "--porcelain", "-uall")
    except Exception:
        return []
    dirty = []
    for ln in out.splitlines():
        if not ln.strip():
            continue
        rel = ln[3:].strip()
        if rel.startswith("reports/") or rel.startswith("comparisons/"):
            continue
        dirty.append(rel)
    return dirty


# ── history ───────────────────────────────────────────────────────────────────

def _collect_history(repo: Path, head_sha: str) -> dict:
    """Read committed run_artifacts/<run_id>/manifest.json files at head_sha."""
    try:
        listing = run_cmd(["git", "-C", str(repo), "ls-tree", "-r", "--name-only",
                           head_sha, "--", "run_artifacts/"])
    except Exception:
        listing = ""

    manifest_paths = [
        p for p in listing.splitlines()
        if p.startswith("run_artifacts/") and p.endswith("/manifest.json")
        and p.count("/") == 2  # exactly run_artifacts/<run_id>/manifest.json
    ]

    confirmed: list[str] = []
    potentially: list[str] = []
    cpu_total: float = 0.0
    wall_total: float = 0.0
    missing_timing = 0
    boundary_values: list[Any] = []
    truncated = False

    for mp in manifest_paths:
        run_id = mp.split("/")[1]
        try:
            raw = run_cmd(["git", "-C", str(repo), "show", f"{head_sha}:{mp}"])
            manifest = json.loads(raw)
        except Exception:
            potentially.append(run_id)
            continue

        metrics = manifest.get("metrics") if isinstance(manifest, dict) else None
        overlap_count = metrics.get("overlap_count") if isinstance(metrics, dict) else None

        if isinstance(overlap_count, int) and overlap_count > 0:
            confirmed.append(run_id)
            # Timing
            timing = manifest.get("timing") if isinstance(manifest, dict) else None
            if isinstance(timing, dict):
                cpu = timing.get("cpu_time_seconds")
                wall = timing.get("wall_time_seconds")
                boundary = timing.get("timing_boundary")
                if cpu is not None and wall is not None:
                    cpu_total += float(cpu)
                    wall_total += float(wall)
                else:
                    missing_timing += 1
                if boundary not in boundary_values:
                    boundary_values.append(boundary)
            else:
                missing_timing += 1
        elif overlap_count == 0:
            pass  # neither confirmed nor potentially
        else:
            potentially.append(run_id)

    confirmed_count = len(confirmed)
    potentially_count = len(potentially)

    if len(confirmed) > 10:
        confirmed = confirmed[:10]
        truncated = True
    if len(potentially) > 10:
        potentially = potentially[:10]
        truncated = True

    result: dict = {
        "confirmed_affected": confirmed,
        "potentially_affected": potentially,
        "confirmed_count": confirmed_count,
        "potentially_count": potentially_count,
        "cpu_time_seconds": round(cpu_total, 3) if confirmed_count else None,
        "wall_time_seconds": round(wall_total, 3) if confirmed_count else None,
        "timing_boundary_values": boundary_values,
        "missing_timing_count": missing_timing,
    }
    if truncated:
        result["truncated"] = True
    return result


# ── check runners ─────────────────────────────────────────────────────────────

_DEFAULT_RUNNERS: dict[str, Callable[[Path], dict]] = {
    "inspect_split": lambda target: _inspect_split_mod.run(target),
    "verify_split_overlap": lambda target: _verify_overlap_mod.run(target),
    "find_invariant_tests": lambda target: _coverage_mod.run(target),
    "regression_tests": lambda target: _run_tests_mod.run(target),
}


# ── schema validation ─────────────────────────────────────────────────────────

def _validate_check_result(check_name: str, result: dict) -> bool:
    """Light structural check: must be a dict with known keys. Returns True if valid."""
    if not isinstance(result, dict):
        return False
    # Minimal: must have 'state' key (all our analyzers return one)
    if "error" in result:
        return True  # error dicts are valid schema-wise; status treats them as review_req
    return "state" in result


# ── Markdown rendering ────────────────────────────────────────────────────────

def _render_md(report: dict) -> str:
    b = report["binding"]
    lines = [
        "# Validity Report",
        "",
        "## Binding",
        "",
        f"- **Repository**: `{b['target_repo']}`",
        f"- **head_sha**: `{b['head_sha']}`",
        f"- **base_sha**: `{b['base_sha']}` (source: {b['base_sha_source']})",
        f"- **run_id**: `{report['run_id']}`",
        f"- **analyzer_commit**: `{b['analyzer_commit']}`",
        f"- **status**: **{report['status']}**",
        "",
        "### Input hashes",
        "",
    ]
    for path, h in b["hashes"].items():
        lines.append(f"- `{path}`: `{h}`")
    lines += [
        "",
        "## Checks",
        "",
    ]
    for check, info in report["checks"].items():
        lines.append(f"### {check}")
        lines.append(f"- contribution: **{info['contribution']}**")
        lines.append(f"- summary: {info['summary']}")
        lines.append("")

    lines += [
        "## Invariants",
        "",
    ]
    for name, info in report.get("invariants", {}).items():
        lines.append(f"- `{name}`: {info['status']}")
    lines += [
        "",
        "## History",
        "",
        f"- confirmed_affected runs: {report['history']['confirmed_count']}",
        f"- potentially_affected runs: {report['history']['potentially_count']}",
        "",
        "## Reviewer explanation (Bob, not evidence)",
        "",
        report["explanation_md"],
        "",
        "## Remediation",
        "",
        report["remediation_md"],
    ]
    return "\n".join(lines)


# ── invariants ────────────────────────────────────────────────────────────────

def _collect_invariants(cfg: dict, check_names: list[str]) -> dict:
    invariants_cfg = cfg.get("invariants", {})
    result: dict = {}
    for name, _info in invariants_cfg.items():
        result[name] = {"status": "checked" if name in check_names else "not_checked"}
    return result


# ── check summary ─────────────────────────────────────────────────────────────

def _check_summary(check_name: str, result: dict | None, contribution: str) -> str:
    if result is None:
        return "missing"
    if "error" in result:
        return f"error: {str(result['error'])[:80]}"
    state = result.get("state", "unknown")
    if check_name == "verify_split_overlap":
        oc = result.get("overlap_count")
        return f"state={state} overlap_count={oc}"
    if check_name == "regression_tests":
        return (f"state={state} passed={result.get('passed',0)} "
                f"failed={result.get('failed',0)} collected={result.get('collected',0)}")
    if check_name == "find_invariant_tests":
        return f"state={state}"
    if check_name == "inspect_split":
        ri = result.get("risk_indicators", [])
        return f"risk_indicators={ri}"
    return f"state={state}"


# ── core build function ───────────────────────────────────────────────────────

def build(
    target: Path,
    explanation_md: str,
    remediation_md: str,
    *,
    reports_root: Path | None = None,
    analyzer_root: Path | None = None,
    expected_head: str | None = None,
    expected_base: str | None = None,
    runners: dict[str, Callable[[Path], dict]] | None = None,
) -> dict:
    """Build a Validity Report. Returns compact MCP summary dict (< 2 KB).

    Raises RefusalError when a refusal condition is met (R1-R5).
    """
    if reports_root is None:
        reports_root = _DEFAULT_REPORTS_ROOT
    if analyzer_root is None:
        analyzer_root = _ANALYZER_ROOT
    if runners is None:
        runners = _DEFAULT_RUNNERS

    # ── R1: target dirty ──────────────────────────────────────────────────────
    dirty = _dirty_paths(target)
    if dirty:
        raise RefusalError(f"target working tree is dirty: {dirty[:10]}")

    # ── R2: analyzer dirty (outside reports/ and comparisons/) ────────────────
    analyzer_dirty = _analyzer_dirty(analyzer_root)
    if analyzer_dirty:
        raise RefusalError(f"analyzer checkout is dirty: {analyzer_dirty[:10]}")

    # ── read invariant.toml ───────────────────────────────────────────────────
    try:
        with open(target / "invariant.toml", "rb") as f:
            cfg = tomllib.load(f)
    except Exception as exc:
        raise RefusalError(f"cannot read invariant.toml: {exc}") from exc

    # ── head SHA ──────────────────────────────────────────────────────────────
    head_sha = _git(target, "rev-parse", "--verify", "HEAD")

    # ── R3: expected head mismatch ────────────────────────────────────────────
    if expected_head and head_sha != expected_head:
        raise RefusalError(
            f"HEAD mismatch: actual={head_sha} expected={expected_head}"
        )

    # ── base SHA ──────────────────────────────────────────────────────────────
    base_sha, base_sha_source = _resolve_base(target, cfg, expected_base)

    # ── R4: base unresolvable ─────────────────────────────────────────────────
    if base_sha is None:
        raise RefusalError(
            "base_sha could not be resolved: set [review] base_ref in invariant.toml "
            "or pass --expected-base"
        )

    # ── compute input hashes (committed blobs) ────────────────────────────────
    # Also include metadata path from toml if present.
    hash_paths = list(_HASH_PATHS)
    meta = cfg.get("target", {}).get("metadata") or cfg.get("metadata")
    if meta and meta not in hash_paths:
        hash_paths.append(meta)

    hashes_before: dict[str, str | None] = {
        p: _blob_sha256(target, head_sha, p) for p in hash_paths
    }

    # ── analyzer commit ───────────────────────────────────────────────────────
    try:
        analyzer_commit = _git(analyzer_root, "rev-parse", "--verify", "HEAD")
    except Exception:
        analyzer_commit = None

    # ── run checks ────────────────────────────────────────────────────────────
    check_results: dict[str, dict | None] = {}
    for check_name in required_checks():
        runner = runners.get(check_name)
        if runner is None:
            check_results[check_name] = None
            continue
        try:
            result = runner(target)
        except Exception as exc:
            log(f"builder: check {check_name} raised: {exc}")
            result = {"error": str(exc), "state": "error"}
        # S17: schema validation
        if not _validate_check_result(check_name, result):
            result = {"error": "schema validation failed", "state": "error"}
        check_results[check_name] = result

    # ── R5: re-hash after checks ──────────────────────────────────────────────
    hashes_after: dict[str, str | None] = {
        p: _blob_sha256(target, head_sha, p) for p in hash_paths
    }
    if hashes_before != hashes_after:
        raise RefusalError("input hashes changed during check execution; report refused")

    # ── derive status ─────────────────────────────────────────────────────────
    status, contributions = derive_status(check_results)

    # ── history ───────────────────────────────────────────────────────────────
    history = _collect_history(target, head_sha)

    # ── collect invariants ────────────────────────────────────────────────────
    invariants = _collect_invariants(cfg, list(check_results.keys()))

    # ── checks section ────────────────────────────────────────────────────────
    checks_section: dict = {}
    for check_name in required_checks():
        result = check_results.get(check_name)
        contrib = contributions.get(check_name, "none")
        checks_section[check_name] = {
            "contribution": contrib,
            "summary": _check_summary(check_name, result, contrib),
            "result": result,
        }

    # ── run_id and report dir ─────────────────────────────────────────────────
    run_id = uuid.uuid4().hex
    target_repo_name = target.name
    report_dir = reports_root / target_repo_name / head_sha / run_id

    # W2: exclusive creation
    report_dir.mkdir(parents=True, exist_ok=False)

    # ── assemble report ───────────────────────────────────────────────────────
    report: dict = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "binding": {
            "target_repo": target.as_posix(),
            "target_repo_name": target_repo_name,
            "head_sha": head_sha,
            "base_sha": base_sha,
            "base_sha_source": base_sha_source,
            "hashes": hashes_before,
            "analyzer_commit": analyzer_commit,
            "required_checks": required_checks(),
            "completed_checks": [k for k, v in check_results.items() if v is not None],
        },
        "checks": checks_section,
        "invariants": invariants,
        "history": history,
        "explanation_md": explanation_md,
        "remediation_md": remediation_md,
    }

    # ── validate report against schema ───────────────────────────────────────
    jsonschema.validate(report, _SCHEMA)

    # ── write files ───────────────────────────────────────────────────────────
    json_path = report_dir / "validity-report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_path = report_dir / "validity-report.md"
    md_path.write_text(_render_md(report), encoding="utf-8")

    # ── compact MCP return (W8: < 2 KB) ──────────────────────────────────────
    per_check_summaries = {
        name: info["summary"] for name, info in checks_section.items()
    }
    mcp_result: dict = {
        "status": status,
        "head_sha": head_sha,
        "run_id": run_id,
        "report_path": report_dir.as_posix(),
        "per_check": per_check_summaries,
    }
    return mcp_result


# ── MCP tool wrapper ──────────────────────────────────────────────────────────

# These are set once at server startup via bind().
_bound_target: Path | None = None
_bound_reports_root: Path | None = None
_bound_analyzer_root: Path | None = None


def bind(target: Path, reports_root: Path | None = None, analyzer_root: Path | None = None) -> None:
    """Called once at server startup to set the bound target."""
    global _bound_target, _bound_reports_root, _bound_analyzer_root
    _bound_target = target
    _bound_reports_root = reports_root
    _bound_analyzer_root = analyzer_root


def build_report(explanation_md: str, remediation_md: str) -> dict:
    """MCP tool entry point. Only explanation_md and remediation_md accepted (R6)."""
    if _bound_target is None:
        return {"error": "builder not bound to a target; call bind() first"}
    return build(
        _bound_target,
        explanation_md,
        remediation_md,
        reports_root=_bound_reports_root,
        analyzer_root=_bound_analyzer_root,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Validity Report for a target repository."
    )
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--reports-root", default=None)
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--expected-base", default=None)
    args = parser.parse_args()

    target = Path(args.target_repo).resolve()
    reports_root = Path(args.reports_root).resolve() if args.reports_root else None

    try:
        result = build(
            target,
            explanation_md="",
            remediation_md="",
            reports_root=reports_root,
            expected_head=args.expected_head,
            expected_base=args.expected_base,
        )
    except RefusalError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))
    status = result.get("status", "")
    if status == "no_findings":
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
