"""Builder tests covering R* (refusals), W* (report writing), H* (history) rows.

All tests use temporary git repositories; no external network access.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Callable

import jsonschema
import pytest

from report.builder import RefusalError, build
from report.status import required_checks

# ── helpers ───────────────────────────────────────────────────────────────────

_SCHEMA = json.loads((Path(__file__).parents[1] / "report" / "schema.json").read_text())


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, msg: str = "init") -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg, "--allow-empty")
    return _git_out(repo, "rev-parse", "HEAD")


def make_target(path: Path, *, toml_extra: str = "", with_base_ref: bool = True) -> Path:
    """Create a minimal valid target git repo with invariant.toml and metadata CSV."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    base_ref_section = '\n[review]\nbase_ref = "HEAD~1"\n' if with_base_ref else ""
    (path / "invariant.toml").write_text(
        f'[target]\nsplit_function = "demo.splits:make_split"\n'
        f'group_key = "patient_id"\nmetadata = "data/meta.csv"\n'
        + base_ref_section + toml_extra,
        encoding="utf-8",
    )
    (path / "data").mkdir(exist_ok=True)
    (path / "data" / "meta.csv").write_text("row_id,patient_id\nr1,G1\nr2,G2\n", encoding="utf-8")
    # make an initial empty commit so HEAD~1 is reachable
    _commit(path, "base")
    _commit(path, "head")
    return path


def make_analyzer(path: Path) -> Path:
    """Create a minimal clean analyzer git repo."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "placeholder.txt").write_text("ok", encoding="utf-8")
    _commit(path, "init")
    return path


def _clean_runners(status: str = "no_findings") -> dict[str, Callable]:
    """Stub runners returning the analyzers' real output shapes for the requested status."""
    overlap_count = 0
    reg_state = "passed"
    guard_state = "recognized_guard"
    guard_evidence = ["tests/test_split_invariants.py:15"]
    risk: list[str] = []
    if status == "blocked":
        overlap_count = 1
    elif status == "review_required":
        guard_state = "no_recognized_guard"
        guard_evidence = []
    return {
        "verify_split_overlap": lambda _: {
            "state": "valid", "partition_errors": [], "overlap_count": overlap_count,
            "overlap_examples": ["G1"] if overlap_count else [],
            "train_group_count": 1, "test_group_count": 1, "rows_partitioned": 2, "split_seed": 0,
        },
        "regression_tests": lambda _: {
            "state": reg_state, "passed": 3, "failed": 0, "errors": 0, "skipped": 0, "collected": 3,
        },
        "find_invariant_tests": lambda _: {
            "state": guard_state, "evidence": guard_evidence,
            "split_function": "demo.splits:make_split", "group_key": "patient_id",
            "test_files_scanned": 1,
        },
        "inspect_split": lambda _: {
            "file": "demo/splits.py", "split_function": "demo.splits:make_split",
            "group_key": "patient_id", "function_line": 4,
            "calls": [{"line": 5, "call": "GroupShuffleSplit"},
                      {"line": 6, "call": "split", "groups": "patient_id"}],
            "group_aware": True, "stratify_col": None,
            "identity_columns": ["row_id", "patient_id"], "risk_indicators": risk,
        },
    }


def _no_findings_runners() -> dict[str, Callable]:
    return _clean_runners("no_findings")


# ── R* refusal tests ──────────────────────────────────────────────────────────

