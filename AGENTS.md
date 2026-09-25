# invariant

ML-correctness reviewer for pull requests. Measures patient-level train/test leakage,
builds deterministic commit-bound Validity Reports, and gates merges with a required CI check.

## Layout (Tool Repository)

- mcp-server/server.py — FastMCP entry; requires absolute --target-repo
- mcp-server/analyzers/ — inspect_split, verify_overlap, coverage, run_tests
- mcp-server/report/ — builder.py, status.py, schema.json
- mcp-server/tests/ — fixtures/, test_status_table.py, test_output_budget.py
- action/ — runs the same builder with the target's invariant.toml
- install.sh — installs .bob/ into the target with absolute MCP paths
- reports/, comparisons/ — generated deterministically; never edit by hand
- viewer/ — static A/B report viewer (Vercel)

## Engineering invariants (do not weaken)

- mcp-server/report/status.py derives status from current-commit checks:
  blocked > review_required > no_findings.
- The builder computes authoritative SHAs and hashes; trusted CI supplies
  expected SHAs for verification. Bob supplies explanations, never evidence values.
- Bind the target via --target-repo, never cwd.
  Dirty target or analyzer tree → authoritative report refused.
- Report dirs <repo>/<head_sha>/<run_id>/ are created exclusively; never overwritten.
- Preserve Report A before edits; commit the fix and rerun checks for Report B.
- Invalid partition → blocked, never a zero-overlap pass.
- History is informational; it never affects status.
- Analyzer output: compact JSON < 2 KB, lists ≤ 10, example IDs ≤ 5.
  Set truncated: true only when content is omitted.
- Never claim "compliant", "non-compliant", "safe" or "OK to merge".

## Strict Behavioral Rules

- Read only @-mentioned files or files an analyzer points to. No repo scans.
- Never open ignored paths: data/, *.npy, mlruns/, reports/**, uv.lock, .venv/.
- Plan at most once per task, then implement. Do only what the prompt asks.
- Same failure after 2 fix attempts → stop and report error. No loops.
- Final message ≤ 10 lines. No echoing files, no monologue files.