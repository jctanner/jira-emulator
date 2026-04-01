"""JQL built-in function implementations.

Provides ``resolve_function(name, args, current_username)`` which maps JQL
function calls such as ``currentUser()``, ``now()``, ``startOfDay()`` etc.
to concrete Python values that the transformer can embed in SQL clauses.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, date, time


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def resolve_function(
    name: str,
    args: list,
    current_username: str | None = None,
):
    """Resolve a JQL function call to a Python value.

    Parameters
    ----------
    name:
        Function name (case-insensitive).
    args:
        List of already-resolved argument values (strings, numbers, etc.).
    current_username:
        The username of the currently authenticated user, used by
        ``currentUser()``.

    Returns
    -------
    The resolved value — typically a ``str`` or ``datetime``.

    Raises
    ------
    ValueError
        If the function name is unknown or argument validation fails.
    """
    fn_name = name.lower().rstrip("(").strip()
    fn_map = {
        "currentuser": _current_user,
        "now": _now,
        "startofday": _start_of_day,
        "endofday": _end_of_day,
        "startofweek": _start_of_week,
        "endofweek": _end_of_week,
        "startofmonth": _start_of_month,
        "endofmonth": _end_of_month,
        "startofyear": _start_of_year,
        "endofyear": _end_of_year,
    }

    handler = fn_map.get(fn_name)
    if handler is None:
        raise ValueError(f"Unknown JQL function: {name}()")

    if fn_name == "currentuser":
        return handler(current_username)

    # Date/time functions accept an optional offset argument
    offset = args[0] if args else None
    return handler(offset)


# ---------------------------------------------------------------------------
# Function implementations
# ---------------------------------------------------------------------------

def _current_user(current_username: str | None) -> str:
    if current_username is None:
        raise ValueError("currentUser() requires an authenticated user")
    return current_username


def _now(_offset=None) -> datetime:
    return datetime.utcnow()


def _start_of_day(offset: str | None = None) -> datetime:
    base = datetime.combine(date.today(), time.min)
    if offset is not None:
        base += _parse_offset(offset)
    return datetime.combine(base.date(), time.min)


def _end_of_day(offset: str | None = None) -> datetime:
    base = datetime.combine(date.today(), time.max)
    if offset is not None:
        base += _parse_offset(offset)
    return datetime.combine(base.date(), time(23, 59, 59))


def _start_of_week(offset: str | None = None) -> datetime:
    today = date.today()
    # ISO weekday: Monday == 1
    start = today - timedelta(days=today.weekday())
    base = datetime.combine(start, time.min)
    if offset is not None:
        base += _parse_offset(offset)
        # Re-snap to start of that week
        base = datetime.combine(
            (base.date() - timedelta(days=base.date().weekday())), time.min
        )
    return base


def _end_of_week(offset: str | None = None) -> datetime:
    today = date.today()
    end = today + timedelta(days=(6 - today.weekday()))
    base = datetime.combine(end, time(23, 59, 59))
    if offset is not None:
        base += _parse_offset(offset)
        # Re-snap to end of that week
        base = datetime.combine(
            (base.date() + timedelta(days=(6 - base.date().weekday()))),
            time(23, 59, 59),
        )
    return base


def _start_of_month(offset: str | None = None) -> datetime:
    today = date.today()
    base = datetime.combine(today.replace(day=1), time.min)
    if offset is not None:
        base += _parse_offset(offset)
        base = datetime.combine(base.date().replace(day=1), time.min)
    return base


def _end_of_month(offset: str | None = None) -> datetime:
    today = date.today()
    base = datetime.combine(today, time.max)
    if offset is not None:
        base += _parse_offset(offset)
    # Snap to last day of the month
    month = base.month
    year = base.year
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    return datetime.combine(last_day, time(23, 59, 59))


def _start_of_year(offset: str | None = None) -> datetime:
    today = date.today()
    base = datetime.combine(date(today.year, 1, 1), time.min)
    if offset is not None:
        base += _parse_offset(offset)
        base = datetime.combine(date(base.year, 1, 1), time.min)
    return base


def _end_of_year(offset: str | None = None) -> datetime:
    today = date.today()
    base = datetime.combine(date(today.year, 12, 31), time(23, 59, 59))
    if offset is not None:
        base += _parse_offset(offset)
        base = datetime.combine(date(base.year, 12, 31), time(23, 59, 59))
    return base


# ---------------------------------------------------------------------------
# Offset parser
# ---------------------------------------------------------------------------

_OFFSET_RE = re.compile(r"^([+-]?\d+)\s*([dwMyhms])$")


def _parse_offset(offset_str: str) -> timedelta:
    """Parse JQL offset strings like ``"-1d"``, ``"2w"``, ``"3M"``.

    Supported units:

    - ``d`` — days
    - ``w`` — weeks
    - ``M`` — months (approximated as 30 days)
    - ``y`` — years (approximated as 365 days)
    - ``h`` — hours
    - ``m`` — minutes
    - ``s`` — seconds

    Returns a ``timedelta``.
    """
    # Strip surrounding quotes if present
    cleaned = str(offset_str).strip().strip("'\"")
    match = _OFFSET_RE.match(cleaned)
    if not match:
        raise ValueError(
            f"Invalid offset format: '{offset_str}'. "
            "Expected a string like '-1d', '2w', '3M'."
        )

    amount = int(match.group(1))
    unit = match.group(2)

    unit_map = {
        "s": timedelta(seconds=1),
        "m": timedelta(minutes=1),
        "h": timedelta(hours=1),
        "d": timedelta(days=1),
        "w": timedelta(weeks=1),
        "M": timedelta(days=30),
        "y": timedelta(days=365),
    }

    return amount * unit_map[unit]
