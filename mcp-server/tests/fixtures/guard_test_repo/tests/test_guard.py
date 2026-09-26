"""Patient-disjointness guard test – recognised guard."""
from demo_repo.splits import make_split


def test_patient_disjoint(df):
    train, test = make_split(df)
    assert set(df.loc[train.index, "patient_id"]) & set(df.loc[test.index, "patient_id"]) == set()
