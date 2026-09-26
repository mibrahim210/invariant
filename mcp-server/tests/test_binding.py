"""Target binding: absolute path, git root, invariant.toml. Handwritten before Task 1."""
import json
import subprocess
from pathlib import Path

import pytest

from server import BindingError, bind_target, hello_payload


def make_repo(path: Path, with_toml: bool = True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if with_toml:
        (path / "invariant.toml").write_text("[target]\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init", "--allow-empty"], check=True)
    return path


def test_relative_path_rejected():
    with pytest.raises(BindingError, match="absolute"):
        bind_target("relative/path")


def test_non_git_rejected(tmp_path):
    with pytest.raises(BindingError, match="not a git repository"):
        bind_target(str(tmp_path))


def test_subdirectory_rejected(tmp_path):
    repo = make_repo(tmp_path / "repo")
    (repo / "sub").mkdir()
    with pytest.raises(BindingError, match="repository root"):
        bind_target(str(repo / "sub"))


def test_missing_toml_rejected(tmp_path):
    repo = make_repo(tmp_path / "repo", with_toml=False)
    with pytest.raises(BindingError, match="invariant.toml"):
        bind_target(str(repo))


def test_hello_reports_binding_under_2kb(tmp_path):
    repo = make_repo(tmp_path / "repo")
    payload = hello_payload(bind_target(str(repo)))
    assert payload["target_repo"] == repo.resolve().as_posix()
    assert len(payload["target_head_sha"]) == 40 and payload["target_clean"] is True
    assert len(json.dumps(payload).encode()) < 2048
