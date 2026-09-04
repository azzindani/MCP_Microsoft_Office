"""How many you got, out of how many. The three fields travel together.

A response that reports `returned` and `truncated` and stops there cannot be
read. `fs_index` with `action=list` returned exactly that shape:

    {"entries": [...], "returned": 50, "truncated": true,
     "hint": "Results capped at 50. Use action=query with a pattern to narrow"}

Fifty of fifty-one and fifty of seven hundred thousand are the same answer.
The caller cannot tell whether narrowing is worth a second call or whether it
already has everything that matters, and the hint tells it to narrow either
way. The number was one `COUNT(*)` away in a table the same function had open.

This is the third time the family has cost something. Round 22 found
`fs_query(content=)` reporting `total_found: 97` where grep found 489 and
added `total_found`, `scan_complete` and `total_found_is_lower_bound` to that
one tool. `resample_timeseries` in a sibling repo returned 20 of 25 periods
under `truncated: false`. `stats` in this very module has always reported
`entry_count`, so the repo does not disagree that the number is worth having --
`list` simply never got it.

The rule this module exists to make mechanical:

    a response carrying `returned` also carries `total` and `truncated`,
    and `truncated` is `returned < total`, never a separately-computed flag.

`truncated` computed independently of the two numbers is what allowed 20-of-25
to ship as complete. Here it cannot disagree with them, because it is derived
from them and there is no other way to build the field.

When the total is genuinely unknown -- a scan stopped early, a cursor with no
cheap count -- say so rather than omitting it. `exact=False` keeps the
denominator and marks it a floor, which is the shape round 22 arrived at
independently and the one a caller can still act on: "at least this many".
"""

from __future__ import annotations

from typing import Any

# The field a caller reads to learn the denominator is a floor, not a count.
LOWER_BOUND_FIELD = "total_is_lower_bound"


def counted(returned: int, total: int, *, exact: bool = True) -> dict[str, Any]:
    """The three count fields, with `truncated` derived rather than passed in.

    Merge into a result dict:

        result = {"success": True, "op": "fs_index", "entries": entries,
                  **counted(len(entries), total_under_root)}

    `exact=False` marks `total` a lower bound, for the case where counting the
    rest would cost as much as returning it.
    """
    returned = int(returned)
    total = int(total)
    if returned > total:
        # A returned count above the total means the two were measured against
        # different populations -- the bug this module is here to make loud,
        # so it is not quietly clamped.
        raise ValueError(
            f"returned ({returned}) exceeds total ({total}); "
            "the two counts were taken over different sets"
        )
    out: dict[str, Any] = {
        "returned": returned,
        "total": total,
        "truncated": returned < total,
    }
    if not exact:
        out[LOWER_BOUND_FIELD] = True
    return out


def count_violations(payload: dict[str, Any]) -> list[str]:
    """Contract breaches in one response dict. Empty list means it holds.

    For tests and for the smoke script -- the check has to run against a real
    response, because the shape is only wrong once a tool has built it.
    """
    problems: list[str] = []
    if "returned" not in payload:
        return problems

    if "total" not in payload:
        problems.append("has `returned` but no `total`: the denominator is missing")
    if "truncated" not in payload:
        problems.append("has `returned` but no `truncated`")

    if "total" in payload and "truncated" in payload:
        returned, total = payload["returned"], payload["total"]
        if isinstance(returned, int) and isinstance(total, int):
            if returned > total:
                problems.append(f"returned ({returned}) exceeds total ({total})")
            expected = returned < total
            if bool(payload["truncated"]) is not expected:
                problems.append(
                    f"truncated is {payload['truncated']!r} but returned={returned} "
                    f"and total={total} say it should be {expected!r}"
                )
    return problems
