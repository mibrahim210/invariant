"""Split via groups= keyword argument only (no named group-aware class)."""
from sklearn.model_selection import StratifiedKFold


def make_split(df, groups=None):
    skf = StratifiedKFold(n_splits=5)
    train_idx, test_idx = next(skf.split(df, df["label"], groups=df["patient_id"]))
    return df.iloc[train_idx], df.iloc[test_idx]
