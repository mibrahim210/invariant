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

## Task 2 - static analyzers (invariant workspace, Agent mode)

```
Implement two static MCP analyzers in @mcp-server/server.py, following @AGENTS.md.
Target code is read from the bound --target-repo only; never import or execute it.
Read the target's invariant.toml with tomllib; resolve a split_function like
"demo_repo.splits:make_split" to <target>/demo_repo/splits.py.

1. mcp-server/analyzers/inspect_split.py -> tool `inspect_split()`:
   From [target] read split_function, group_key and metadata. Parse the split module with
   ast. Report: file, line and call name of each split call; group_aware (GroupShuffleSplit,
   GroupKFold, StratifiedGroupKFold, LeaveOneGroupOut, or a groups= argument); stratify
   column if any; identity columns found in the metadata CSV header (header line only);
   risk_indicators, e.g. "row_level_split_with_group_key_in_metadata".
2. mcp-server/analyzers/coverage.py -> tool `find_invariant_tests()`:
   Parse <target>/tests/**/*.py with ast. recognized_guard: a test that calls the configured
   split function and asserts an empty intersection or disjointness of sets built from the
   group_key column (e.g. df.loc[train, "patient_id"]) of both outputs. Disjointness of row
   IDs or index labels is NOT a guard. no_recognized_guard: all tests parse and none
   qualifies. unknown: parse errors, or split outputs used indirectly so the asserted sets
   cannot be resolved. Return state and evidence as file:line (max 10).

Both return compact JSON < 2 KB, lists <= 10, truncated only when content is omitted.
Fixtures: small target repos under mcp-server/tests/fixtures/ (row-level split, grouped
split, grouped via groups=, patient-disjointness guard test, row-ID-only disjointness test,
unparsable test). Create mcp-server/tests/conftest.py with collect_ignore_glob =
["fixtures/*"] so fixture files are never collected. Tests go in
mcp-server/tests/test_static_analyzers.py; create test_output_budget.py with a < 2 KB check
for both tools. Run `uv run --locked pytest -q` in mcp-server. Final message <= 10 lines.
```

## Task 3 - execution analyzers (invariant workspace, Agent mode)

```
Implement two execution MCP analyzers in @mcp-server/server.py, following @AGENTS.md.
Target code runs only in a subprocess in the target's own environment:
`uv run --locked --directory <target> python <runner> ...`, started only through
proc.run_proc with a per-call timeout (runner 120 s, pytest 300 s).

1. mcp-server/analyzers/verify_overlap.py -> tool `verify_split_overlap()`, with
   mcp-server/analyzers/split_runner.py executed by the target's Python.
   The runner uses only the standard library and pandas (never Invariant modules), inserts
   the target root at sys.path[0], reads [target] metadata with pandas keeping the stored
   row order and reading row_id and group_key as str, sets row_id as index, calls
   split_function(df, seed=split_seed), converts both outputs to lists of str and writes
   {"train": [...], "test": [...]} to an output path given as an argument (a temp file
   outside both repositories). Nothing is parsed from stdout.
   The analyzer (stdlib only, csv module) validates the partition contract against the
   metadata: unique row IDs, non-missing group IDs, both sets non-empty, no unknown or
   duplicate IDs, no shared rows, union covers every row exactly once. Return state
   valid / invalid_partition / error, partition_errors, overlap_count, train and test
   group counts, up to 5 example group IDs. Invalid partitions are never zero overlap.
2. mcp-server/analyzers/run_tests.py -> tool `run_required_tests()`:
   Run `python -m pytest -q -p no:cacheprovider --junitxml=<temp file outside both repos>`
   on [checks] regression_tests in the target env. Return passed / failed / errors /
   skipped / collected counts and a state: passed, failed, no_tests (exit 5),
   collection_error (missing files, exit 4, or no junit file), crash (timeout or other).
   No test output text.

Never change a test's expected result to make it pass; fix the code or report the conflict.Unit-test partition validation and junit parsing with in-memory fixtures in mcp-server/tests/test_execution_analyzers.py (empty, duplicate, unknown, shared, omitted,
missing group ID; failed, error, zero collected, missing file). Add an integration test
that runs only when INVARIANT_DEMO_REPO is set and asserts state valid and
overlap_count > 0. Extend test_output_budget.py. Run `uv run --locked pytest -q` in
mcp-server. Final message <= 10 lines.
```

## Task 4 - report builder and status (invariant workspace, Agent mode)

```
Implement mcp-server/report/status.py, builder.py and schema.json and the MCP tool
`build_report(explanation_md, remediation_md)` so that every row of
@docs/task4_acceptance.md is a passing test (S*, P* in test_status_table.py; R*, W*, H* in
test_builder.py using temporary git repositories and stubbed check results).
Follow @AGENTS.md. The builder computes all SHAs, hashes, check results and status; the
caller supplies text only. Never change a test's expected result to make it pass; fix the
code or report the conflict.

Checks: the builder calls the existing analyzers in-process through an injectable mapping
of check runners (tests pass stubs): inspect_split -> analyzers.inspect_split.run(target),
verify_split_overlap -> analyzers.verify_overlap.run(target), find_invariant_tests ->
analyzers.coverage.run(target), regression_tests -> analyzers.run_tests.run(target).
Status mapping (derive from each result's `state`, never from overlap_count alone):
- verify_split_overlap: invalid_partition -> blocked; valid with overlap_count > 0 ->
  blocked; valid with overlap_count == 0 -> none; error or anything else -> review_required.
- regression_tests: failed -> blocked; passed with collected > 0 -> none; no_tests,
  collection_error, crash -> review_required.
- find_invariant_tests: recognized_guard -> none; no_recognized_guard, unknown ->
  review_required.
- inspect_split: any risk_indicators while overlap_count == 0 -> review_required.
- a missing result, an "error" key, or a schema failure -> review_required.

Bindings: git runs only through proc.run_cmd. Hash inputs from committed blobs
(`git cat-file blob <head_sha>:<path>`). Target dirty (git status --porcelain, untracked
included) -> refuse. Analyzer dirty outside reports/ and comparisons/ -> refuse.
The builder takes reports_root and analyzer_root parameters, defaulting to
<invariant>/reports and <invariant>; tests always use temporary directories.

CLI: `python -m report.builder --target-repo PATH [--reports-root PATH]
[--expected-head SHA --expected-base SHA]`; print the compact summary; exit 0 on
no_findings, 1 on blocked or review_required, 2 on refusal.
Run `uv run --locked pytest -q` in mcp-server. Final message <= 10 lines.
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
