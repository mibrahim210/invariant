"""Execution analyser: run the target's required regression tests via pytest."""
from __future__ import annotations

import subprocess
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from proc import log, run_proc

_PYTEST_TIMEOUT = 300


def _load_config(target: Path) -> dict:
    with open(target / "invariant.toml", "rb") as f:
        return tomllib.load(f)


def _parse_junit(junit_path: Path) -> dict:
    """Parse a JUnit XML file and return counts.

    Returns dict with keys: passed, failed, errors, skipped, collected.
    """
    try:
        tree = ET.parse(junit_path)
    except (ET.ParseError, OSError) as exc:
        return {"_parse_error": str(exc)}

    root = tree.getroot()
    # JUnit XML root may be <testsuite> or <testsuites>
    if root.tag == "testsuites":
        suites = list(root.iter("testsuite"))
    else:
        suites = [root]

    total = 0
    failures = 0
    errors = 0
    skipped = 0

    for suite in suites:
        total += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))

    passed = total - failures - errors - skipped
    return {
        "passed": max(passed, 0),
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "collected": total,
    }


def run(target: Path) -> dict:
    try:
        cfg = _load_config(target)
    except Exception as exc:
        return {"state": "collection_error", "error": f"cannot read invariant.toml: {exc}"}

    checks = cfg.get("checks", {})
    regression_tests = checks.get("regression_tests", [])

    if not regression_tests:
        return {
            "state": "no_tests",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }

    # Validate that all configured test paths exist before launching pytest.
    missing = [t for t in regression_tests if not (target / t).exists()]
    if missing:
        return {
            "state": "collection_error",
            "error": f"configured test paths not found: {missing[:5]}",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }

    with tempfile.NamedTemporaryFile(
        suffix=".xml", delete=False, mode="w", encoding="utf-8"
    ) as tf:
        junit_path = Path(tf.name)

    try:
        cmd = [
            "uv", "run", "--locked", "--directory", str(target),
            "python", "-m", "pytest",
            "-q", "-p", "no:cacheprovider",
            f"--junitxml={junit_path}",
            *regression_tests,
        ]
        log(f"run_required_tests: launching pytest for {target}")
        result = run_proc(cmd, cwd=target, timeout=_PYTEST_TIMEOUT)
        exit_code = result.returncode
        log(f"run_required_tests: pytest exit {exit_code}")

    except subprocess.TimeoutExpired:
        log("run_required_tests: pytest timed out")
        return {
            "state": "crash",
            "error": "pytest timed out",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }
    except FileNotFoundError as exc:
        return {
            "state": "crash",
            "error": f"uv not found: {exc}",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }
    finally:
        # Keep junit_path for parsing; unlink after.
        pass

    # Exit code 5 = no tests collected.
    if exit_code == 5:
        try:
            junit_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "state": "no_tests",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }

    # Exit code 4 = collection error (usage/import error before any test ran).
    if exit_code == 4:
        try:
            junit_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "state": "collection_error",
            "error": "pytest reported a collection error (exit 4)",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }

    # Parse JUnit XML.
    if not junit_path.exists() or junit_path.stat().st_size == 0:
        return {
            "state": "collection_error",
            "error": "no junit xml file produced by pytest",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }

    counts = _parse_junit(junit_path)
    try:
        junit_path.unlink(missing_ok=True)
    except OSError:
        pass

    if "_parse_error" in counts:
        return {
            "state": "collection_error",
            "error": f"junit xml parse error: {counts['_parse_error']}",
            "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "collected": 0,
        }

    # Determine state from exit code and counts.
    # pytest exit codes: 0 all passed, 1 some tests failed, 2 interrupted (including
    # collection errors such as an import error), 3 internal error, 4 usage error.
    if exit_code == 0:
        state = "passed"
    elif exit_code == 1 or (exit_code == 2 and counts["failed"] > 0):
        state = "failed"
    elif exit_code == 2:
        state = "collection_error"
    else:
        state = "crash"

    return {
        "state": state,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
        "collected": counts["collected"],
    }
