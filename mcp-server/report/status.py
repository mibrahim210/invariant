"""Status derivation for the Validity Report.

All logic is pure: given a mapping of check_name -> result_dict, compute the
per-check contribution and the aggregate status.

Precedence: blocked > review_required > no_findings.
"""
from __future__ import annotations

_REQUIRED_CHECKS = [
    "verify_split_overlap",
    "regression_tests",
    "find_invariant_tests",
    "inspect_split",
]

# The overlap_count from verify_split_overlap (if known) is needed by inspect_split.
_SENTINEL_OVERLAP = object()


def check_contribution(check_name: str, result: dict, overlap_count) -> str:
    """Return 'blocked', 'review_required', or 'none' for a single check result.

    overlap_count: the validated overlap_count from verify_split_overlap (int or None),
                   or _SENTINEL_OVERLAP when it hasn't been resolved yet.
    """
    if result is None:
        return "review_required"   # S16: missing
    if "error" in result:
        return "review_required"   # S18: exception / error key
    state = result.get("state")

    if check_name == "verify_split_overlap":
        # S1/S2: invalid partition -> blocked
        if state == "invalid_partition":
            return "blocked"
        # S3: valid partition but groups overlap -> blocked
        if state == "valid":
            cnt = result.get("overlap_count")
            if cnt is not None and cnt > 0:
                return "blocked"
            if cnt == 0:
                return "none"   # S4
        # S5: error or anything else -> review_required
        return "review_required"

    if check_name == "regression_tests":
        if state == "failed":
            return "blocked"        # S6
        if state == "passed":
            collected = result.get("collected", 0)
            if collected and collected > 0:
                return "none"       # S8
            return "review_required"  # S9 (passed but zero collected)
        # no_tests, collection_error, crash -> review_required  (S7, S9)
        return "review_required"

    if check_name == "find_invariant_tests":
        if state == "recognized_guard":
            return "none"           # S10
        return "review_required"    # S11, S12

    if check_name == "inspect_split":
        risk = result.get("risk_indicators", [])
        if not risk:
            return "none"           # S15
        # S13: risk present, overlap == 0 -> review_required
        # S14: risk present, overlap > 0 -> none from this row (S3 already blocks)
        if isinstance(overlap_count, int) and overlap_count > 0:
            return "none"           # S14
        return "review_required"    # S13

    # Unknown check name: treat as review_required
    return "review_required"


def derive_status(results: dict) -> tuple[str, dict[str, str]]:
    """Derive aggregate status and per-check contributions.

    results: {check_name: result_dict | None}

    Returns:
        status: 'blocked' | 'review_required' | 'no_findings'
        contributions: {check_name: contribution_str}
    """
    # Extract overlap_count from verify_split_overlap result first.
    overlap_result = results.get("verify_split_overlap")
    if overlap_result and "error" not in overlap_result and overlap_result.get("state") == "valid":
        overlap_count: int | None = overlap_result.get("overlap_count")
    else:
        overlap_count = None

    contributions: dict[str, str] = {}
    for name in _REQUIRED_CHECKS:
        result = results.get(name)
        contributions[name] = check_contribution(name, result, overlap_count)

    # Precedence: blocked > review_required > no_findings
    if any(c == "blocked" for c in contributions.values()):
        status = "blocked"
    elif any(c == "review_required" for c in contributions.values()):
        status = "review_required"
    else:
        status = "no_findings"

    return status, contributions


def required_checks() -> list[str]:
    return list(_REQUIRED_CHECKS)
