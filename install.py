"""Install Invariant's Bob configuration into a target repository.

    python install.py --target-repo ../invariant-demo-nsclc

Stdlib only; any Python 3.10+ works. It:
  1. resolves both repositories to absolute paths and checks the target is a git root
     with an invariant.toml;
  2. copies templates/bob/ (mode + skills) into <target>/.bob/, reporting changes;
  3. writes <target>/.bob/mcp.json with absolute uv, server and target paths
     (build_report is deliberately NOT auto-approved);
  4. refuses if .bob/mcp.json would be tracked by git (it holds machine-specific paths);
  5. starts the server once with --self-test and prints the binding it reports.
Both uv invocations use --locked, so installation never rewrites mcp-server/uv.lock.
Re-running refreshes the installation after template changes.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import subprocess
import sys
from pathlib import Path

INVARIANT_ROOT = Path(__file__).resolve().parent
SERVER_DIR = INVARIANT_ROOT / "mcp-server"
TEMPLATES = INVARIANT_ROOT / "templates" / "bob"
AUTO_APPROVED = ["hello", "inspect_split", "verify_split_overlap", "find_invariant_tests", "run_required_tests"]


def fail(msg: str) -> None:
    sys.exit(f"install: ERROR: {msg}")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def resolve_target(raw: str) -> Path:
    target = Path(raw).expanduser().resolve()
    if not target.is_dir():
        fail(f"target does not exist: {target}")
    top = git(target, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        fail(f"target is not a git repository: {target}")
    if Path(top.stdout.strip()).resolve() != target:
        fail(f"target must be the repository root; git top-level is {top.stdout.strip()}")
    if not (target / "invariant.toml").is_file():
        fail(f"target has no invariant.toml: {target}")
    if target == INVARIANT_ROOT or INVARIANT_ROOT in target.parents:
        fail("target must be a separate repository, not the invariant repository")
    return target


def copy_templates(target: Path) -> list[str]:
    report = []
    for src in sorted(p for p in TEMPLATES.rglob("*") if p.is_file()):
        rel = src.relative_to(TEMPLATES)
        dst = target / ".bob" / rel
        state = "unchanged" if dst.exists() and filecmp.cmp(src, dst, shallow=False) else (
            "updated" if dst.exists() else "added")
        if state != "unchanged":
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        report.append(f"  {state:9} .bob/{rel.as_posix()}")
    return report


def write_mcp_json(target: Path, uv: str) -> Path:
    path = target / ".bob" / "mcp.json"
    config = {"mcpServers": {}}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
            config.setdefault("mcpServers", {})
        except json.JSONDecodeError:
            fail(f"{path} exists but is not valid JSON; fix or remove it")
    config["mcpServers"]["invariant"] = {
        "command": uv,
        "args": ["run", "--locked", "--directory", str(SERVER_DIR), "python", "server.py",
                 "--target-repo", str(target)],
        "timeout": 600,
        "alwaysAllow": AUTO_APPROVED,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--uv", help="absolute path to uv (default: found on PATH)")
    args = parser.parse_args()

    target = resolve_target(args.target_repo)
    uv = args.uv or shutil.which("uv")
    if not uv:
        fail("uv not found on PATH; pass --uv <absolute path>")
    uv = str(Path(uv).resolve())
    if not (SERVER_DIR / "server.py").is_file():
        fail(f"server not found: {SERVER_DIR / 'server.py'}")

    ignored = git(target, "check-ignore", "-q", ".bob/mcp.json").returncode == 0
    if not ignored:
        fail("add '.bob/mcp.json' to the target's .gitignore and commit it first; "
             "the file contains machine-specific absolute paths")

    print(f"invariant: {INVARIANT_ROOT}")
    print(f"target:    {target}")
    print(f"uv:        {uv}")
    print("templates:")
    print("\n".join(copy_templates(target)))
    mcp_path = write_mcp_json(target, uv)
    print(f"wrote      {mcp_path} (build_report requires manual approval)")

    print("self-test: starting the server once against the target...")
    result = subprocess.run([uv, "run", "--locked", "--directory", str(SERVER_DIR), "python", "server.py",
                             "--target-repo", str(target), "--self-test"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"server self-test failed:\n{result.stderr.strip() or result.stdout.strip()}")
    payload = json.loads(result.stdout)
    for key in ("target_repo", "target_head_sha", "target_clean", "analyzer_head_sha", "analyzer_clean", "python"):
        print(f"  {key:18} {payload[key]}")
    print("\nNext: commit .bob/custom_modes.yaml and .bob/skills/ in the target (mcp.json stays untracked),")
    print("then reload Bob in the target workspace and run Task 1.")


if __name__ == "__main__":
    main()
