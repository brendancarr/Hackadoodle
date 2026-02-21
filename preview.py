"""
preview.py - CLI test harness for the renderer + data sources.

Run from the hackadoodle/ root:
    python preview.py           ← uses JSON source (default)
    python preview.py ics       ← uses ICS source
    python preview.py ics all   ← ICS including past events
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from geekmagic_app.sources.json_source import JsonSource
from geekmagic_app.sources.ics_source import IcsSource
from geekmagic_app.renderer.template_loader import TemplateLoader
from geekmagic_app.renderer.renderer import Renderer


def build_source(mode: str, include_past: bool):
    if mode == "ics":
        print(f"  Source: ICS  ({'all events' if include_past else 'upcoming only'})")
        return IcsSource(
            "sample_data/calendar.ics",
            upcoming_only=not include_past,
        )
    elif mode == "weather":
        import json
        from geekmagic_app.sources.weather_source import WeatherSource
        cfg = json.loads(Path("sample_data/weather_config.json").read_text())
        print(f"  Source: Weather ({cfg['location']})")
        return WeatherSource(
            lat=cfg["lat"], lon=cfg["lon"],
            location=cfg["location"],
            units=cfg.get("units", "celsius")
        )
    else:
        print("  Source: JSON")
        return JsonSource("sample_data/events.json")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "json"
    include_past = len(sys.argv) > 2 and sys.argv[2] == "all"

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print("Loading data...")
    source = build_source(mode, include_past)
    items = source.get_items()
    print(f"  ✓ {len(items)} item(s) loaded")

    if not items:
        print("  No items to render. Check your source or filters.")
        return

    # Print a summary table so you can see what was loaded
    print()
    print(f"  {'#':<3} {'TITLE':<28} {'DATE':<22} {'VALUE':<12} {'LOCATION'}")
    print(f"  {'-'*3} {'-'*28} {'-'*22} {'-'*12} {'-'*20}")
    for i, item in enumerate(items):
        date_str = str(item.date)[:19] if item.date else "—"
        loc = (item.location or "—")[:20]
        print(f"  {i:<3} {item.title[:28]:<28} {date_str:<22} {item.value[:12]:<12} {loc}")
    print()

    # ── 2. Load template ──────────────────────────────────────────────────────
    loader = TemplateLoader("geekmagic_app/templates")
    template_name = "weather_current" if mode == "weather" else "calendar_basic"
    template = loader.load(template_name)
    print(f"  ✓ Template '{template.name}' ({len(template.zones)} zones)")

    # ── 3. Render each item ───────────────────────────────────────────────────
    renderer = Renderer(fonts_dir="geekmagic_app/fonts")
    output_dir = Path("preview_output")
    output_dir.mkdir(exist_ok=True)

    # Clear old previews so stale files don't confuse things
    for old in output_dir.glob("preview_*.png"):
        old.unlink()

    output_files = []
    for i, item in enumerate(items):
        safe_title = item.title[:20].replace(" ", "_").replace("/", "-")
        out_path = output_dir / f"preview_{i:02d}_{safe_title}.png"
        try:
            renderer.render_to_file(template, item, out_path)
            print(f"  ✓ [{i+1}/{len(items)}] {out_path.name}")
            output_files.append(out_path)
        except Exception as e:
            import traceback
            print(f"  ✗ [{i+1}/{len(items)}] RENDER ERROR: {e}")
            traceback.print_exc()

    # ── 4. Open the first one ─────────────────────────────────────────────────
    first = output_files[0]
    print(f"\nOpening {first.name}...")
    if sys.platform == "win32":
        os.startfile(str(first))
    elif sys.platform == "darwin":
        os.system(f"open '{first}'")
    else:
        os.system(f"xdg-open '{first}'")

    print(f"All output → {output_dir.resolve()}")


if __name__ == "__main__":
    main()
