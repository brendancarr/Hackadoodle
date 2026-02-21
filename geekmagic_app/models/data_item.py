"""
DataItem model - the standard data structure passed between
sources, templates, and the renderer.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DataItem:
    title: str = ""
    subtitle: str = ""
    value: str = ""
    date: datetime | str | None = None
    image: str | None = None
    location: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def get(self, field_name: str, fallback: str = ""):
        """
        Retrieve a field value.
        Returns the raw value for date fields (so filters can work with
        the actual datetime object), str for everything else.
        Returns fallback if the field is missing or None.
        """
        val = getattr(self, field_name, None)
        if val is None:
            val = self.meta.get(field_name, None)
        if val is None:
            return fallback
        # Return datetime objects as-is so date_short filter works correctly
        if isinstance(val, datetime):
            return val
        return str(val)

    @classmethod
    def from_dict(cls, d: dict) -> "DataItem":
        """Build a DataItem from a plain dictionary (e.g. from JSON source)."""
        known = {f for f in cls.__dataclass_fields__}
        meta = {k: v for k, v in d.items() if k not in known}
        base = {k: v for k, v in d.items() if k in known}
        return cls(**base, meta={**meta, **d.get("meta", {})})
