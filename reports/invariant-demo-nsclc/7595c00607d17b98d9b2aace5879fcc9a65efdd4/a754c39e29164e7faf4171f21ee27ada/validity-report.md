# Validity Report

## Binding

- **Repository**: `C:/Users/mdibr/Desktop/LabLab/IBM Bob Hackathon/ibm-bob2.0-hackathon-2026/invariant-demo-nsclc`
- **head_sha**: `7595c00607d17b98d9b2aace5879fcc9a65efdd4`
- **base_sha**: `7314aad4193a94a13b18df1b02b1b4921d1f3377` (source: invariant.toml)
- **run_id**: `a754c39e29164e7faf4171f21ee27ada`
- **analyzer_commit**: `ee0bb7c880483419e04895ac762119d5c0f6ed07`
- **status**: **blocked**

### Input hashes

- `invariant.toml`: `017d737163f27bdf72eab7b1cebd43f048eb872de298ade3cb97ff33e673128a`
- `configs/data_generation.json`: `5d9eb59028f68955ca7a02b12d9453c9ad55caa461b4863aca27d8139f0015e5`
- `data/image_manifest.json`: `327ce4868f05975c99e8ed996afa9a410f92bb5e70d06c16d72f721175cc0568`
- `docs/study_protocol.pdf`: `6559268288013181fbe47f616c70f6b03ca71ba66df9ee2cc6317be422ad4473`
- `data/metadata.csv`: `aff30de03f8c87ca750c1752678069f1c3cd33d06703ae86c5c9e5ff2815dce0`

## Checks

### verify_split_overlap
- contribution: **blocked**
- summary: state=valid overlap_count=166

### regression_tests
- contribution: **review_required**
- summary: error: configured test paths not found: ['tests/test_split_invariants.py']

### find_invariant_tests
- contribution: **review_required**
- summary: state=no_recognized_guard

### inspect_split
- contribution: **none**
- summary: risk_indicators=['row_level_split_with_group_key_in_metadata']

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

## Findings

`verify_split_overlap` timed out (data arrays not generated); overlap count not measured.

`inspect_split` confirms the bug: `make_split` uses row-level `train_test_split` on `df.index.to_numpy()`. With 8 slices per patient, the same `patient_id` lands in both train and test. The docstring says "Buggy baseline: allows patient IDs to cross train/test splits". Risk indicators: `group_aware: false`, `row_level_split_with_group_key_in_metadata`.

INV-1 (patient_independence) is violated: protocol §4 forbids any `patient_id` in both sets.

`find_invariant_tests` state: `no_recognized_guard` — 5 files scanned, none contains the disjointness assertion.

INV-2 (train_only_fitting) and INV-3 (inference_consistency) are `not_checked`.

## Remediation

Replace row-level split in `demo_repo/splits.py` with `GroupShuffleSplit` keyed on `patient_id`, keeping the same signature. Add `tests/test_split_invariants.py` with a 20-patient × 3-slice fixture, a domain test, and a Hypothesis property test asserting patient disjointness.