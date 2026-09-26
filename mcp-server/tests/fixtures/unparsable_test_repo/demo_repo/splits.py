"""Minimal split for unparsable_test_repo."""


def make_split(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]
