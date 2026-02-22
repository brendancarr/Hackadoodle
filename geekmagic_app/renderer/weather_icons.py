"""
weather_icons.py - Draws simple geometric weather icons using PIL.

Each icon is drawn into a bounding box on the image.
No fonts, no emoji, no external files — pure PIL shapes.

Usage:
    from geekmagic_app.renderer.weather_icons import draw_weather_icon
    draw_weather_icon(img, wmo_code=63, x=160, y=60, size=60)
"""

from PIL import Image, ImageDraw
import math


# ── Colour palette ────────────────────────────────────────────────────────────

SUN_COLOUR    = "#FFD700"
CLOUD_COLOUR  = "#CCDDEE"
RAIN_COLOUR   = "#4fc3f7"
SNOW_COLOUR   = "#FFFFFF"
STORM_COLOUR  = "#FFD700"
FOG_COLOUR    = "#889aaa"


# ── Primitive helpers ─────────────────────────────────────────────────────────

def _circle(draw, cx, cy, r, fill, outline=None):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline)


def _cloud(draw, cx, cy, w, h, colour):
    """Draw a simple 3-bump cloud shape."""
    # Main body
    bx = cx - w // 2
    by = cy - h // 4
    draw.ellipse([bx, by, bx + w, by + h // 2], fill=colour)
    # Left bump
    _circle(draw, bx + w // 4, by, h // 3, colour)
    # Centre bump (tallest)
    _circle(draw, bx + w // 2, by - h // 6, h // 2 - 2, colour)
    # Right bump
    _circle(draw, bx + 3 * w // 4, by, h // 3, colour)


def _sun(draw, cx, cy, r, colour):
    """Draw a sun: circle + rays."""
    ray_len = r // 2
    ray_r   = max(1, r // 8)
    # Rays
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = cx + int((r + 2) * math.cos(rad))
        y1 = cy + int((r + 2) * math.sin(rad))
        x2 = cx + int((r + ray_len) * math.cos(rad))
        y2 = cy + int((r + ray_len) * math.sin(rad))
        draw.line([x1, y1, x2, y2], fill=colour, width=max(1, ray_r))
    # Core circle
    _circle(draw, cx, cy, r, colour)


def _rain_drops(draw, cx, cy, w, h, colour, count=3):
    """Draw evenly-spaced raindrops below a centre point."""
    drop_w = max(2, w // 12)
    drop_h = max(4, h // 4)
    spacing = w // (count + 1)
    start_x = cx - w // 2 + spacing
    for i in range(count):
        dx = start_x + i * spacing
        dy = cy
        draw.ellipse([dx - drop_w, dy, dx + drop_w, dy + drop_h], fill=colour)


def _snow_dots(draw, cx, cy, w, h, colour, count=6):
    """Draw snowflake dots in two rows."""
    r = max(2, w // 14)
    cols = 3
    rows = 2
    col_spacing = w // (cols + 1)
    row_spacing = h // (rows + 1)
    for row in range(rows):
        for col in range(cols):
            dx = cx - w // 2 + col_spacing * (col + 1)
            dy = cy + row_spacing * (row + 1)
            _circle(draw, dx, dy, r, colour)


def _lightning(draw, cx, cy, size, colour):
    """Draw a lightning bolt."""
    s = size
    points = [
        (cx + s * 0.1,  cy - s * 0.5),
        (cx - s * 0.1,  cy),
        (cx + s * 0.15, cy),
        (cx - s * 0.1,  cy + s * 0.5),
        (cx + s * 0.05, cy + s * 0.1),
        (cx + s * 0.2,  cy + s * 0.1),
    ]
    points = [(int(x), int(y)) for x, y in points]
    draw.polygon(points, fill=colour)


def _fog_lines(draw, cx, cy, w, h, colour, lines=3):
    """Draw horizontal fog lines."""
    lw = max(2, h // 10)
    spacing = h // (lines + 1)
    for i in range(lines):
        y = cy - h // 2 + spacing * (i + 1)
        x0 = cx - w // 2 + (i % 2) * (w // 6)
        x1 = cx + w // 2 - (i % 2) * (w // 6)
        draw.line([x0, y, x1, y], fill=colour, width=lw)


# ── Icon drawing functions ────────────────────────────────────────────────────

def _icon_clear(draw, cx, cy, size):
    _sun(draw, cx, cy, size // 3, SUN_COLOUR)


def _icon_partly_cloudy(draw, cx, cy, size):
    # Sun peeking behind cloud
    _sun(draw, cx - size // 6, cy - size // 6, size // 4, SUN_COLOUR)
    _cloud(draw, cx + size // 8, cy + size // 8,
           int(size * 0.7), int(size * 0.45), CLOUD_COLOUR)


def _icon_cloudy(draw, cx, cy, size):
    _cloud(draw, cx, cy, int(size * 0.85), int(size * 0.55), CLOUD_COLOUR)


def _icon_fog(draw, cx, cy, size):
    _fog_lines(draw, cx, cy, int(size * 0.85), size, FOG_COLOUR)


def _icon_drizzle(draw, cx, cy, size):
    cloud_h = int(size * 0.45)
    _cloud(draw, cx, cy - size // 6, int(size * 0.8), cloud_h, CLOUD_COLOUR)
    _rain_drops(draw, cx, cy + size // 6, int(size * 0.6), size // 3,
                RAIN_COLOUR, count=3)


def _icon_rain(draw, cx, cy, size):
    cloud_h = int(size * 0.4)
    _cloud(draw, cx, cy - size // 6, int(size * 0.8), cloud_h, CLOUD_COLOUR)
    _rain_drops(draw, cx, cy + size // 8, int(size * 0.7), size // 3,
                RAIN_COLOUR, count=4)


def _icon_snow(draw, cx, cy, size):
    cloud_h = int(size * 0.4)
    _cloud(draw, cx, cy - size // 6, int(size * 0.8), cloud_h, CLOUD_COLOUR)
    _snow_dots(draw, cx, cy + size // 8, int(size * 0.7), size // 3, SNOW_COLOUR)


def _icon_showers(draw, cx, cy, size):
    # Sun + cloud + rain
    _sun(draw, cx - size // 4, cy - size // 3, size // 5, SUN_COLOUR)
    cloud_h = int(size * 0.38)
    _cloud(draw, cx + size // 8, cy - size // 8, int(size * 0.7), cloud_h, CLOUD_COLOUR)
    _rain_drops(draw, cx + size // 8, cy + size // 6, int(size * 0.5),
                size // 3, RAIN_COLOUR, count=3)


def _icon_thunderstorm(draw, cx, cy, size):
    cloud_h = int(size * 0.38)
    _cloud(draw, cx, cy - size // 4, int(size * 0.8), cloud_h, CLOUD_COLOUR)
    _lightning(draw, cx, cy + size // 8, size * 0.4)


# ── WMO code → icon function map ─────────────────────────────────────────────

WMO_ICON_FN = {
    0:  _icon_clear,
    1:  _icon_clear,
    2:  _icon_partly_cloudy,
    3:  _icon_cloudy,
    45: _icon_fog,
    48: _icon_fog,
    51: _icon_drizzle,
    53: _icon_drizzle,
    55: _icon_drizzle,
    61: _icon_rain,
    63: _icon_rain,
    65: _icon_rain,
    71: _icon_snow,
    73: _icon_snow,
    75: _icon_snow,
    77: _icon_snow,
    80: _icon_showers,
    81: _icon_showers,
    82: _icon_rain,
    85: _icon_snow,
    86: _icon_snow,
    95: _icon_thunderstorm,
    96: _icon_thunderstorm,
    99: _icon_thunderstorm,
}


# ── Wind & humidity badges ───────────────────────────────────────────────────

def draw_wind_badge(img: Image.Image, speed_str: str, x: int, y: int,
                    font, text_colour: str = "#aabbcc"):
    """
    Wind icon: three horizontal streaks tapering right + arrowhead, then speed text.
    (x, y) = top-left of the badge area.
    """
    draw = ImageDraw.Draw(img)
    ic = "#7799bb"   # icon colour
    cy = y + 10      # vertical centre of the icon

    # Three wind streaks at different lengths
    for dy, x1 in [(-4, x + 14), (0, x + 18), (4, x + 14)]:
        draw.line([(x, cy + dy), (x1, cy + dy)], fill=ic, width=2)

    # Arrowhead pointing right, aligned with middle streak
    ax = x + 18
    draw.polygon([(ax, cy - 5), (ax + 8, cy), (ax, cy + 5)], fill=ic)

    # Speed text to the right of icon
    draw.text((x + 30, y + 2), speed_str, font=font, fill=text_colour)
    del draw


def draw_humidity_badge(img: Image.Image, humidity_str: str, x: int, y: int,
                        font, text_colour: str = "#aabbcc"):
    """
    Humidity icon: teardrop (circle + upward triangle point) then humidity% text.
    (x, y) = top-left of the badge area.
    """
    draw = ImageDraw.Draw(img)
    ic = "#4fc3f7"   # icon colour
    r  = 6
    cx = x + r + 1
    cy = y + 14      # centre of the round base

    # Round base of teardrop
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ic)

    # Triangular tip pointing upward
    draw.polygon([(cx, cy - r - 7), (cx - r + 1, cy - r + 2),
                  (cx + r - 1, cy - r + 2)], fill=ic)

    # Humidity text to the right of icon
    draw.text((x + 18, y + 2), humidity_str, font=font, fill=text_colour)
    del draw


# ── Public API ────────────────────────────────────────────────────────────────

def draw_weather_icon(
    img: Image.Image,
    wmo_code: int,
    x: int,
    y: int,
    size: int = 64,
):
    """
    Draw a weather icon onto img at position (x, y).
    (x, y) is the top-left corner of the icon's bounding box.
    size is the width and height of the bounding box in pixels.

    Args:
        img:      PIL Image to draw onto (modified in place)
        wmo_code: WMO weather code from Open-Meteo
        x, y:     Top-left corner of icon bounding box
        size:     Icon bounding box size in pixels
    """
    # Create a fresh ImageDraw bound to this image
    draw = ImageDraw.Draw(img)
    cx = x + size // 2
    cy = y + size // 2

    fn = WMO_ICON_FN.get(wmo_code, _icon_cloudy)
    fn(draw, cx, cy, size)
    # Delete draw object so PIL flushes it back to the image buffer
    del draw
