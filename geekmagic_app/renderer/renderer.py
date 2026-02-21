"""
Renderer - converts a Template + DataItem → 240×240 PIL Image (PNG).

Usage:
    renderer = Renderer(fonts_dir="geekmagic_app/fonts")
    img = renderer.render(template, data_item)
    img.save("preview.png")
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from geekmagic_app.renderer.weather_icons import draw_weather_icon
from geekmagic_app.renderer.template_loader import Template, Zone
from geekmagic_app.models.data_item import DataItem
from geekmagic_app.renderer.filters import apply_filters


# ── Font registry ─────────────────────────────────────────────────────────────

# Built-in fallback sizes when no TTF fonts are installed.
# Maps "bold18" → (style_hint, size)
FONT_ALIASES: dict[str, tuple[str, int]] = {
    "regular10": ("regular", 10),
    "regular12": ("regular", 12),
    "regular14": ("regular", 14),
    "regular16": ("regular", 16),
    "regular18": ("regular", 18),
    "regular24": ("regular", 24),
    "regular32": ("regular", 32),
    "bold10": ("bold", 10),
    "bold12": ("bold", 12),
    "bold14": ("bold", 14),
    "bold16": ("bold", 16),
    "bold18": ("bold", 18),
    "bold24": ("bold", 24),
    "bold32": ("bold", 32),
    "bold48": ("bold", 48),
}


class FontRegistry:
    """
    Loads and caches PIL fonts.
    Looks for TTF files in the fonts_dir first.
    Falls back to PIL's built-in bitmap font if no TTF found.

    Naming convention for TTF files:
        regular.ttf   → all "regular" aliases
        bold.ttf      → all "bold" aliases
    Or explicit files:
        bold18.ttf    → exact alias match
    """

    def __init__(self, fonts_dir: str | Path):
        self.dir = Path(fonts_dir)
        self._cache: dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

    def get(self, alias: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if alias in self._cache:
            return self._cache[alias]

        font = self._load(alias)
        self._cache[alias] = font
        return font

    def _load(self, alias: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        style, size = FONT_ALIASES.get(alias, ("regular", 14))

        # 1. Exact match: bold18.ttf
        exact = self.dir / f"{alias}.ttf"
        if exact.exists():
            return ImageFont.truetype(str(exact), size)

        # 2. Style match: bold.ttf or regular.ttf
        style_file = self.dir / f"{style}.ttf"
        if style_file.exists():
            return ImageFont.truetype(str(style_file), size)

        # 3. Any .ttf in folder (just grab the first one)
        ttf_files = list(self.dir.glob("*.ttf"))
        if ttf_files:
            return ImageFont.truetype(str(ttf_files[0]), size)

        # 4. PIL built-in fallback (tiny bitmap, always works)
        return ImageFont.load_default()


# ── Color helpers ─────────────────────────────────────────────────────────────

def _parse_color(color: str) -> tuple[int, int, int]:
    """Parse a hex color like '#ff0000' → (255, 0, 0)."""
    color = color.strip().lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    return (r, g, b)


# ── Renderer ──────────────────────────────────────────────────────────────────

class Renderer:
    def __init__(self, fonts_dir: str | Path = "geekmagic_app/fonts"):
        self.fonts = FontRegistry(fonts_dir)

    def render(self, template: Template, item: DataItem) -> Image.Image:
        """
        Render a DataItem using a Template.
        Returns a PIL Image (mode=RGB, size=template.width×template.height).
        """
        img = self._make_background(template)
        draw = ImageDraw.Draw(img)

        for zone in template.zones:
            try:
                self._draw_zone(img, draw, zone, item, template.width)
            except Exception as e:
                print(f"[renderer] Zone '{zone.field}' error: {e}")

        return img

    def render_to_file(self, template: Template, item: DataItem, path: str | Path) -> None:
        """Render and save directly to a PNG file."""
        img = self.render(template, item)
        img.save(str(path), format="PNG")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_background(self, template: Template) -> Image.Image:
        bg = template.background.strip()

        # Background image path?
        if not bg.startswith("#"):
            bg_path = Path(bg)
            if bg_path.exists():
                img = Image.open(bg_path).convert("RGB")
                img = img.resize((template.width, template.height), Image.LANCZOS)
                return img

        # Solid color (default)
        try:
            color = _parse_color(bg)
        except Exception:
            color = (0, 0, 0)
        return Image.new("RGB", (template.width, template.height), color)

    def _draw_zone(self, img: Image.Image, draw: ImageDraw.Draw, zone: Zone, item: DataItem, canvas_width: int) -> None:
        # Handle weather icon zones separately — they draw shapes, not text
        if zone.type == "weather_icon":
            raw = item.meta.get("wmo_code", 0)
            try:
                wmo_code = int(raw)
            except (ValueError, TypeError):
                wmo_code = 0
            size = zone.size or 64
            draw_weather_icon(img, wmo_code, zone.x, zone.y, size)
            return

        # 1. Get raw value from data item
        # Support dot-notation for meta fields e.g. "meta.wind"
        if "." in zone.field:
            parts = zone.field.split(".", 1)
            if parts[0] == "meta":
                raw = str(item.meta.get(parts[1], ""))
            else:
                raw = item.get(zone.field)
        else:
            raw = item.get(zone.field)

        # 2. Apply filters
        text = apply_filters(raw, zone.filters)

        # 3. Skip empty
        if not text:
            return

        # 4. Get font
        font = self.fonts.get(zone.font)

        # 5. Truncate to max_width if needed
        if zone.max_width:
            text = self._fit_text(draw, text, font, zone.max_width)

        # 6. Resolve x for alignment
        x = zone.x
        if zone.align in ("center", "right"):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            if zone.align == "center":
                max_w = zone.max_width or canvas_width
                x = zone.x + (max_w - text_w) // 2
            else:  # right
                max_w = zone.max_width or canvas_width
                x = zone.x + max_w - text_w

        # 7. Parse color
        try:
            color = _parse_color(zone.color)
        except Exception:
            color = (255, 255, 255)

        # 8. Draw
        draw.text((x, zone.y), text, font=font, fill=color)

    def _fit_text(self, draw: ImageDraw.Draw, text: str, font, max_width: int) -> str:
        """Trim text until it fits within max_width pixels. Appends ellipsis."""
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return text

        # Binary-chop would be faster but this is clear and good enough for 240px
        for i in range(len(text), 0, -1):
            candidate = text[:i] + "…"
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return candidate

        return "…"
