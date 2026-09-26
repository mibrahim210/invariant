# Bob sessions and acceptance evidence

Task summaries (required submission evidence) and screenshots of each acceptance step.
Costs: `costs.txt` and `docs/bob_tasks.md`. Account usage screenshot: `invariant_bobcoin_usage.png`.

| File | Shows |
|---|---|
| `invariant_required_check_settings.png` | Branch protection on main: three required checks, no bypass |
| `invariant_step1_pr1_ci_run.png` | Step 1: CI run summary on PR #1 |
| `invariant_step1_pr1_gate_red.png` | Step 1: reviewed head, baseline green, Invariant red, merge blocked |
| `invariant_step1_pr1_gate_red_old.png` | Step 1 (earlier head): baseline green, Invariant red |
| `invariant_step1_pr1_head_873d009.png` | Step 1: PR #1 head 873d009 (the commit Report A binds) |
| `invariant_step1_pr1_head_old.png` | Step 1 (earlier head): PR #1 commit |
| `invariant_step5_pr2_checks_green.png` | Step 5: PR #2 into feature/predict-cli, all checks green |
| `invariant_step5_pr2_listed_green.png` | Step 5: PR #2 listed with 3/3 checks |
| `invariant_step6_pr1_green_after_fix.png` | After the fix merged: PR #1 green |
| `invariant_step7_pr3_ci_summary.png` | Step 7: PR #3 CI summary |
| `invariant_step7_pr3_gate_red.png` | Step 7: PR #3 reintroduces the bug; Invariant red, merge blocked |
| `invariant_step7_pr3_invariant_log.png` | Step 7: Invariant log, overlap 166, 2 tests failed, blocked |
| `invariant_step7_pr3_workflow_runs.png` | Step 7: failing workflow run for PR #3 |
| `invariant_task01_mcp_timeout_diagnostic.png` | Task 1: diagnostic of the MCP timeout |
| `invariant_task01_smoke_test_attempt2_summary.png` | Task 1, attempt 2: hello timed out (MCP timeout was read in milliseconds) |
| `invariant_task01_smoke_test_summary.png` | Task 1, attempt 3: hello returns the bound demo head and analyzer commit |
| `invariant_task02_static_analyzers_summary.png` | Task 2 summary: inspect_split and find_invariant_tests (2.30) |
| `invariant_task03_execution_analyzers_summary.png` | Task 3 summary: verify_split_overlap and run_required_tests (4.56) |
| `invariant_task04_report_builder_summary.png` | Task 4 summary: report builder, status table, schema (7.32) |
| `invariant_task05_attempt1_subagents.png` | Task 5, attempt 1: two explore subagents |
| `invariant_task05_attempt1_summary.png` | Task 5, attempt 1: tool replies lost; no Report A received by Bob |
| `invariant_task05_parallel_explore_subagents.png` | Task 5: two parallel explore subagents (patient_id trace, test coverage) |
| `invariant_task05_report_a_blocked.png` | Task 5: overlap 166 measured; Report A blocked at 873d009 |
| `invariant_task05_review_report_a_summary.png` | Task 5 summary: fix and tests written, 4 tests pass |
| `invariant_task06_create_pr_workflow_failed_1.png` | Task 6: Create Pull Request workflow failed (1) |
| `invariant_task06_create_pr_workflow_failed_2.png` | Task 6: Create Pull Request workflow failed (2) |
| `invariant_task06_fix_pr_report_b_summary.png` | Task 6 summary: Report B no_findings at 555dd62 |
| `invariant_task06_pr2_created_by_bob_gh.png` | Task 6: Bob opens PR #2 with gh pr create |
| `invariant_bobcoin_usage.png` | Account usage: 9.52 of 40 Bobcoins |
