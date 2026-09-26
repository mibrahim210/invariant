"""Grouped split – uses GroupShuffleSplit. Should be group_aware=True."""
from sklearn.model_selection import GroupShuffleSplit


def make_split(df):
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(gss.split(df, groups=df["patient_id"]))
    return df.iloc[train_idx], df.iloc[test_idx]
