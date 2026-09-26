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
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

SERVER_VERSION = "0.1.0"
ANALYZER_ROOT = Path(__file__).resolve().parents[1]  # the invariant repository


class BindingError(RuntimeError):
    pass


SUBPROCESS_TIMEOUT_S = 30
LOG_PATH = Path(os.environ.get("INVARIANT_MCP_LOG", Path(tempfile.gettempdir()) / "invariant-mcp.log"))


def log(msg: str) -> None:
    """Diagnostics go to a file outside both repositories; never to stdout (the MCP pipe)."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} pid={os.getpid()} {msg}\n")
    except OSError:
        pass


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = SUBPROCESS_TIMEOUT_S) -> str:
    """Every subprocess goes through here: no inherited stdin, no console window, no prompts."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    start = time.monotonic()
    log(f"run start: {cmd[:4]}")
    try:
        out = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=timeout, creationflags=flags, check=True).stdout
        log(f"run ok {time.monotonic() - start:.2f}s")
        return out
    except Exception as exc:
        log(f"run failed {time.monotonic() - start:.2f}s: {type(exc).__name__}")
        raise


def _git(repo: Path, *args: str) -> str:
    return run_cmd(["git", "-C", str(repo), *args]).strip()


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
        log("hello called")
        payload = hello_payload(target)
        log("hello returning")
        return payload

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
        log(f"binding failed: {exc}")
        print(f"invariant: binding failed: {exc}", file=sys.stderr)
        sys.exit(2)
    if args.self_test:
        print(json.dumps(hello_payload(target), indent=2))
        return
    log(f"server start: python={platform.python_version()} target={target} log={LOG_PATH}")
    build_server(target).run()  # stdio transport


if __name__ == "__main__":
    main()