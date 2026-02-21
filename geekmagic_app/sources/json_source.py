"""
json_source.py - Loads DataItems from a JSON URL or local file.

SIMPLE CASE — the JSON is already a list of objects:
    [
        {"title": "Meeting", "date": "2026-02-21", "location": "Zoom"},
        {"title": "Lunch",   "date": "2026-02-22", "location": "Cafe"}
    ]

NESTED CASE — the data is buried inside the response:
    {
        "status": "ok",
        "data": {
            "events": [
                {"summary": "Meeting", "start": "2026-02-21"}
            ]
        }
    }
    Use json_path="data.events" to drill down.

FIELD MAPPING — your JSON keys don't match DataItem fields?
    {"summary": "Meeting", "dtstart": "2026-02-21"}
    Use field_map={"title": "summary", "date": "dtstart"} to remap.

SINGLE OBJECT — if the result is a dict not a list, it's wrapped in a list.

Usage:
    source = JsonSource("https://api.example.com/events.json")
    source = JsonSource("/path/to/local.json")
    source = JsonSource(url, json_path="data.items", field_map={"title": "name"})
    items = source.get_items()
"""

import json
import requests
from pathlib import Path
from geekmagic_app.sources.base import DataSource
from geekmagic_app.models.data_item import DataItem


class JsonSource(DataSource):
    """
    Loads DataItems from a JSON URL or local file path.

    Args:
        url_or_path:  HTTP/HTTPS URL or local file path string.
        json_path:    Dot-separated path into the JSON to find the list.
                      e.g. "data.events" → response["data"]["events"]
                      Leave None if the root is already a list or single object.
        field_map:    Dict mapping DataItem field names → JSON key names.
                      e.g. {"title": "summary", "date": "dtstart"}
                      Unmapped fields are matched by name automatically.
        timeout:      HTTP request timeout in seconds (default 10).
        headers:      Optional dict of HTTP headers (for auth tokens, etc.)
    """

    def __init__(
        self,
        url_or_path: str,
        json_path: str | None = None,
        field_map: dict[str, str] | None = None,
        timeout: int = 10,
        headers: dict[str, str] | None = None,
    ):
        self.url_or_path = url_or_path
        self.json_path = json_path
        self.field_map = field_map or {}
        self.timeout = timeout
        self.headers = headers or {}

    # ── DataSource interface ──────────────────────────────────────────────────

    def fetch(self) -> str:
        """Returns raw JSON string. Raises on network/IO error."""
        target = self.url_or_path.strip()

        if target.startswith("http://") or target.startswith("https://"):
            return self._fetch_url(target)
        else:
            return self._fetch_file(target)

    def parse(self, raw: str) -> list[DataItem]:
        """
        Parse a raw JSON string into DataItems.
        Returns empty list on any parse error (never raises).
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[JsonSource] JSON parse error: {e}")
            return []

        # Drill into nested path if specified
        if self.json_path:
            data = self._dig(data, self.json_path)
            if data is None:
                print(f"[JsonSource] json_path '{self.json_path}' not found in response")
                return []

        # Normalize to list
        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            print(f"[JsonSource] Expected list or dict, got {type(data).__name__}")
            return []

        items = []
        for i, obj in enumerate(data):
            if not isinstance(obj, dict):
                print(f"[JsonSource] Skipping item {i}: not a dict")
                continue
            try:
                item = self._map_to_item(obj)
                items.append(item)
            except Exception as e:
                print(f"[JsonSource] Skipping item {i}: {e}")

        return items

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_url(self, url: str) -> str:
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()  # raises HTTPError on 4xx/5xx
        return response.text

    def _fetch_file(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"JSON file not found: {p.resolve()}")
        return p.read_text(encoding="utf-8")

    def _dig(self, data: object, path: str) -> object:
        """Traverse a dot-separated path into a nested dict."""
        keys = path.split(".")
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if current is None:
                return None
        return current

    def _map_to_item(self, obj: dict) -> DataItem:
        """
        Convert a single JSON object → DataItem.

        Strategy:
        1. Apply field_map: DataItem.title ← obj[field_map["title"]]
        2. Direct match: DataItem.subtitle ← obj["subtitle"] (if key exists)
        3. Anything leftover → meta dict
        """
        # Known DataItem fields (minus "meta" which we handle separately)
        known_fields = {"title", "subtitle", "value", "date", "image", "location"}

        resolved: dict = {}

        # Step 1: apply explicit field_map
        for item_field, json_key in self.field_map.items():
            if json_key in obj:
                resolved[item_field] = obj[json_key]

        # Step 2: direct name matches for anything not already resolved
        for field in known_fields:
            if field not in resolved and field in obj:
                resolved[field] = obj[field]

        # Step 3: everything else → meta
        mapped_source_keys = set(self.field_map.values())
        meta = {
            k: v for k, v in obj.items()
            if k not in known_fields and k not in mapped_source_keys
        }

        return DataItem(
            title=str(resolved.get("title", "")),
            subtitle=str(resolved.get("subtitle", "")),
            value=str(resolved.get("value", "")),
            date=resolved.get("date"),
            image=resolved.get("image"),
            location=str(resolved.get("location", "")) if resolved.get("location") else None,
            meta=meta,
        )