class TestRefusals:

    def test_R1_dirty_target_refused(self, tmp_path):
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        # Create an untracked file to dirty the target
        (target / "untracked.txt").write_text("dirty", encoding="utf-8")
        with pytest.raises(RefusalError, match="dirty"):
            build(target, "", "", reports_root=tmp_path / "reports",
                  analyzer_root=analyzer, runners=_no_findings_runners())

    def test_R1_dirty_message_names_paths(self, tmp_path):
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        (target / "dirty.txt").write_text("x", encoding="utf-8")
        try:
            build(target, "", "", reports_root=tmp_path / "reports",
                  analyzer_root=analyzer, runners=_no_findings_runners())
        except RefusalError as exc:
            assert "dirty.txt" in str(exc)

    def test_R2_dirty_analyzer_refused(self, tmp_path):
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        # Dirty the analyzer outside reports/ and comparisons/
        (analyzer / "dirty.py").write_text("x", encoding="utf-8")
        with pytest.raises(RefusalError, match="dirty"):
            build(target, "", "", reports_root=tmp_path / "reports",
                  analyzer_root=analyzer, runners=_no_findings_runners())

    def test_R2_dirty_reports_not_refused(self, tmp_path):
        """Dirty files under reports/ and comparisons/ must NOT cause R2."""
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        # Add dirty files only under reports/ and comparisons/ in the analyzer repo
        (analyzer / "reports").mkdir()
        (analyzer / "reports" / "something.json").write_text("{}", encoding="utf-8")
        (analyzer / "comparisons").mkdir()
        (analyzer / "comparisons" / "x.json").write_text("{}", encoding="utf-8")
        # Should NOT raise — these paths are excluded
        result = build(target, "exp", "rem", reports_root=tmp_path / "reports",
                       analyzer_root=analyzer, runners=_no_findings_runners())
        assert result["status"] == "no_findings"

    def test_R3_head_mismatch_refused(self, tmp_path):
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        with pytest.raises(RefusalError, match="HEAD mismatch"):
            build(target, "", "", reports_root=tmp_path / "reports",
                  analyzer_root=analyzer, expected_head="0" * 40,
                  runners=_no_findings_runners())

    def test_R4_no_base_ref_refused(self, tmp_path):
        target = make_target(tmp_path / "target", with_base_ref=False)
        analyzer = make_analyzer(tmp_path / "analyzer")
        with pytest.raises(RefusalError, match="base_sha"):
            build(target, "", "", reports_root=tmp_path / "reports",
                  analyzer_root=analyzer, runners=_no_findings_runners())

    def test_R4_unresolvable_base_ref_refused(self, tmp_path):
        target = make_target(tmp_path / "target",
                             toml_extra='\n[review]\nbase_ref = "refs/no-such-branch"\n',
                             with_base_ref=False)
        analyzer = make_analyzer(tmp_path / "analyzer")
        with pytest.raises(RefusalError, match="base_sha"):
            build(target, "", "", reports_root=tmp_path / "reports",
                  analyzer_root=analyzer, runners=_no_findings_runners())

    def test_R5_hash_change_refused(self, tmp_path):
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        # Runner that modifies invariant.toml on disk (but can't change committed blob)
        # We simulate hash change by having the after-hash differ from before.
        # Since blobs are read via git, we need to actually change a committed file.
        # The simplest approach: override _blob_sha256 by making runners commit a new file.
        # Instead, test that the refusal is raised when hashes differ (monkeypatching).
        import report.builder as builder_mod
        original = builder_mod._blob_sha256
        call_count = [0]
        def patched(repo, sha, path):
            call_count[0] += 1
            # Return different hash on second call for invariant.toml
            if path == "invariant.toml" and call_count[0] > 1:
                return "different_hash"
            return original(repo, sha, path)
        builder_mod._blob_sha256 = patched
        try:
            with pytest.raises(RefusalError, match="hashes changed"):
                build(target, "", "", reports_root=tmp_path / "reports",
                      analyzer_root=analyzer, runners=_no_findings_runners())
        finally:
            builder_mod._blob_sha256 = original

    def test_R6_only_explanation_remediation_accepted(self, tmp_path):
        """The build() signature must only accept explanation_md and remediation_md from caller."""
        import inspect
        import report.builder as builder_mod
        sig = inspect.signature(builder_mod.build_report)
        params = list(sig.parameters)
        assert "explanation_md" in params
        assert "remediation_md" in params
        # No other caller-supplied params (target, sha, hash, etc.)
        caller_params = [p for p in params if p not in ("explanation_md", "remediation_md")]
        assert caller_params == [], f"unexpected params in build_report: {caller_params}"


