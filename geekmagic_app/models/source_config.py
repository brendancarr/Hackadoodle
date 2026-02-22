"""
source_config.py - Data model for a configured source entry.

A SourceConfig describes everything needed to fetch and render
a source: what type it is, what parameters it needs, and which
template to render it with.

This is what gets saved to hackadoodle.json and displayed in
the sources list in the UI.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceConfig:
    """One entry in the source list."""
    type:     str          # "weather" | "ics" | "json"
    label:    str          # display name in the UI
    template: str          # template name (without .json)
    config:   dict = field(default_factory=dict)  # source-specific params

    # ── Factories ─────────────────────────────────────────────────────────────

    @classmethod
    def weather(cls, lat: float, lon: float, location: str,
                units: str = "celsius", max_days: int = 1,
                template: str = "weather_current") -> "SourceConfig":
        return cls(
            type     = "weather",
            label    = f"Weather \u2014 {location}",
            template = template,
            config   = {
                "lat":      lat,
                "lon":      lon,
                "location": location,
                "units":    units,
                "max_days": max_days,
            }
        )

    @classmethod
    def ics(cls, path: str, upcoming_only: bool = True, days_ahead: int = 2,
            label: str = "", template: str = "calendar_basic") -> "SourceConfig":
        return cls(
            type     = "ics",
            label    = label or f"Calendar \u2014 {path}",
            template = template,
            config   = {
                "path":          path,
                "upcoming_only": upcoming_only,
                "days_ahead":    days_ahead,
            }
        )

    @classmethod
    def time(cls, template: str = "clock") -> "SourceConfig":
        return cls(
            type     = "time",
            label    = "Current Time",
            template = template,
            config   = {},
        )

    @classmethod
    def json(cls, path: str, label: str = "",
             template: str = "calendar_basic") -> "SourceConfig":
        return cls(
            type     = "json",
            label    = label or f"JSON \u2014 {path}",
            template = template,
            config   = {"path": path}
        )

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":     self.type,
            "label":    self.label,
            "template": self.template,
            "config":   self.config,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SourceConfig":
        return cls(
            type     = d.get("type", "json"),
            label    = d.get("label", ""),
            template = d.get("template", "calendar_basic"),
            config   = d.get("config", {}),
        )

    def build_source(self):
        """Instantiate and return the appropriate DataSource object."""
        from geekmagic_app.sources.json_source import JsonSource
        from geekmagic_app.sources.ics_source import IcsSource
        from geekmagic_app.sources.weather_source import WeatherSource

        if self.type == "weather":
            return WeatherSource(
                lat      = self.config["lat"],
                lon      = self.config["lon"],
                location = self.config["location"],
                units    = self.config.get("units", "celsius"),
                max_days = self.config.get("max_days", 1),
            )
        elif self.type == "ics":
            return IcsSource(
                self.config["path"],
                upcoming_only=self.config.get("upcoming_only", True),
                days_ahead=self.config.get("days_ahead", 2),
            )
        elif self.type == "time":
            from geekmagic_app.sources.time_source import TimeSource
            return TimeSource()
        else:
            return JsonSource(self.config["path"])
