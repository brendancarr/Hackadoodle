"""
ics_source.py - Loads DataItems from an ICS calendar (URL or local file).

ICS (iCalendar) is the standard format used by:
    Google Calendar, Apple Calendar, Outlook, Nextcloud, etc.

Each VEVENT in the calendar becomes one DataItem:
    title    ← SUMMARY
    subtitle ← DESCRIPTION (first line only, cleaned up)
    date     ← DTSTART
    location ← LOCATION
    value    ← formatted time string e.g. "2:30 PM" or "All day"
    meta     ← uid, dtend, organizer, url, status, and anything else

FILTERING:
    By default, all events are returned sorted by start date.
    Use max_items to cap the list (e.g. "next 5 events").
    Use upcoming_only=True to skip events that have already passed.

Usage:
    # From a local file
    source = IcsSource("sample_data/calendar.ics")

    # From a URL (Google Calendar public ICS link, etc.)
    source = IcsSource("https://calendar.google.com/calendar/ical/.../basic.ics")

    # Next 3 upcoming events only
    source = IcsSource("sample_data/calendar.ics", upcoming_only=True, max_items=3)

    items = source.get_items()
"""

import requests
from pathlib import Path
from datetime import datetime, date, timezone, timedelta

from icalendar import Calendar, vDatetime, vDate, vText, vGeo
from geekmagic_app.sources.base import DataSource
from geekmagic_app.models.data_item import DataItem


class IcsSource(DataSource):
    """
    Loads DataItems from an ICS calendar file or URL.

    Args:
        url_or_path:    HTTP/HTTPS URL or local file path.
        upcoming_only:  If True, skip events whose start is in the past.
        max_items:      Cap on number of items returned (None = no limit).
        timeout:        HTTP request timeout in seconds.
        headers:        Optional HTTP headers dict.
    """

    def __init__(
        self,
        url_or_path: str,
        upcoming_only: bool = False,
        days_ahead: int | None = None,
        max_items: int | None = None,
        timeout: int = 10,
        headers: dict[str, str] | None = None,
    ):
        self.url_or_path   = url_or_path
        self.upcoming_only = upcoming_only
        self.days_ahead    = days_ahead   # None = no limit, 1 = today, 2 = today+tomorrow
        self.max_items     = max_items
        self.timeout       = timeout
        self.headers       = headers or {}

    # ── DataSource interface ──────────────────────────────────────────────────

    def fetch(self) -> bytes:
        """Returns raw ICS bytes. Raises on network/IO error."""
        target = self.url_or_path.strip()
        if target.startswith("http://") or target.startswith("https://"):
            return self._fetch_url(target)
        else:
            return self._fetch_file(target)

    def parse(self, raw: bytes) -> list[DataItem]:
        """
        Parse raw ICS bytes into a sorted list of DataItems.
        Never raises — returns empty list on failure.
        """
        try:
            cal = Calendar.from_ical(raw)
        except Exception as e:
            print(f"[IcsSource] Failed to parse ICS: {e}")
            return []

        items = []
        now = datetime.now(tz=timezone.utc)

        # Cutoff = end of the Nth day from today (midnight at end of that day)
        if self.days_ahead is not None:
            cutoff = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                      + timedelta(days=self.days_ahead))
        else:
            cutoff = None

        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            try:
                item = self._parse_event(component)
                if item is None:
                    continue

                event_dt = self._as_datetime(component.get("DTSTART"))

                # Filter past events if requested
                if self.upcoming_only and event_dt and event_dt < now:
                    continue

                # Filter events beyond days_ahead window
                if cutoff and event_dt and event_dt >= cutoff:
                    continue

                items.append(item)
            except Exception as e:
                print(f"[IcsSource] Skipping event: {e}")
                continue

        # Sort by date ascending
        items.sort(key=lambda x: self._sort_key(x.date))

        # Cap if requested
        if self.max_items is not None:
            items = items[: self.max_items]

        return items

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_url(self, url: str) -> bytes:
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def _fetch_file(self, path: str) -> bytes:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"ICS file not found: {p.resolve()}")
        return p.read_bytes()

    def _parse_event(self, component) -> DataItem | None:
        """Convert a single VEVENT component into a DataItem."""

        # SUMMARY → title
        summary = component.get("SUMMARY")
        title = self._to_str(summary) if summary else "(No title)"

        # DESCRIPTION → subtitle (first line, stripped)
        description = component.get("DESCRIPTION")
        subtitle = ""
        if description:
            raw_desc = self._to_str(description)
            subtitle = raw_desc.strip().split("\n")[0].strip()
            # Clean up escaped characters common in ICS descriptions
            subtitle = subtitle.replace("\\n", " ").replace("\\,", ",").strip()

        # DTSTART → date (keep as datetime if possible)
        dtstart = component.get("DTSTART")
        dt = self._as_datetime(dtstart) if dtstart else None

        # value → human-readable time string
        value = self._format_time(dtstart) if dtstart else ""

        # LOCATION
        location_raw = component.get("LOCATION")
        location = self._to_str(location_raw).strip() if location_raw else None

        # META — everything else worth keeping
        meta = {}
        for key in ("UID", "DTEND", "ORGANIZER", "URL", "STATUS", "RRULE"):
            val = component.get(key)
            if val is not None:
                meta[key.lower()] = self._to_str(val)

        return DataItem(
            title=title,
            subtitle=subtitle,
            value=value,
            date=dt,
            location=location,
            meta=meta,
        )

    def _to_str(self, val) -> str:
        """Safely convert an icalendar value type to a plain string."""
        if val is None:
            return ""
        if isinstance(val, (vText,)):
            return str(val)
        if hasattr(val, "to_ical"):
            return val.to_ical().decode("utf-8", errors="replace")
        return str(val)

    def _as_datetime(self, dtstart) -> datetime | None:
        """
        Convert a DTSTART value to a timezone-aware datetime.
        Handles: datetime with tz, datetime without tz, date-only.
        """
        if dtstart is None:
            return None

        dt = dtstart.dt  # icalendar unwraps the value with .dt

        if isinstance(dt, datetime):
            # Make timezone-aware if naive
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        if isinstance(dt, date):
            # All-day event: treat as midnight UTC on that date
            return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)

        return None

    def _format_time(self, dtstart) -> str:
        """
        Format DTSTART as a readable time string.
        All-day events → "All day"
        Timed events   → "2:30 PM"
        """
        if dtstart is None:
            return ""
        dt = dtstart.dt
        if isinstance(dt, date) and not isinstance(dt, datetime):
            return "All day"
        if isinstance(dt, datetime):
            # Format as 12-hour time without leading zero
            return dt.strftime("%I:%M %p").lstrip("0")
        return ""

    def _sort_key(self, date_val) -> datetime:
        """Return a sortable datetime for any date/datetime/string/None."""
        if isinstance(date_val, datetime):
            if date_val.tzinfo is None:
                return date_val.replace(tzinfo=timezone.utc)
            return date_val
        if isinstance(date_val, date):
            return datetime(date_val.year, date_val.month, date_val.day, tzinfo=timezone.utc)
        # Fallback: sort unknowns to the end
        return datetime(9999, 12, 31, tzinfo=timezone.utc)