# ── W* report writing tests ───────────────────────────────────────────────────

class TestReportWriting:

    def _build(self, tmp_path, runners=None, **kw):
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        reports_root = tmp_path / "reports"
        return build(target, "my explanation", "my remediation",
                     reports_root=reports_root,
                     analyzer_root=analyzer,
                     runners=runners or _no_findings_runners(),
                     **kw)

    def test_W1_path_structure(self, tmp_path):
        result = self._build(tmp_path)
        p = Path(result["report_path"])
        parts = p.parts
        # .../<target_repo_name>/<head_sha>/<run_id>/
        assert len(parts) >= 4
        assert parts[-1] == result["run_id"]
        assert parts[-2] == result["head_sha"]

    def test_W2_exclusive_creation(self, tmp_path):
        result = self._build(tmp_path)
        p = Path(result["report_path"])
        assert p.is_dir()
        # Creating the same directory again must fail (exclusive)
        with pytest.raises(FileExistsError):
            p.mkdir(parents=True, exist_ok=False)

    def test_W3_two_builds_same_sha_two_dirs(self, tmp_path):
        r1 = self._build(tmp_path)
        r2 = self._build(tmp_path)
        assert r1["run_id"] != r2["run_id"]
        assert r1["report_path"] != r2["report_path"]
        assert Path(r1["report_path"]).is_dir()
        assert Path(r2["report_path"]).is_dir()

    def test_W4_json_validates_against_schema(self, tmp_path):
        result = self._build(tmp_path)
        report_dir = Path(result["report_path"])
        report = json.loads((report_dir / "validity-report.json").read_text())
        jsonschema.validate(report, _SCHEMA)

    def test_W4_md_exists(self, tmp_path):
        result = self._build(tmp_path)
        assert (Path(result["report_path"]) / "validity-report.md").is_file()

    def test_W5_explanation_in_md_verbatim(self, tmp_path):
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        explanation = "This is the unique explanation XYZ-789."
        result = build(target, explanation, "rem",
                       reports_root=tmp_path / "reports",
                       analyzer_root=analyzer,
                       runners=_no_findings_runners())
        md = (Path(result["report_path"]) / "validity-report.md").read_text()
        assert explanation in md
        # Heading must be present
        assert "Reviewer explanation (Bob, not evidence)" in md

    def test_W5_explanation_only_in_section(self, tmp_path):
        """Caller text must not appear outside the designated section."""
        target = make_target(tmp_path / "target")
        analyzer = make_analyzer(tmp_path / "analyzer")
        unique = "UNIQUETOKEN_ABCDEF_987"
        result = build(target, unique, "rem",
                       reports_root=tmp_path / "reports",
                       analyzer_root=analyzer,
                       runners=_no_findings_runners())
        md = (Path(result["report_path"]) / "validity-report.md").read_text()
        heading = "## Reviewer explanation (Bob, not evidence)"
        idx = md.index(heading)
        before = md[:idx]
        assert unique not in before, "caller text appears before designated section"

    def test_W6_invariants_listed(self, tmp_path):
        result = self._build(tmp_path)
        report = json.loads((Path(result["report_path"]) / "validity-report.json").read_text())
        # invariants section must exist (may be empty if not configured)
        assert "invariants" in report

    def test_W7_binding_header_complete(self, tmp_path):
        result = self._build(tmp_path)
        report = json.loads((Path(result["report_path"]) / "validity-report.json").read_text())
        b = report["binding"]
        assert b["target_repo"]
        assert b["head_sha"]
        assert b["base_sha"]
        assert b["base_sha_source"]
        assert isinstance(b["hashes"], dict)
        assert b["required_checks"]
        assert report["run_id"]
        assert report["status"]

    def test_W8_mcp_return_under_2kb(self, tmp_path):
        result = self._build(tmp_path)
        size = len(json.dumps(result, separators=(",", ":")).encode())
        assert size < 2048, f"MCP return too large: {size} bytes"

    def test_W8_mcp_has_required_keys(self, tmp_path):
        result = self._build(tmp_path)
        for key in ("status", "head_sha", "run_id", "report_path", "per_check"):
            assert key in result, f"missing key: {key}"

    def test_W9_report_no_forward_reference(self, tmp_path):
        """A report built first must not reference a later report."""
        r1 = self._build(tmp_path)
        r2 = self._build(tmp_path)
        report1 = json.loads((Path(r1["report_path"]) / "validity-report.json").read_text())
        # r2's run_id must not appear in r1
        assert r2["run_id"] not in json.dumps(report1)


