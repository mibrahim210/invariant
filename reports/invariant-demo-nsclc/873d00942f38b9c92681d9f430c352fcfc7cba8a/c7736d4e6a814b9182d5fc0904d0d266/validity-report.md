# Validity Report

## Binding

- **Repository**: `C:/Users/mdibr/Desktop/LabLab/IBM Bob Hackathon/ibm-bob2.0-hackathon-2026/invariant-demo-nsclc`
- **head_sha**: `873d00942f38b9c92681d9f430c352fcfc7cba8a`
- **base_sha**: `e739727886a3dd69a2c2733a97877754a0cfee28` (source: invariant.toml)
- **run_id**: `c7736d4e6a814b9182d5fc0904d0d266`
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

## Finding: Patient-level train/test leakage — INV-1 violated

`demo_repo/splits.py:make_split` calls `sklearn.model_selection.train_test_split` at the **row level** without grouping by `patient_id`. Because each patient contributes 8 slices, rows from the same patient are independently assigned to train or test, so a patient can (and does) appear in both partitions.

`verify_split_overlap` (seed 0, 1 600 rows, 200 patients) measured **overlap_count = 166**: 166 of the 200 patients have slices in both the training set and the test set. Example overlapping patients: NSCLC_P001, NSCLC_P002, NSCLC_P003, NSCLC_P004, NSCLC_P005.

The persistent patient texture engineered into the synthetic images (see protocol §3) means the model can memorise per-patient appearance from training slices and transfer that signal to the test slices of the same patient, inflating the reported ROC AUC.

`find_invariant_tests` returned `no_recognized_guard`: no test in tests/ asserts disjoint patient sets between train and test, so the defect has been undetected.

`inspect_split` confirms `group_aware=false` and risk indicator `row_level_split_with_group_key_in_metadata`.

INV-2 (train_only_fitting) and INV-3 (inference_consistency) are **not_checked** in this review.

## Remediation

## Remediation

Replace `train_test_split` with `GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)` grouped on the `patient_id` column. This ensures every patient's slices appear in exactly one partition.

Concrete change in `demo_repo/splits.py`:

```python
from sklearn.model_selection import GroupShuffleSplit

def make_split(df, seed, test_size=0.2):
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(gss.split(df, groups=df["patient_id"]))
    return df.index[train_idx], df.index[test_idx]
```

Add `tests/test_split_invariants.py` with:
1. A fixed fixture of 20 patients × 3 slices each (60 rows).
2. A domain test asserting that the patient sets of the two returned index arrays are disjoint.
3. A Hypothesis property test over variable patient counts and test sizes that asserts the same disjointness property.