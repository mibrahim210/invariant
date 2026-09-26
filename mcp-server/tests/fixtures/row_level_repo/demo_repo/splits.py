"""Row-level split – no group awareness. Should trigger risk indicator."""
from sklearn.model_selection import train_test_split


def make_split(df):
    train, test = train_test_split(df, test_size=0.2, random_state=42)
    return train, test
