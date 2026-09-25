"""Reference patient-grouped split, used ONLY to measure Y before the review.

Committed in the invariant repository (reference/reference_splits.py), not in the demo
repository's history still contains only the buggy split until Bob's fix.
"""
from sklearn.model_selection import GroupShuffleSplit


def grouped_split(df, seed=0, test_size=0.2):
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(gss.split(df, groups=df["patient_id"]))
    return df.index[train_idx], df.index[test_idx]
