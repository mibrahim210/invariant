# Task 4 acceptance specification - report builder and status

Handwritten before Task 4. Bob implements `mcp-server/report/status.py`, `builder.py` and
`schema.json` so that every row below is a parametrized test in
`mcp-server/tests/test_status_table.py` (S*, P*) or `mcp-server/tests/test_builder.py` (R*, W*, H*).
Do not change a row's expected outcome to make a test pass; report the conflict instead.

## Inputs the builder owns

`build_report(explanation_md, remediation_md)` is the only entry point for Bob. It accepts no status,
SHA, hash, check result or path. Everything else is computed:

- target binding from `--target-repo`; `invariant.toml` from the target;
- `head_sha` from the target's HEAD; `base_sha` from `[review] base_ref` in `invariant.toml`
  (locally) or from trusted CI inputs `--expected-head` / `--expected-base`;
- SHA-256 of protocol, metadata, `invariant.toml`, `configs/data_generation.json`,
  `data/image_manifest.json`; analyzer commit SHA;
- results of every check in `[checks] required`, run by the builder itself.

The CI entry point is `python -m report.builder --target-repo ... [--expected-head SHA --expected-base SHA]`
and calls the same code.

## Status table (current commit only)

Precedence: `blocked` > `review_required` > `no_findings`.

| ID | Check | Result | Contribution |
|---|---|---|---|
| S1 | verify_split_overlap | invalid partition (any contract violation) | blocked |
| S2 | verify_split_overlap | missing patient IDs | blocked |
| S3 | verify_split_overlap | valid partition, overlap > 0 | blocked |
| S4 | verify_split_overlap | valid partition, overlap = 0 | none |
| S5 | verify_split_overlap | execution error or timeout | review_required |
| S6 | regression_tests | any test failed | blocked |
| S7 | regression_tests | collection error, missing file, crash | review_required |
| S8 | regression_tests | all passed (at least one test collected) | none |
| S9 | regression_tests | zero tests collected | review_required |
| S10 | find_invariant_tests | recognized_guard | none |
| S11 | find_invariant_tests | no_recognized_guard | review_required |
| S12 | find_invariant_tests | unknown | review_required |
| S13 | inspect_split | risk indicator present, overlap = 0 | review_required |
| S14 | inspect_split | risk indicator present, overlap > 0 | none from this row (S3 already blocks) |
| S15 | inspect_split | no risk indicator | none |
| S16 | any required check | missing from results | review_required |
| S17 | any required check | output fails schema validation | review_required |
| S18 | any required check | raised an exception | review_required |

| ID | Scenario | Expected status |
|---|---|---|
| P1 | one blocked and one review_required contribution | blocked |
| P2 | only review_required contributions | review_required |
| P3 | every required check completed, no contributions | no_findings |
| P4 | buggy head: overlap > 0, regression test file missing, no guard, row-level split | blocked |
| P5 | fix head: overlap 0, tests passed, recognized_guard, group-aware split | no_findings |
| P6 | historical runs with overlap > 0, current checks clean | no_findings (history never affects status) |

## Refusals (no report directory is created)

| ID | Condition | Expected |
|---|---|---|
| R1 | target working tree dirty | refused, message names the dirty paths (max 10) |
| R2 | analyzer checkout dirty outside `reports/` and `comparisons/` | refused |
| R3 | `--expected-head` given and differs from actual HEAD | refused |
| R4 | base ref missing or unresolvable, and no `--expected-base` | refused; never guessed |
| R5 | any bound input hash differs between before and after the checks | refused (execution invalid) |
| R6 | caller passes any argument other than explanation_md / remediation_md | rejected by the signature |

## Report writing

| ID | Requirement |
|---|---|
| W1 | Path is `reports/<target_repo_name>/<head_sha>/<run_id>/`; `run_id` is unique per invocation |
| W2 | Directory is created exclusively; an existing directory is never written into |
| W3 | Two builds at the same SHA produce two directories |
| W4 | `validity-report.json` validates against `schema.json`; `validity-report.md` is rendered from the JSON |
| W5 | The Markdown contains the heading `Reviewer explanation (Bob, not evidence)` holding the caller's text verbatim, and nothing from the caller appears elsewhere |
| W6 | Invariants are listed from `[invariants]` as `checked` / `not_checked` |
| W7 | Binding header: repo, head_sha, base_sha with its source, all hashes, analyzer commit, run_id, required vs completed checks, status |
| W8 | The MCP return is < 2 KB: status, head_sha, run_id, report path, per-check one-line summary |
| W9 | A report never references a later report or a fix result |

## History (informational)

Run manifests are the files `run_artifacts/<run_id>/manifest.json` committed at the reviewed HEAD.
Enumerate them with `git ls-tree -r --name-only <head_sha> -- run_artifacts/` and read them with
`git show <head_sha>:<path>`. Untracked or uncommitted manifests are never read (the clean-tree
refusal R1 already applies). `run_artifacts/sweeps/*.json` are summaries, not run manifests.

| ID | Requirement |
|---|---|
| H1 | Only committed `run_artifacts/<run_id>/manifest.json` at `head_sha` are read, as above |
| H2 | confirmed_affected: `metrics.overlap_count` is an integer > 0, regardless of `status` (older manifests may lack `status`) |
| H3 | potentially_affected: `metrics.overlap_count` is missing or null (for example `status` = `invalid_partition` or `failed`), or the manifest does not parse; a manifest with `metrics.overlap_count` = 0 is neither |
| H4 | compute: sums of `timing.cpu_time_seconds` and `timing.wall_time_seconds` over confirmed_affected runs, the count of confirmed runs missing either field, and the distinct `timing.timing_boundary` values (null when absent) |
| H5 | Lists hold run IDs (max 10 each, `truncated` when more) plus total counts; history is excluded from status (see P6) |
| H6 | Each report freezes the history observed at its own `head_sha`; Report B does not re-read Report A |

## Analyzer outputs the builder consumes

Every analyzer returns compact JSON < 2 KB with lists <= 10, example IDs <= 5 and
`truncated: true` only when content was omitted. The builder validates each against its
schema before deriving status (S17).
