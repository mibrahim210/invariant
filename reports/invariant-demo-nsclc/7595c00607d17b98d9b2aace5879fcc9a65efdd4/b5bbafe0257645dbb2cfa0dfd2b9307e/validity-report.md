# Validity Report

## Binding

- **Repository**: `C:/Users/mdibr/Desktop/LabLab/IBM Bob Hackathon/ibm-bob2.0-hackathon-2026/invariant-demo-nsclc`
- **head_sha**: `7595c00607d17b98d9b2aace5879fcc9a65efdd4`
- **base_sha**: `7314aad4193a94a13b18df1b02b1b4921d1f3377` (source: invariant.toml)
- **run_id**: `b5bbafe0257645dbb2cfa0dfd2b9307e`
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

`verify_split_overlap` timed out on all three attempts (data arrays likely not generated at this commit), so the overlap count could not be measured directly.  
Static analysis (`inspect_split`) confirms the root cause: `make_split` calls `sklearn.model_selection.train_test_split` at the **row level** (`df.index.to_numpy()`).  
Because each patient contributes 8 slices, row-level splitting scatters those slices between train and test, placing the same `patient_id` in both partitions.  
The source file (`demo_repo/splits.py` line 9) has the docstring "**Buggy baseline: … allows patient IDs to cross train/test splits**" — the bug is self-documented.

**Risk indicators from inspect_split**  
- `group_aware: false` — the splitter has no knowledge of `patient_id`  
- `row_level_split_with_group_key_in_metadata` — rows, not patients, are the split unit  
- `stratify_col: label` — label-stratification is applied at the row level, not at the patient level

**INV-1 violation (patient_independence)**  
Protocol §4 requires *"No patient_id may appear in both the training set and the test set."*  
Row-level splitting with 8 slices per patient guarantees that patients appear in both sets for any reasonable `test_size`.

**find_invariant_tests**  
State: `no_recognized_guard` — none of the 5 scanned test files contains the required patient-disjointness assertion.

**Remaining protocol invariants not checked by this tool**  
- INV-2 `train_only_fitting` — not checked  
- INV-3 `inference_consistency` — not checked

## Remediation

## Remediation

Replace the row-level `train_test_split` in `demo_repo/splits.py` with `GroupShuffleSplit` keyed on `patient_id`.  
The function signature and return type (index labels) are unchanged; only the splitting strategy changes.

```python
from sklearn.model_selection import GroupShuffleSplit

def make_split(df, seed=0, test_size=0.2):
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_pos, test_pos = next(gss.split(df, groups=df["patient_id"]))
    return df.index[train_pos], df.index[test_pos]
```

Add `tests/test_split_invariants.py` with:
1. A fixed fixture of 20 patients × 3 slices each.
2. A domain test asserting no `patient_id` appears in both train and test index sets.
3. A Hypothesis property test over varied seeds and test sizes confirming the same invariant.