"""Eating occasions — collapsing one meal logged in several messages.

A plate and the things that follow it are one meal, but they arrive as separate
WhatsApp messages: pizza at 21:00 and the yogurt at 21:15, or a plate at 14:00
and whatever else gets added at 14:20. Each message becomes its own `meals`
row, so meal_count counted submissions rather than meals, and the weekly coach
report said "5 ארוחות" for a day that had four.

The 20-minute threshold is not a round number, it came out of the data.
Across 151 consecutive same-day pairs:

    <= 5 min   34 pairs     <- the cluster: one meal, logged in pieces
    5-10 min   10
    10-15 min   8
    15-20 min   1           <- the valley
    20-25 min   2
    25-30 min   4
    30-35 min   5

52 pairs land inside 15 minutes, then almost nothing until 25. Cutting at 20
takes the whole cluster and stops inside the gap.

Deliberately NOT also requiring the same meal_type: 5 of the 34 sub-5-minute
pairs have different types, because detect_meal_type() is purely hour-based
with boundaries at 11:00 / 15:00 / 18:00 / 23:00. A plate at 14:58 is "lunch"
and the extras at 15:02 are "snack". Those boundaries sit exactly when people
eat, so matching on type would re-split the very cases this joins.

Nothing here merges or deletes rows. The meals table stays a faithful log of
what was actually submitted — both photos are kept, /undo is unaffected, and
changing MEAL_GAP_MINUTES re-groups history on the next recompute.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

MEAL_GAP_MINUTES = 20


def _as_dt(value: Any) -> datetime | None:
    """Parse a Supabase timestamp into an aware UTC datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def count_eating_occasions(
    timestamps: Iterable[Any], gap_minutes: int = MEAL_GAP_MINUTES
) -> int:
    """How many distinct meals a set of logged timestamps represents.

    Consecutive logs closer together than `gap_minutes` belong to the same
    occasion. Unparseable timestamps are ignored rather than counted, so a bad
    row cannot silently inflate the number.
    """
    seen = sorted(dt for dt in (_as_dt(t) for t in timestamps) if dt is not None)
    if not seen:
        return 0
    gap = gap_minutes * 60
    occasions = 1
    for prev, cur in zip(seen, seen[1:]):
        if (cur - prev).total_seconds() > gap:
            occasions += 1
    return occasions


def assign_eating_occasions(
    rows: list[dict],
    ts_key: str = "eaten_at",
    gap_minutes: int = MEAL_GAP_MINUTES,
) -> list[dict]:
    """Copy of `rows`, sorted by time, each tagged with a 1-based `occasion`.

    The coach prompt is given both the per-day meal_count and the raw meal
    rows. If meal_count said 4 while the list showed 5 rows, the model would
    have two contradictory facts and would reconcile them by inventing an
    explanation — which is exactly how an earlier bug produced a report
    accusing the user of not logging a run he had logged. Tagging the rows
    makes the relationship explicit instead of leaving it to be guessed.

    Rows with an unparseable timestamp keep occasion=None and sort last.
    """
    decorated = [(_as_dt(r.get(ts_key)), r) for r in rows]
    parsed = sorted((d for d in decorated if d[0] is not None), key=lambda d: d[0])
    unparsed = [d for d in decorated if d[0] is None]

    out: list[dict] = []
    gap = gap_minutes * 60
    occasion = 0
    prev: datetime | None = None
    for dt, row in parsed:
        if prev is None or (dt - prev).total_seconds() > gap:
            occasion += 1
        out.append({**row, "occasion": occasion})
        prev = dt
    out.extend({**row, "occasion": None} for _, row in unparsed)
    return out
