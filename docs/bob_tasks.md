# Bob task prompts and record

One task per step. Each prompt below is the one actually used. Task summary screenshots and
costs are in `bob_sessions/` (see `docs/bob_evidence_capture_guide.md`).

## Operating rules learned during the build

- **MCP timeout is in milliseconds.** `.bob/mcp.json` uses `"timeout": 600000` (10 minutes).
  With `600` (0.6 s) every tool that launches `uv` was abandoned by Bob and the server restarted,
  even though the tool finished in 3-6 s. `install.py` writes 600000.
- **Approvals.** In the per-task permission panel keep Read ticked and leave MCP, Edit and
  Subagent unticked for review tasks: every analyzer call, file edit and subagent spawn is
  approved by hand, and `build_report` (never in `alwaysAllow`) is always a visible approval.
- **Call MCP tools one at a time.** The server handles one call at a time.
- **Stop rule.** If a task fails on setup or integration, stop, fix by hand and confirm with a
  zero-coin check (`mcp-server/scripts/check_mcp.py`, `call_tool.py`). No paid debugging tasks.
- **Screenshots never go into either checkout while a report can be built.** An untracked file
  makes the target (R1) or the analyzer (R2) dirty and the builder refuses. They were kept in
  `../bob_sessions_staging/` and copied into `bob_sessions/` after Report B.
- **Every Bob task was verified independently** against the real server and the demo repo with
  expected results fixed in advance. What those checks caught is summarized below; fixes are in
  separate commits.

## Record

| Task | Workspace | Mode | Budget | Task header value (Bobcoins) |
|---|---|---|---|---|
| 1 Smoke test | invariant-demo-nsclc | ML Reviewer | 2 | 0.133 (3 attempts: 0.044 + 0.044 + 0.045) |
| 2 Static analyzers | invariant | Agent | 5 | 2.30 |
| 3 Execution analyzers | invariant | Agent | 5 | 4.56 |
| 4 Report builder + status | invariant | Agent | 4 (+ contingency) | 7.32 |
| 5 Review, Report A, fix | invariant-demo-nsclc | ML Reviewer | 5 | 1.120 (attempt 1: 0.611; attempt 2: 0.509) |
| 6 Fix PR, Report B | invariant-demo-nsclc | Agent | 2 | 0.811 (same chat as Task 5 attempt 2; chat total 1.32) |
| **Total** | | | **23** | **9.52 of 40 (account usage)** |

The total is the account usage figure reported by IBM Bob, which is the billed amount. Per-task values are the running totals shown in each Bob task header; they
sum to 16.24 and do not reconcile with the account figure, so they are treated as relative
per-task costs. Task 5 attempt 2 and Task 6 share one chat, whose final header value (1.32) is
counted once; the intermediate snapshots in `bob_sessions/costs.txt` (0.843, 0.901, 1.02) are not
added.

### Review of Bob's work

Bob wrote the MCP analyzers, the report builder, the status table, the schema and most of the
tests, and it ran the review, wrote the fix and opened the fix pull request. We treated its output
the way Invariant treats a pull request: every task was checked against the real repository with
expected results fixed in advance, before it was committed.

| Task | What the independent check caught | Fix |
|---|---|---|
| 1 | MCP timeout read in milliseconds; child processes inherited the MCP pipe on Windows | Timeout 600000; shared subprocess helper (`proc.py`) with diagnostics |
| 2 | Splitter calls inside `make_split` not reported; helper-based guard tests and BOM-encoded files missed | Analyzer corrected; 6 regression tests added |
| 3 | Overlap counted shared rows instead of patients; seed 0 fell back to 42; runner crashed on index labels | Patient-level overlap; explicit seed handling; tests corrected |
| 4 | `inspect_split` result rejected by validation; protocol not hashed; invariants always `not_checked` | Per-analyzer validation; byte-level hashing incl. protocol; declared invariants |
| 5 | First attempt lost tool replies (timeout); guard detector missed `a.isdisjoint(b)` | Rerun after the timeout fix; assertion routed through a helper (known limit) |
| 6 | Create Pull Request workflow could not load the repository | Bob opened PR #2 with `gh pr create` |

After these checks, dry runs reproduced `blocked` on the buggy head and `no_findings` on the fix,
and CI reproduced both independently. Report A `c7736d4e` (`blocked`, 166 patients at `873d009`)
and Report B `b82ed850` (`no_findings` at `555dd62`) are in `reports/`. The six reports written
during the first review attempt (at `7595c00`) are kept as history.

---

## Task 1 - smoke test (demo repo workspace, ML Reviewer mode)

