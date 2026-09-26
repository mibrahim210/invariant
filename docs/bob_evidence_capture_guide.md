# Bob evidence capture guide

Use this guide alongside `invariant/docs/bob_tasks.md`. The six Bob task summaries are required submission evidence. Capture extra images where they demonstrate an acceptance step or a feature that a summary cannot show.

## Where to save images and costs

Before Task 1, create `bob_sessions_staging/` **beside** `invariant/` and `invariant-demo-nsclc/`. Save every screenshot there until Report B has been built. Keep a small cost note there too, for example `bob_sessions_staging/costs.txt`, with the task number and the actual coins shown by Bob.

Do not edit the **Actual** column in `invariant/docs/bob_tasks.md` while reports still need to be built. The report builder requires a clean analyzer checkout; an edited table or an untracked PNG in `invariant/` can make it refuse the report. The demo checkout must also be clean for Report A. After Report B, transfer the screenshots and costs into `invariant/` and commit them.

## Required task summaries

When each task finishes, open its **task session consumption summary** in Bob and screenshot it promptly, with the task identity and coin cost visible. Save a PNG using your fixed team name in place of `<team>`.

| Task | Staging filename |
|---|---|
| 1 · smoke test | `<team>_task01_smoke_test_summary.png` |
| 2 · static analyzers | `<team>_task02_static_analyzers_summary.png` |
| 3 · execution analyzers | `<team>_task03_execution_analyzers_summary.png` |
| 4 · report builder | `<team>_task04_report_builder_summary.png` |
| 5 · review and Report A | `<team>_task05_review_report_a_summary.png` |
| 6 · fix PR and Report B | `<team>_task06_fix_pr_report_b_summary.png` |

After saving each summary, add its cost to `bob_sessions_staging/costs.txt`. Select **All** in Bob's Tasks list when moving between the two project workspaces so you can find every task.

## Additional acceptance evidence

Capture these at the stated moment; keep every PNG in the same staging folder. Include the visible branch, commit SHA, check name or report run ID where applicable. Use separate images when one screen cannot show the evidence legibly.

| Moment | Suggested staging filename | Capture |
|---|---|---|
| Before the Invariant CI gate is wired | `<team>_baseline_pr_green.png` | Buggy PR head and existing baseline test checks green. This establishes acceptance step 1. |
| After CI wiring, before Task 5 | `<team>_buggy_pr_gate_red.png` | Same PR head: baseline tests green, Invariant check red, and merge blocked. |
| After branch protection is set | `<team>_required_check_settings.png` | `main` protection/ruleset showing the Invariant check as required. |
| During Task 5, immediately after Report A | `<team>_report_a_blocked.png` | Report A `blocked`, reviewed head SHA, measured patient overlap **N**, and report/run ID. Capture before editing the split. |
| During Task 5 | `<team>_parallel_explore_subagents.png` | Parallel panel showing both `explore` subagents. |
| After Task 6 | `<team>_fix_pr.png` | Fix PR targeting `feature/predict-cli`, with the fix commit visible. |
| After Task 6 | `<team>_report_b_no_findings.png` | Report B `no_findings` at the fix SHA, overlap zero, tests passed, and historical affected runs retained. Together with the fix diff, this supports acceptance steps 4–6. |
| Final verification | `<team>_regression_gate_red.png` | Separate branch that reintroduces the bug: required check red and merge blocked. This is acceptance step 7. Preserve the fixed branch and Report B. |

Screenshots support the record; the authoritative numbers and status remain in committed run manifests, CI output, and Reports A and B. Do not put a future fix result into Report A.

## Transfer after Report B

From the parent directory that contains both repositories and `bob_sessions_staging/`, use PowerShell:

```powershell
New-Item -ItemType Directory -Force .\invariant\bob_sessions | Out-Null
Copy-Item .\bob_sessions_staging\*.png .\invariant\bob_sessions\
Set-Location .\invariant
# Fill the Actual column in docs/bob_tasks.md from ..\bob_sessions_staging\costs.txt.
git add -- bob_sessions docs/bob_tasks.md
git status --short
git commit -m "Record Bob task summaries and acceptance evidence"
git push
git status --porcelain
```

Review and commit Reports A and B and any comparison artifact as their own deliberate deliverables; the command above stages only the evidence images and cost table. A later evidence commit changes the analyzer repository's current HEAD, but it does not rewrite either report's recorded analyzer SHA. Confirm `git status --porcelain` is empty before any further report build.

Rehearse and record the video separately after the evidence is secure. The screenshots are the submission evidence, not the video recording.
