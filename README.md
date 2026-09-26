# Invariant - code review for ML correctness

*Your code compiles. Your tests pass. Your results are wrong.*

Invariant measures patient-level train/test leakage in a pull request, builds deterministic,
commit-bound Validity Reports, and blocks the merge through a required CI check. Built with
IBM Bob 2.0 for the IBM Bob 2.0 Hackathon (lablab.ai, September 2026).

Status: scaffolding. Analyzers and the report builder are built in Bob tasks 2-4
(`docs/bob_tasks.md`); every task summary is in `bob_sessions/`.

## Install into a target repository

```bash
python install.py --target-repo ../invariant-demo-nsclc
```

The target must be a git repository root containing `invariant.toml`, with `.bob/mcp.json` in its
`.gitignore`. The installer copies the ML Reviewer mode and data-leakage skill, writes `mcp.json`
with absolute paths (`build_report` always requires manual approval), and self-tests the server.

## Development

```bash
cd mcp-server
uv sync --locked
uv run --locked pytest -q
uv run --locked python scripts/check_mcp.py /absolute/path/to/invariant-demo-nsclc/.bob/mcp.json
```

## Scope

Checks protocol invariant INV-1 (patient independence). Train-only fitting and inference
consistency are reported as `not_checked`. Invariant flags risk and records evidence; a qualified
human determines compliance. Sample data is fully synthetic (see the demo repository).
