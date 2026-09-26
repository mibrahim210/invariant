"""Invariant MCP server (FastMCP, stdio).

    uv run --directory <invariant>/mcp-server python server.py --target-repo <ABSOLUTE_DEMO_REPO>
    uv run --directory <invariant>/mcp-server python server.py --target-repo <...> --self-test

The target is bound once at startup and validated before any tool is registered.
Tools never infer the target from the working directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

SERVER_VERSION = "0.1.0"
ANALYZER_ROOT = Path(__file__).resolve().parents[1]  # the invariant repository


class BindingError(RuntimeError):
    pass


SUBPROCESS_TIMEOUT_S = 30


def _git(repo: Path, *args: str) -> str:
    # stdin=DEVNULL is required: under the stdio transport the server's stdin is the MCP
    # pipe, and a child that inherits it can block forever (observed on Windows).
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True,
                                   stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=SUBPROCESS_TIMEOUT_S).strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind_target(raw: str) -> Path:
    """Resolve and validate the target repository. Raises BindingError."""
    path = Path(raw)
    if not path.is_absolute():
        raise BindingError(f"--target-repo must be absolute, got {raw!r}")
    path = path.resolve()
    if not path.is_dir():
        raise BindingError(f"target does not exist: {path}")
    try:
        top = Path(_git(path, "rev-parse", "--show-toplevel")).resolve()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise BindingError(f"target is not a git repository: {path}") from exc
    if top != path:
        raise BindingError(f"target must be the repository root; git top-level is {top}")
    if not (path / "invariant.toml").is_file():
        raise BindingError(f"target has no invariant.toml: {path}")
    return path


def repo_state(repo: Path) -> dict:
    try:
        return {"head_sha": _git(repo, "rev-parse", "--verify", "HEAD"),
                "clean": _git(repo, "status", "--porcelain") == ""}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {"head_sha": None, "clean": None}


def hello_payload(target: Path) -> dict:
    """Binding facts for the smoke test; compact and evidence-only."""
    target_state = repo_state(target)
    analyzer_state = repo_state(ANALYZER_ROOT)
    return {
        "server_version": SERVER_VERSION,
        "python": platform.python_version(),
        "target_repo": target.as_posix(),
        "target_head_sha": target_state["head_sha"],
        "target_clean": target_state["clean"],
        "invariant_toml_sha256": _sha256(target / "invariant.toml"),
        "analyzer_repo": ANALYZER_ROOT.as_posix(),
        "analyzer_head_sha": analyzer_state["head_sha"],
        "analyzer_clean": analyzer_state["clean"],
    }


def build_server(target: Path) -> FastMCP:
    mcp = FastMCP("invariant")

    @mcp.tool()
    def hello() -> dict:
        """Smoke test: report the bound target repository, its HEAD and cleanliness,
        and the analyzer checkout. Reads nothing else and changes nothing."""
        return hello_payload(target)

    # Tasks 2-4 register: inspect_split, verify_split_overlap, find_invariant_tests,
    # run_required_tests, build_report. Each receives `target` from this closure.
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--self-test", action="store_true",
                        help="validate the binding, print the hello payload and exit")
    args = parser.parse_args()
    try:
        target = bind_target(args.target_repo)
    except BindingError as exc:
        print(f"invariant: binding failed: {exc}", file=sys.stderr)
        sys.exit(2)
    if args.self_test:
        print(json.dumps(hello_payload(target), indent=2))
        return
    build_server(target).run()  # stdio transport


if __name__ == "__main__":
    main()