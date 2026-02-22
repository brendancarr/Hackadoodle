"""
geocoding.py - Location search using Open-Meteo's free geocoding API.
No API key required. Returns lat/lon/display name for a search query.
"""

import requests


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def search_location(query: str, count: int = 5, timeout: int = 8) -> list[dict]:
    """
    Search for locations by name.
    Returns a list of dicts, each with:
        name:        display name (e.g. "Maple Ridge, British Columbia, Canada")
        lat:         float
        lon:         float
        country:     str
        admin1:      str (state/province)
    Returns [] on error or no results.
    """
    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"name": query, "count": count, "language": "en", "format": "json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", []):
            parts = [r.get("name", "")]
            if r.get("admin1"):
                parts.append(r["admin1"])
            if r.get("country"):
                parts.append(r["country"])
            results.append({
                "name":    ", ".join(parts),
                "lat":     r["latitude"],
                "lon":     r["longitude"],
                "country": r.get("country", ""),
                "admin1":  r.get("admin1", ""),
            })
        return results
    except Exception as e:
        print(f"[geocoding] Search error: {e}")
        return []
