"""
Filters - text transformation functions applied to field values before rendering.

Filter strings in templates can be:
  - "upper"
  - "lower"
  - "date_short"
  - "currency"
  - "truncate(20)"   ← with argument in parens

Usage:
    from renderer.filters import apply_filters
    result = apply_filters("hello world", ["upper", "truncate(5)"])
    # → "HELLO"
"""

import re
from datetime import datetime


# ── Individual filters ────────────────────────────────────────────────────────

def filter_upper(value: str, _=None) -> str:
    return value.upper()


def filter_lower(value: str, _=None) -> str:
    return value.lower()


def filter_truncate(value: str, arg: str | None = None) -> str:
    n = int(arg) if arg else 30
    return value[:n] + ("…" if len(value) > n else "")


def filter_date_short(value: str, _=None) -> str:
    """Parse common date formats and render as e.g. 'Feb 21'."""
    import sys
    
    # Handle datetime objects passed directly
    if isinstance(value, datetime):
        return value.strftime("%b %-d" if sys.platform != "win32" else "%b %#d")
    
    # Handle stringified datetimes (e.g. from DataItem.get())
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    # Strip timezone suffix that strptime can't always handle
    clean = value.strip()

    for fmt in formats: #not working
        try:
            dt = datetime.strptime(clean, fmt)
            
            return dt.strftime("%b %-d" if sys.platform != "win32" else "%b %#d")
        except (ValueError, AttributeError):
            continue
    return value  # give up, return as-is


def filter_currency(value: str, _=None) -> str:
    """Format a numeric string as currency: 1234.5 → $1,234.50"""
    try:
        f = float(value.replace(",", "").replace("$", ""))
        return f"${f:,.2f}"
    except ValueError:
        return value


# ── Registry & dispatcher ────────────────────────────────────────────────────

FILTER_MAP = {
    "upper": filter_upper,
    "lower": filter_lower,
    "truncate": filter_truncate,
    "date_short": filter_date_short,
    "currency": filter_currency,
}

_FILTER_RE = re.compile(r"^(\w+)(?:\((.+)\))?$")


def apply_filters(value: str, filters: list[str]) -> str:
    """
    Apply a list of filter strings to a value in order.
    Unknown filters are silently skipped.
    """
    for f_str in filters:
        m = _FILTER_RE.match(f_str.strip())
        if not m:
            continue
        name, arg = m.group(1), m.group(2)
        fn = FILTER_MAP.get(name)
        if fn:
            value = fn(value, arg)
    return value
