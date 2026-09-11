"""Calendar recurrences always refer back to their original anchor."""

from calendar import monthrange
from datetime import date


def add_months(anchor: date, months: int) -> date:
    index = anchor.year * 12 + anchor.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(anchor.day, monthrange(year, month)[1]))


def occurrence(anchor: date, months: int, end: date) -> date | None:
    """A bounded occurrence, including horizons near date.max."""
    if anchor.year * 12 + anchor.month + months > end.year * 12 + end.month:
        return None
    result = add_months(anchor, months)
    return result if result <= end else None


def period_bounds(anchor: date, on: date) -> tuple[date, date]:
    months = (on.year - anchor.year) * 12 + on.month - anchor.month
    if add_months(anchor, months) > on:
        months -= 1
    return add_months(anchor, months), add_months(anchor, months + 1)
