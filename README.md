# Invariant — code review for ML correctness

*Your code compiles. Your tests pass. Your results are wrong.*

Invariant reviews machine-learning pull requests for a class of bug that ordinary review and
testing miss: evaluation leakage. It **measures** the problem on the project's own data, builds a
deterministic, commit-bound **Validity Report**, and blocks the merge through a **required CI
check**. IBM Bob drives the review, explains the finding, writes the fix and the regression tests,
and opens the fix pull request.

Built with IBM Bob 2.0 for the IBM Bob 2.0 Hackathon (lablab.ai, 25–27 September 2026).
Sample project: [`invariant-demo-nsclc`](https://github.com/mibrahim210/invariant-demo-nsclc),
a fully synthetic, NSCLC-inspired imaging benchmark. No real patient data is used anywhere.

## Results (measured, with sources)

| What | Before (Report A) | After (Report B) | Source |
|---|---|---|---|
| Patients in both train and test | **166** (of 166 test patients) | **0** | Reports A and B |
| Status | `blocked` | `no_findings` | Reports A and B |
| Patient-disjointness guard test | none recognized | recognized | Reports A and B |
| Regression tests | missing | 4 passed | Reports A and B |
| Patient-level AUC, seed 0 | 1.000 | 0.663 | `comparisons/c7736d4e_b82ed850.json` |
| Patient-level AUC, mean of 5 seeds | 1.000 | 0.617 | same file (population SD 0.045) |
| Existing baseline tests | pass | pass | CI on PR #1 |

- **Report A** `reports/invariant-demo-nsclc/873d009…/c7736d4e…/` — buggy PR head `873d009`.
- **Report B** `reports/invariant-demo-nsclc/555dd62…/b82ed850…/` — fix commit `555dd62`.
- Both reports were built by the same analyzer commit (`ee0bb7c`) that CI pins, bind the protocol,
  metadata, configuration and image-manifest hashes, and list 11 historical training runs
  confirmed affected by the leak (7.9 s CPU time; history never changes status).
- The AUC values come from training sweeps committed in the demo repository. The leaky and grouped
  splits hold out different patients, so the drop describes this engineered benchmark only; it is
  not a clinical performance claim.
- Bob usage for the whole build: **9.52 of 40 Bobcoins** (account usage). Per-task detail and every
  prompt are in [`docs/bob_tasks.md`](docs/bob_tasks.md); task summaries are in `bob_sessions/`.

## The acceptance sequence, demonstrated

| # | Step | Evidence |
|---|---|---|
| 1 | Existing tests pass on the buggy pull request | PR #1: `baseline-tests` green, `invariant` red, merge blocked |
| 2 | Invariant measures patient overlap | `verify_split_overlap`: 166 at `873d009` |
| 3 | Report A records `blocked` before any edit | Report A `c7736d4e` (the builder refuses a dirty tree) |
| 4 | Bob writes the fix and regression tests | commit `555dd62`: grouped split + `tests/test_split_invariants.py` |
| 5 | The fixed commit passes | PR #2: all checks green |
| 6 | Report B records the fixed commit, history retained | Report B `b82ed850`: `no_findings` |
| 7 | Reintroducing the bug fails the required check | PR #3: overlap 166, two regression tests fail, merge blocked, closed |

In PR #3 the ordinary `baseline-tests` job stays green while `invariant` blocks the merge — the
problem this tool exists for.

## How it works

```
Bob (ML Reviewer mode) ──MCP──► Invariant server ──subprocess──► target repo's own environment
                                   │
      inspect_split ───────────────┤ static: where the split happens, is it group-aware?  (risk)
      find_invariant_tests ────────┤ static: does any test assert patient disjointness?   (coverage)
      verify_split_overlap ────────┤ runs the real split on the real metadata; validates the
                                   │ partition; counts patients in both sets               (proof)
      run_required_tests ──────────┤ runs the configured regression tests                  (proof)
      build_report ────────────────┘ runs all four itself, hashes committed inputs, derives
                                     status, writes an append-only report; Bob supplies text only
```

- **Static checks raise risk; measurements prove it; the builder decides status; Bob explains
  and fixes.** Bob cannot pass a status, SHA or hash to the builder.
- **Status** (current commit only): `blocked` > `review_required` > `no_findings`. An invalid
  partition is `blocked`, never a zero-overlap pass. The full table is in
  [`docs/task4_acceptance.md`](docs/task4_acceptance.md).
- **Binding.** The builder refuses a dirty target or analyzer checkout, hashes committed blob bytes
  (identical on Windows and Linux), verifies the head CI expected, and writes each execution to a
  new `reports/<repo>/<head_sha>/<run_id>/` directory that is never overwritten.
- **CI.** The demo repo's `invariant` job checks out the exact PR head and this repository at a
  pinned commit, runs the same builder, and passes only on `no_findings`. It is a required check
  on `main`.
- **Bob integration.** `install.py` copies the ML Reviewer mode and the data-leakage skill into the
  target's `.bob/` and writes `mcp.json` with absolute paths. `build_report` is never
  auto-approved, so report creation is always a visible human approval.

## Scope and limitations

- **Checked:** protocol INV-1, patient-level train/test independence.
- **Not checked:** INV-2 train-only fitting and INV-3 inference consistency. Every report lists
  them as `not_checked`.
- **Guard detection is pattern-based.** It recognizes disjointness asserted inline, through a
  same-file helper, or through a variable holding an intersection. It does not yet follow two
  variables that each hold one patient set (`a.isdisjoint(b)`); Bob's original assertion used that
  form and was routed through a helper by hand. Following such variables is on the roadmap.
- **Human review of Bob's output.** Each Bob task was verified against the real server and demo
  repository with expected results fixed in advance; the defects found and fixed are listed in
  [`docs/bob_tasks.md`](docs/bob_tasks.md).
- Invariant flags risk and records evidence. It does not determine regulatory compliance; a
  qualified human does. The evidence is relevant to data-governance expectations such as the EU AI
  Act (Article 10) and the Good Machine Learning Practice principle that training and test data are
  independent.

## Install into a target repository

```bash
python install.py --target-repo ../invariant-demo-nsclc
```

The target must be a git repository root with `invariant.toml` and `.bob/mcp.json` in its
`.gitignore`. The installer copies the mode and skill, writes `mcp.json` (timeout in milliseconds:
600000), and self-tests the server.

## Development

```bash
cd mcp-server
uv sync --locked
uv run --locked pytest -q
uv run --locked python scripts/check_mcp.py /absolute/path/to/target/.bob/mcp.json
uv run --locked python -m report.builder --target-repo PATH --reports-root /tmp/dry-run
```

Python 3.12 (pinned), MCP SDK `mcp>=1.10,<2` (FastMCP).

## Repository layout

| Path | Content |
|---|---|
| `mcp-server/` | MCP server, analyzers, report builder, tests |
| `templates/bob/` | ML Reviewer mode and data-leakage skill installed into targets |
| `install.py` | installer |
| `reference/` | reference grouped split used only for the pre-review measurement |
| `reports/` | all Validity Reports, including the failed first review attempt at `7595c00` |
| `comparisons/` | A/B comparison with measured metrics and their sources |
| `scripts/make_comparison.py` | builds the comparison from report and sweep files |
| `docs/` | Bob task prompts and record, Task 4 acceptance table, evidence guide |
| `bob_sessions/` | Bob task summaries and acceptance screenshots |

## License

MIT (see `LICENSE`).