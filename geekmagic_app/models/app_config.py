"""
app_config.py - Loads and saves hackadoodle.json.

Persists:
    - Device IP, brightness, interval
    - List of configured sources (with templates)
    - Tile order (indices into sources list)
"""

import json
from pathlib import Path
from geekmagic_app.models.source_config import SourceConfig

CONFIG_PATH = Path("hackadoodle.json")


class AppConfig:

    def __init__(self):
        self.device_ip:  str          = "10.0.0.195"
        self.brightness: int          = 80
        self.interval:   int          = 10
        self.sources:    list[SourceConfig] = []
        self.tile_order: list[int]    = []   # indices into sources

    # ── Load / Save ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        if not CONFIG_PATH.exists():
            return cfg
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.device_ip  = data.get("device_ip",  cfg.device_ip)
            cfg.brightness = data.get("brightness",  cfg.brightness)
            cfg.interval   = data.get("interval",    cfg.interval)
            cfg.sources    = [SourceConfig.from_dict(s) for s in data.get("sources", [])]
            cfg.tile_order = data.get("tile_order",  [])
        except Exception as e:
            print(f"[AppConfig] Load error: {e}")
        return cfg

    def save(self):
        try:
            data = {
                "device_ip":  self.device_ip,
                "brightness": self.brightness,
                "interval":   self.interval,
                "sources":    [s.to_dict() for s in self.sources],
                "tile_order": self.tile_order,
            }
            CONFIG_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[AppConfig] Save error: {e}")