Before: `uv run --locked python --version` in mcp-server prints 3.12.x;
`python install.py --target-repo ../invariant-demo-nsclc` succeeded; the zero-coin check
`uv run --locked --directory ../invariant/mcp-server python scripts/check_mcp.py <ABSOLUTE mcp.json>`
lists `hello`; the installed `.bob/custom_modes.yaml` and skill are committed in the demo repo,
and Bob was reloaded.

```
Smoke test only. Call the invariant MCP tool `hello` once. Reply in at most 6 lines with:
target_repo, target_head_sha, target_clean, analyzer_head_sha, and whether the
data-leakage skill is available. Do not read files, edit files or call other tools.
```

Pass: the mode is selectable with read, mcp, skill, edit and subagent tools and the explore
preset only, and `target_head_sha` equals `git rev-parse HEAD` in the demo repo.

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

Verified afterwards with `call_tool.py` on the demo repo: `train_test_split` at line 9 stratified
on `label`; `no_recognized_guard` on the buggy tests; `recognized_guard` with the planned test.

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

Never change a test's expected result to make it pass; fix the code or report the conflict.
Unit-test partition validation and junit parsing with in-memory fixtures in
mcp-server/tests/test_execution_analyzers.py (empty, duplicate, unknown, shared, omitted,
missing group ID; failed, error, zero collected, missing file). Add an integration test
that runs only when INVARIANT_DEMO_REPO is set and asserts state valid and
overlap_count > 0. Extend test_output_budget.py. Run `uv run --locked pytest -q` in
mcp-server. Final message <= 10 lines.
```

Verified afterwards: `verify_split_overlap` on the demo repo gives `valid`, overlap 166 of 166
test patients, seed 0, matching the recorded seed-0 training run; the grouped split gives 0.

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

Verified afterwards with two zero-coin dry runs into a temporary reports folder: the buggy PR
head gave `blocked` (exit 1); a throwaway worktree with the grouped split and the regression
test committed gave `no_findings` (exit 0). CI then reproduced `blocked` on the PR head.

## Task 5 - measured review, Report A, fix (demo repo workspace, ML Reviewer mode)

Before: the Invariant CI check is required on `main` and red on the PR head; the demo repo is
checked out on the PR branch (`feature/predict-cli`) with a clean working tree; the `invariant`
checkout is clean; `.bob/mcp.json` has `"timeout": 600000`; Bob was restarted.

Prompt used for attempt 2 (attempt 1 lacked the second and third lines):

```
Review the checked-out pull request head for ML correctness, following your mode's steps 0-7.
Call MCP tools one at a time and wait for each result. If any tool errors or times out,
stop and report it; do not edit any file.
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

Result: Report A `c7736d4e` - `blocked` at `873d009`, overlap 166, analyzer `ee0bb7c`.

## Task 6 - fix PR and Report B (demo repo workspace, Agent mode, same chat as Task 5)

Commit and push:

```
Create the branch fix/patient-independent-split from the current HEAD. Commit only
demo_repo/splits.py and tests/test_split_invariants.py with the message
"Use a patient-grouped split and add patient-independence regression tests".
Push the branch and open a pull request into feature/predict-cli using Bob's pull request
feature. In the description, state the measured overlap from Report A (166 patients in both
sets at 873d009, report run c7736d4e), the fix, and that the test's disjointness assertion
was routed through a patient_overlap helper by hand so Invariant's guard detector recognizes it.
Then, on the committed state, call run_required_tests, verify_split_overlap,
find_invariant_tests and build_report one at a time, and report the status, head_sha and
report path. Do not edit any file. Final message <= 10 lines.
```

The Create Pull Request workflow failed ("Failed to load repository data"), also after GitHub
CLI login. Fallback used:

```
The Create Pull Request workflow cannot load the repository. Create the pull request with the
GitHub CLI instead. Run exactly one command:
gh pr create --base feature/predict-cli --head fix/patient-independent-split --title "Use a patient-grouped split and add patient-independence regression tests" --body "<description as above>"
Do not write any file, commit or push. Report the PR URL.
```

Report B:

```
The fix is committed and the pull request is open. On the committed state, call
run_required_tests, verify_split_overlap, find_invariant_tests and build_report one at a time.
For build_report, explain what changed since Report A (run c7736d4e) and why the checks now pass.
Report the status, head_sha and report path. Do not edit any file. Final message <= 10 lines.
```

Result: PR #2 green; Report B `b82ed850` - `no_findings` at `555dd62`, overlap 0, 4 tests passed,
guard recognized, 11 historical affected runs retained. PR #2 and PR #1 were then merged; PR #3,
which restores the row-level split, was blocked by the required check (overlap 166, two
regression tests failing) and closed without merging.