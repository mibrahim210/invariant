"""Minimal split for rowid_guard_repo."""


def make_split(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]
