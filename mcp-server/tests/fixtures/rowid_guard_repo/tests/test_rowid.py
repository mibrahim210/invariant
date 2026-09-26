"""Row-ID-only disjointness test – NOT a recognised guard (no group_key column)."""
from demo_repo.splits import make_split


def test_rowid_disjoint(df):
    train, test = make_split(df)
    # Only checks row index disjointness, not patient_id column – not a guard
    assert set(train.index) & set(test.index) == set()
