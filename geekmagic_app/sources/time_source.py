"""
time_source.py - Returns a single DataItem with the current date and time.

Produces one item per call. The main window refreshes this source
every minute independently of the other sources.
"""

from datetime import datetime
from geekmagic_app.sources.base import DataSource
from geekmagic_app.models.data_item import DataItem


class TimeSource(DataSource):

    def fetch(self):
        return datetime.now()

    def parse(self, raw: datetime) -> list[DataItem]:
        now = raw
        # value = time in 12-hour format, e.g. "3:42 PM"
        time_str = now.strftime("%I:%M %p").lstrip("0")
        # subtitle = day of week spelled out
        day_str  = now.strftime("%A")
        # date line: "February 22, 2026" — %-d is Linux only, use lstrip on %d
        date_str = now.strftime("%B %d, %Y").replace(" 0", " ")

        return [DataItem(
            title    = date_str,
            subtitle = day_str,
            value    = time_str,
            date     = now,
            location = None,
            meta     = {"type": "time"},
        )]

    def get_items(self) -> list[DataItem]:
        return self.parse(self.fetch())
