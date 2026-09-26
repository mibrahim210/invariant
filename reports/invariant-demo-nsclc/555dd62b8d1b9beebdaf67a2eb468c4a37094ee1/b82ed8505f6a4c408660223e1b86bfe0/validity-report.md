# Validity Report

## Binding

- **Repository**: `C:/Users/mdibr/Desktop/LabLab/IBM Bob Hackathon/ibm-bob2.0-hackathon-2026/invariant-demo-nsclc`
- **head_sha**: `555dd62b8d1b9beebdaf67a2eb468c4a37094ee1`
- **base_sha**: `e739727886a3dd69a2c2733a97877754a0cfee28` (source: invariant.toml)
- **run_id**: `b82ed8505f6a4c408660223e1b86bfe0`
- **analyzer_commit**: `ee0bb7c880483419e04895ac762119d5c0f6ed07`
- **status**: **no_findings**

### Input hashes

- `invariant.toml`: `017d737163f27bdf72eab7b1cebd43f048eb872de298ade3cb97ff33e673128a`
- `configs/data_generation.json`: `5d9eb59028f68955ca7a02b12d9453c9ad55caa461b4863aca27d8139f0015e5`
- `data/image_manifest.json`: `327ce4868f05975c99e8ed996afa9a410f92bb5e70d06c16d72f721175cc0568`
- `docs/study_protocol.pdf`: `6559268288013181fbe47f616c70f6b03ca71ba66df9ee2cc6317be422ad4473`
- `data/metadata.csv`: `aff30de03f8c87ca750c1752678069f1c3cd33d06703ae86c5c9e5ff2815dce0`

## Checks

### verify_split_overlap
- contribution: **none**
- summary: state=valid overlap_count=0

### regression_tests
- contribution: **none**
- summary: state=passed passed=4 failed=0 collected=4

### find_invariant_tests
- contribution: **none**
- summary: state=recognized_guard

### inspect_split
- contribution: **none**
- summary: risk_indicators=[]

## Invariants

- `patient_independence`: checked
- `train_only_fitting`: not_checked
- `inference_consistency`: not_checked

## History

- confirmed_affected runs: 11
- potentially_affected runs: 0
- CPU time on confirmed runs (s): 7.906
- wall time on confirmed runs (s): 9.364
- timing boundary: [None, 'split + partition validation + feature preparation (array load and block means) + fit + prediction + evaluation; excludes image-manifest verification, MLflow logging and manifest writing']
- History is informational and does not affect status.

## Reviewer explanation (Bob, not evidence)

## Changes since Report A (run c7736d4e, head 873d009, status: blocked)

**What changed:**
- `demo_repo/splits.py`: replaced `train_test_split` (row-level, no grouping) with `GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)` grouped on `patient_id`. All slices of a patient now land in exactly one partition, satisfying INV-1.
- `tests/test_split_invariants.py` (new file): adds a `patient_overlap` helper function that computes the intersection of patient sets across partitions; a fixed 20×3 fixture; domain tests for disjointness, full coverage, and non-emptiness; and a Hypothesis property test over variable patient/slice/seed/test_size combinations. The disjointness assertion is routed through `patient_overlap` so Invariant's guard detector recognises it.

**Why the checks now pass:**
- `verify_split_overlap`: overlap_count dropped from 166 to **0** — no patient appears in both train (160 patients) and test (40 patients).
- `find_invariant_tests`: now `recognized_guard` — evidence at `tests/test_split_invariants.py:46` and `:77`.
- `regression_tests`: all 4 tests pass (was: file not found in Report A).
- `inspect_split` risk indicator remains as a static note but the measured finding is resolved.

## Remediation

No further remediation required for INV-1. INV-2 (train_only_fitting) and INV-3 (inference_consistency) remain not_checked and are out of scope for this PR.