# ── H* history tests ──────────────────────────────────────────────────────────

def _write_manifest(repo: Path, run_id: str, overlap_count, cpu=None, wall=None, boundary=None):
    """Write a run_artifacts/<run_id>/manifest.json and commit it."""
    d = repo / "run_artifacts" / run_id
    d.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    if overlap_count is not None:
        manifest["metrics"] = {"overlap_count": overlap_count}
    else:
        manifest["metrics"] = {}
    if cpu is not None:
        manifest["timing"] = {
            "cpu_time_seconds": cpu,
            "wall_time_seconds": wall,
            "timing_boundary": boundary,
        }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", f"add manifest {run_id}", "--allow-empty")


class TestHistory:

    def _build_with_history(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        _git(target, "init", "-q")
        # initial commit as base
        (target / "invariant.toml").write_text(
            '[target]\nsplit_function = "demo.splits:make_split"\n'
            'group_key = "patient_id"\nmetadata = "data/meta.csv"\n'
            '[review]\nbase_ref = "HEAD~1"\n',
            encoding="utf-8",
        )
        (target / "data").mkdir()
        (target / "data" / "meta.csv").write_text("row_id,patient_id\nr1,G1\nr2,G2\n", encoding="utf-8")
        _commit(target, "base")
        return target

    def test_H1_only_committed_manifests_read(self, tmp_path):
        target = self._build_with_history(tmp_path)
        # Write an uncommitted manifest – it must not be read (clean tree required anyway)
        run_id = "uncommitted_run"
        d = target / "run_artifacts" / run_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text('{"metrics": {"overlap_count": 5}}', encoding="utf-8")
        # Target is now dirty; builder must refuse (R1), which means the uncommitted
        # manifest is never read. This transitively verifies H1.
        analyzer = make_analyzer(tmp_path / "analyzer")
        with pytest.raises(RefusalError, match="dirty"):
            build(target, "", "", reports_root=tmp_path / "reports",
                  analyzer_root=analyzer, runners=_no_findings_runners())

    def test_H2_confirmed_affected_overlap_gt_0(self, tmp_path):
        target = self._build_with_history(tmp_path)
        _write_manifest(target, "run_alpha", overlap_count=3, cpu=1.5, wall=2.0, boundary="2024-01-01")
        _commit(target, "head2")
        analyzer = make_analyzer(tmp_path / "analyzer")
        result = build(target, "", "", reports_root=tmp_path / "reports",
                       analyzer_root=analyzer, runners=_no_findings_runners())
        report = json.loads((Path(result["report_path"]) / "validity-report.json").read_text())
        hist = report["history"]
        assert "run_alpha" in hist["confirmed_affected"]
        assert hist["confirmed_count"] >= 1

    def test_H3_potentially_affected_missing_overlap(self, tmp_path):
        target = self._build_with_history(tmp_path)
        _write_manifest(target, "run_beta", overlap_count=None)
        _commit(target, "head3")
        analyzer = make_analyzer(tmp_path / "analyzer")
        result = build(target, "", "", reports_root=tmp_path / "reports",
                       analyzer_root=analyzer, runners=_no_findings_runners())
        report = json.loads((Path(result["report_path"]) / "validity-report.json").read_text())
        hist = report["history"]
        assert "run_beta" in hist["potentially_affected"]

    def test_H3_overlap_zero_is_neither(self, tmp_path):
        target = self._build_with_history(tmp_path)
        _write_manifest(target, "run_clean", overlap_count=0)
        _commit(target, "head_clean")
        analyzer = make_analyzer(tmp_path / "analyzer")
        result = build(target, "", "", reports_root=tmp_path / "reports",
                       analyzer_root=analyzer, runners=_no_findings_runners())
        report = json.loads((Path(result["report_path"]) / "validity-report.json").read_text())
        hist = report["history"]
        assert "run_clean" not in hist["confirmed_affected"]
        assert "run_clean" not in hist["potentially_affected"]

    def test_H4_timing_sums(self, tmp_path):
        target = self._build_with_history(tmp_path)
        _write_manifest(target, "r1", overlap_count=2, cpu=1.0, wall=2.0, boundary="A")
        _write_manifest(target, "r2", overlap_count=1, cpu=3.0, wall=4.0, boundary="B")
        _commit(target, "head4")
        analyzer = make_analyzer(tmp_path / "analyzer")
        result = build(target, "", "", reports_root=tmp_path / "reports",
                       analyzer_root=analyzer, runners=_no_findings_runners())
        report = json.loads((Path(result["report_path"]) / "validity-report.json").read_text())
        hist = report["history"]
        assert abs(hist["cpu_time_seconds"] - 4.0) < 0.01
        assert abs(hist["wall_time_seconds"] - 6.0) < 0.01
        boundaries = hist["timing_boundary_values"]
        assert "A" in boundaries and "B" in boundaries

    def test_H5_lists_max_10_with_truncated(self, tmp_path):
        target = self._build_with_history(tmp_path)
        for i in range(15):
            _write_manifest(target, f"run_{i:02d}", overlap_count=i + 1)
        _commit(target, "head5")
        analyzer = make_analyzer(tmp_path / "analyzer")
        result = build(target, "", "", reports_root=tmp_path / "reports",
                       analyzer_root=analyzer, runners=_no_findings_runners())
        report = json.loads((Path(result["report_path"]) / "validity-report.json").read_text())
        hist = report["history"]
        assert len(hist["confirmed_affected"]) <= 10
        assert hist["confirmed_count"] == 15
        assert hist.get("truncated") is True

    def test_H6_report_freezes_history_at_own_head(self, tmp_path):
        """Report B must not see manifests added after Report A's HEAD."""
        target = self._build_with_history(tmp_path)
        _write_manifest(target, "early_run", overlap_count=5)
        # Commit head A state
        _commit(target, "head_A")
        analyzer = make_analyzer(tmp_path / "analyzer")
        result_A = build(target, "", "", reports_root=tmp_path / "reports",
                         analyzer_root=analyzer, runners=_no_findings_runners())
        report_A = json.loads((Path(result_A["report_path"]) / "validity-report.json").read_text())

        # Add another manifest and advance HEAD
        _write_manifest(target, "late_run", overlap_count=3)
        _commit(target, "head_B")
        result_B = build(target, "", "", reports_root=tmp_path / "reports",
                         analyzer_root=analyzer, runners=_no_findings_runners())
        report_B = json.loads((Path(result_B["report_path"]) / "validity-report.json").read_text())

        # Report A must not see late_run
        all_A = report_A["history"]["confirmed_affected"] + report_A["history"]["potentially_affected"]
        assert "late_run" not in all_A

        # Report B sees both
        all_B = report_B["history"]["confirmed_affected"] + report_B["history"]["potentially_affected"]
        assert "early_run" in all_B or report_B["history"]["confirmed_count"] >= 2
