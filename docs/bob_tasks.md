# Bob task prompts

One task per step. Paste the prompt as written.Save each task summary screenshot and its cost in `../bob_sessions_staging/` (see
`docs/bob_evidence_capture_guide.md`). Fill the Actual column below only after Report B.
Turn on Bob's MCP auto-approval: approval wait counts against the MCP timeout.
If a task fails on setup or integration, stop: fix by hand and confirm with a zero-coin check.
Do not open a second paid task to debug installation.

Screenshots never go into either checkout while a report can be built: an untracked PNG makes
the target (R1) or the analyzer (R2) dirty and the builder refuses. Save them to a staging folder
outside both repositories (for example `..\bob_sessions_staging\`) and copy them into
`invariant/bob_sessions/` in a separate commit only after Report B exists.

| Task | Workspace | Mode | Budget | Actual |
|---|---|---|---|---|
| 1 Smoke test | invariant-demo-nsclc | ML Reviewer | 2 | |
| 2 Static analyzers | invariant | Agent | 5 | |
| 3 Execution analyzers | invariant | Agent | 5 | |
| 4 Report builder + status | invariant | Agent | 4 (+ contingency, decide after Task 3) | |
| 5 Review, Report A, fix | invariant-demo-nsclc | ML Reviewer | 5 | |
| 6 Commit, fix PR, Report B | invariant-demo-nsclc | Agent | 2 | |

## Task 1 - smoke test (demo repo workspace, ML Reviewer mode)

Before: `uv run --locked python --version` in mcp-server prints 3.12.x;
`python install.py --target-repo ../invariant-demo-nsclc` succeeded; the zero-coin check
`uv run --locked --directory ../invariant/mcp-server python scripts/check_mcp.py <ABSOLUTE mcp.json>` lists `hello`; the installed
`.bob/custom_modes.yaml` and skill are committed in the demo repo, and Bob was reloaded.

```
Smoke test only. Call the invariant MCP tool `hello` once. Reply in at most 6 lines with:
target_repo, target_head_sha, target_clean, analyzer_head_sha, and whether the
data-leakage skill is available. Do not read files, edit files or call other tools.
```

Pass: the mode is selectable, the Modes tab shows it with read, mcp, skill, edit and subagent
tools and the explore preset only, `hello` runs without an approval prompt, and
target_head_sha equals `git rev-parse HEAD` in the demo repo.

## Task 2 - static analyzers (invariant workspace, Code mode)

```
Implement two static MCP analyzers in @mcp-server/server.py, following @AGENTS.md.
Target code is read from the bound --target-repo only; never import or execute it.

1. mcp-server/analyzers/inspect_split.py -> tool `inspect_split()`:
   Read [target] split_function, group_key and metadata from the target's invariant.toml.
   Parse the split module with ast. Report: file, line and call name of each split call;
   group_aware (GroupShuffleSplit, GroupKFold, StratifiedGroupKFold, LeaveOneGroupOut,
   or a groups= argument); stratify target if any; identity columns found in the metadata
   CSV header; risk_indicators, e.g. "row_level_split_with_group_key_in_metadata".
2. mcp-server/analyzers/coverage.py -> tool `find_invariant_tests()`:
   Parse tests/**/*.py with ast. recognized_guard: a test that calls the configured split
   function and asserts empty intersection or disjointness of group_key values from both
   outputs. no_recognized_guard: tests parse and none qualifies. unknown: parse errors or
   indirect calls that cannot be resolved. Return state, evidence as file:line (max 10).

Both return compact JSON < 2 KB, lists <= 10, truncated only when content is omitted.
Add fixtures under mcp-server/tests/fixtures/ (row-level split, grouped split, grouped via
groups=, guard test, non-guard test, unparsable test) and tests in
mcp-server/tests/test_static_analyzers.py plus a size check in test_output_budget.py.
Run `uv run --locked pytest -q` in mcp-server. Final message <= 10 lines.
```

## Task 3 - execution analyzers (invariant workspace, Code mode)

```
Implement two execution MCP analyzers in @mcp-server/server.py, following @AGENTS.md.
They run target code only in a subprocess, in the target's own environment:
`uv run --locked --directory <target> python <runner> ...`, started only through
proc.run_proc with a per-call timeout (runner 120 s, pytest 300 s).

1. mcp-server/analyzers/verify_overlap.py -> tool `verify_split_overlap()`:
   Runner loads metadata (index = [target] row_id), sorts by group_key then slice order
   as stored, calls split_function(df, seed=split_seed) and prints train/test row IDs as
   JSON. The analyzer (stdlib only) then validates the partition contract: unique row IDs,
   non-missing group IDs, both sets non-empty, no unknown or duplicate IDs, no shared rows,
   union covers every row exactly once. Return state valid / invalid_partition / error,
   partition_errors, overlap_count, train and test group counts, up to 5 example IDs.
   Invalid partitions are never reported as zero overlap.
2. mcp-server/analyzers/run_tests.py -> tool `run_required_tests()`:
   Run pytest on [checks] regression_tests in the target env with --junitxml to a temp
   file. Return passed / failed / errors / skipped / collected counts and a state:
   passed, failed, collection_error (includes missing files), crash. No test output text.

Unit-test partition validation and junit parsing with in-memory fixtures in
mcp-server/tests/test_execution_analyzers.py (empty, duplicate, unknown, shared, omitted,
missing group ID; failed, error, zero collected). Add an integration test that runs only
when INVARIANT_DEMO_REPO is set. Extend test_output_budget.py. Run the tests.
Final message <= 10 lines.
```

## Task 4 - report builder and status (invariant workspace, Code mode)

```
Implement mcp-server/report/status.py, builder.py and schema.json and the MCP tool
`build_report(explanation_md, remediation_md)` so that every row of
@docs/task4_acceptance.md is a passing test (S*, P* in test_status_table.py; R*, W*, H* in
test_builder.py using temporary git repositories and stubbed check results).
Follow @AGENTS.md. The builder computes all SHAs, hashes, check results and status; the
caller supplies text only. Do not change a row's expected outcome; report conflicts.
Also add the CLI `python -m report.builder --target-repo PATH [--expected-head SHA
--expected-base SHA]`. Run the tests. Final message <= 10 lines.
```

## Task 5 - measured review, Report A, fix (demo repo workspace, ML Reviewer mode)

Before: the Invariant CI check is required on `main` and red on the PR head; the demo repo is
checked out on the PR branch (`feature/predict-cli`) with a clean working tree; Tasks 2-4 are
merged in the `invariant` repo and its checkout is clean.

```
Review the checked-out pull request head for ML correctness, following your mode's steps 0-7.
0. Read the protocol named in invariant.toml; list its invariants as checked / not_checked.
1-3. Call inspect_split, verify_split_overlap and find_invariant_tests; report their results
   exactly as returned.
4. Call build_report with your explanation and remediation text before editing anything.
   Report the status, head_sha and report path it returns.
5. Spawn two explore subagents in parallel: (a) trace patient_id through data_gen.py,
   dataset.py, splits.py and train.py, anchored on the measured overlap; (b) determine
   whether the inspected tests guard patient disjointness, citing file:line evidence and
   stating uncertainty. Max 10 lines each; their output is explanation, not evidence.
6. Then write the minimal fix in demo_repo/splits.py (patient-grouped split, same signature,
   returns index labels) and add tests/test_split_invariants.py (fixed fixture of 20 patients
   x 3 images, a domain test, and a Hypothesis property test). Do not edit invariant.toml.
7. Stop without committing. Final message <= 10 lines.
```

Screenshot the summary and the parallel-subagents panel. Record the cost as C.

Optional, by hand, for the video: show the new tests failing on the old splitter with
`git worktree add ../nsclc-old HEAD`, copying tests/test_split_invariants.py into it and running
`uv run --locked pytest -q tests/test_split_invariants.py` there. Remove the worktree afterwards.

## Task 6 - commit, fix PR, Report B (demo repo workspace, Agent mode)

```
Create the branch fix/patient-independent-split from the current HEAD. Commit only
demo_repo/splits.py and tests/test_split_invariants.py with the message
"Use a patient-grouped split and add patient-independence regression tests".
Push the branch and open a pull request into feature/predict-cli using Bob's pull request
feature, describing the measured overlap from Report A and the fix. Then, on the committed
state, call run_required_tests, verify_split_overlap and build_report, and report the
status, head_sha and report path. Do not edit any other file. Final message <= 10 lines.
```

Report B must show `no_findings` at the fix commit, with the historical affected runs still in
its history block. Screenshot the summary.
