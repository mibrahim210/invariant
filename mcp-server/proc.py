"""The only place Invariant starts subprocesses or writes diagnostics.

Under the stdio transport the server's stdin/stdout are the MCP pipe, so every child
process gets stdin=DEVNULL, no console window (Windows), no git prompts, a timeout,
and an environment without the server's own VIRTUAL_ENV (so `uv run --directory <target>`
uses the target's environment). Diagnostics go to a log file, never to stdout.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_TIMEOUT_S = 30
LOG_PATH = Path(os.environ.get("INVARIANT_MCP_LOG", Path(tempfile.gettempdir()) / "invariant-mcp.log"))


def log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} pid={os.getpid()} {msg}\n")
    except OSError:
        pass


def _env() -> dict:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    env.pop("VIRTUAL_ENV", None)
    return env


def run_proc(cmd: list[str], cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT_S) -> subprocess.CompletedProcess:
    """Run a command and return the CompletedProcess without raising on a non-zero exit.
    Raises subprocess.TimeoutExpired or FileNotFoundError; callers map them to results."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    start = time.monotonic()
    log(f"run start: {cmd[:4]}")
    try:
        result = subprocess.run(cmd, cwd=cwd, env=_env(), text=True, encoding="utf-8", errors="replace",
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, creationflags=flags)
        log(f"run exit {result.returncode} {time.monotonic() - start:.2f}s")
        return result
    except Exception as exc:
        log(f"run failed {time.monotonic() - start:.2f}s: {type(exc).__name__}")
        raise


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT_S) -> str:
    """Run a command that must succeed; return stdout. Raises CalledProcessError on failure."""
    result = run_proc(cmd, cwd=cwd, timeout=timeout)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result.stdout