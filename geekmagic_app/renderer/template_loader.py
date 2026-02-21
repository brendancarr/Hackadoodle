"""
Template loader - reads and validates JSON template files.

A template file looks like:
{
    "name": "my_template",
    "background": "#000000",
    "zones": [
        {
            "field": "title",
            "x": 10, "y": 10,
            "font": "bold18",
            "color": "#ffffff",
            "filters": ["upper"],
            "max_width": 220
        }
    ]
}
"""

import json
from pathlib import Path
from dataclasses import dataclass, field


# ── Zone ─────────────────────────────────────────────────────────────────────

@dataclass
class Zone:
    field: str              # which DataItem field to render
    x: int                  # left edge (pixels)
    y: int                  # top edge (pixels)
    font: str = "regular14" # font key (resolved by renderer)
    color: str = "#ffffff"  # hex color string
    filters: list[str] = field(default_factory=list)  # e.g. ["upper", "truncate(20)"]
    max_width: int | None = None   # clip text to this pixel width
    align: str = "left"            # left | center | right
    line_height: int | None = None # for future multi-line support
    type: str = "text"             # text | weather_icon
    size: int | None = None        # for weather_icon: bounding box size

    @classmethod
    def from_dict(cls, d: dict) -> "Zone":
        return cls(
            field=d["field"],
            x=int(d.get("x", 0)),
            y=int(d.get("y", 0)),
            font=d.get("font", "regular14"),
            color=d.get("color", "#ffffff"),
            filters=d.get("filters", []),
            max_width=d.get("max_width"),
            align=d.get("align", "left"),
            line_height=d.get("line_height"),
            type=d.get("type", "text"),
            size=d.get("size"),
        )


# ── Template ──────────────────────────────────────────────────────────────────

@dataclass
class Template:
    name: str
    background: str = "#000000"  # hex color or path to bg image
    zones: list[Zone] = field(default_factory=list)
    width: int = 240
    height: int = 240

    @classmethod
    def from_dict(cls, d: dict) -> "Template":
        zones = [Zone.from_dict(z) for z in d.get("zones", [])]
        return cls(
            name=d.get("name", "unnamed"),
            background=d.get("background", "#000000"),
            zones=zones,
            width=int(d.get("width", 240)),
            height=int(d.get("height", 240)),
        )


# ── Loader ────────────────────────────────────────────────────────────────────

class TemplateLoader:
    """
    Loads template JSON files from a directory.
    Usage:
        loader = TemplateLoader("geekmagic_app/templates")
        t = loader.load("calendar_basic")
    """

    def __init__(self, templates_dir: str | Path):
        self.dir = Path(templates_dir)

    def load(self, name: str) -> Template:
        """Load a template by name (filename without .json)."""
        path = self.dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Template.from_dict(data)

    def load_from_file(self, path: str | Path) -> Template:
        """Load a template from an explicit file path."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Template.from_dict(data)

    def list_templates(self) -> list[str]:
        """Return names of all available templates."""
        return [p.stem for p in self.dir.glob("*.json")]
