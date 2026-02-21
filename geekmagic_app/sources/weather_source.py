"""
weather_source.py - Fetches current weather from Open-Meteo (no API key needed).

Open-Meteo is a free, open-source weather API with no registration required.
It uses latitude/longitude for location. Returns current conditions plus
a daily forecast.

WMO Weather Codes (wmo_code field):
    0        = Clear sky
    1,2,3    = Mainly clear, partly cloudy, overcast
    45,48    = Fog
    51,53,55 = Drizzle (light, moderate, dense)
    61,63,65 = Rain (slight, moderate, heavy)
    71,73,75 = Snow (slight, moderate, heavy)
    77       = Snow grains
    80,81,82 = Rain showers (slight, moderate, violent)
    85,86    = Snow showers
    95       = Thunderstorm
    96,99    = Thunderstorm with hail

Usage:
    source = WeatherSource(lat=49.2827, lon=-123.1207, location="Vancouver, BC")
    items = source.get_items()
    # items[0] = current conditions
    # items[1..7] = daily forecast
"""

import requests
from datetime import datetime
from geekmagic_app.sources.base import DataSource
from geekmagic_app.models.data_item import DataItem


# WMO weather interpretation codes → human readable
WMO_DESCRIPTIONS = {
    0:  "Clear Sky",
    1:  "Mainly Clear",
    2:  "Partly Cloudy",
    3:  "Overcast",
    45: "Foggy",
    48: "Icy Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Showers",
    81: "Rain Showers",
    82: "Heavy Showers",
    85: "Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}

# Text-based icon prefixes — PIL can't render emoji Unicode reliably.
# These render as plain ASCII using whatever TTF font is loaded.
WMO_ICONS = {
    0:  "[SUN]",
    1:  "[SUN]",
    2:  "[PTCLD]",
    3:  "[OVRCT]",
    45: "[FOG]",
    48: "[FOG]",
    51: "[DRZL]",
    53: "[DRZL]",
    55: "[DRZL]",
    61: "[RAIN]",
    63: "[RAIN]",
    65: "[RAIN]",
    71: "[SNOW]",
    73: "[SNOW]",
    75: "[SNOW]",
    77: "[SNOW]",
    80: "[SHWR]",
    81: "[SHWR]",
    82: "[SHWR]",
    85: "[SNWSHR]",
    86: "[SNWSHR]",
    95: "[TSTM]",
    96: "[TSTM]",
    99: "[TSTM]",
}


class WeatherSource(DataSource):
    """
    Fetches current weather + 7-day forecast from Open-Meteo.

    Args:
        lat:          Latitude  (e.g. 49.2827 for Vancouver)
        lon:          Longitude (e.g. -123.1207 for Vancouver)
        location:     Display name shown in the template
        units:        "celsius" or "fahrenheit"
        timeout:      HTTP timeout in seconds
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(
        self,
        lat: float,
        lon: float,
        location: str = "",
        units: str = "celsius",
        timeout: int = 10,
    ):
        self.lat      = lat
        self.lon      = lon
        self.location = location
        self.units    = units
        self.timeout  = timeout

    # ── DataSource interface ──────────────────────────────────────────────────

    def fetch(self) -> dict:
        temp_unit = "celsius" if self.units == "celsius" else "fahrenheit"
        params = {
            "latitude":            self.lat,
            "longitude":           self.lon,
            "current":             "temperature_2m,apparent_temperature,weathercode,windspeed_10m,relativehumidity_2m",
            "daily":               "weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit":    temp_unit,
            "windspeed_unit":      "kmh",
            "timezone":            "auto",
            "forecast_days":       7,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def parse(self, raw: dict) -> list[DataItem]:
        items = []
        symbol = "°C" if self.units == "celsius" else "°F"

        try:
            # ── Current conditions → items[0] ─────────────────────────────────
            cur  = raw.get("current", {})
            temp = cur.get("temperature_2m")
            feel = cur.get("apparent_temperature")
            code = cur.get("weathercode", 0)
            wind = cur.get("windspeed_10m")
            humi = cur.get("relativehumidity_2m")
            desc = WMO_DESCRIPTIONS.get(code, "Unknown")
            icon = WMO_ICONS.get(code, "?")

            items.append(DataItem(
                title    = desc,
                subtitle = f"Feels like {feel}{symbol}  Humidity {humi}%",
                value    = f"{temp}{symbol}",
                date     = datetime.now(),
                location = self.location,
                meta     = {
                    "icon":     icon,
                    "wind":     f"Wind {wind} km/h",
                    "humidity": f"{humi}%",
                    "wmo_code": code,
                    "type":     "current",
                }
            ))

            # ── Daily forecast → items[1..7] ──────────────────────────────────
            daily = raw.get("daily", {})
            dates     = daily.get("time", [])
            codes     = daily.get("weathercode", [])
            temp_maxs = daily.get("temperature_2m_max", [])
            temp_mins = daily.get("temperature_2m_min", [])
            precip    = daily.get("precipitation_probability_max", [])

            for i, date_str in enumerate(dates):
                d_code = codes[i] if i < len(codes) else 0
                d_max  = temp_maxs[i] if i < len(temp_maxs) else None
                d_min  = temp_mins[i] if i < len(temp_mins) else None
                d_prec = precip[i] if i < len(precip) else None
                d_desc = WMO_DESCRIPTIONS.get(d_code, "Unknown")
                d_icon = WMO_ICONS.get(d_code, "?")

                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    dt = None

                items.append(DataItem(
                    title    = d_desc,
                    subtitle = f"Low {d_min}{symbol}",
                    value    = f"{d_max}{symbol}",
                    date     = dt,
                    location = self.location,
                    meta     = {
                        "temp_min":   f"{d_min}{symbol}",
                        "temp_max":   f"{d_max}{symbol}",
                        "precip_pct": f"{d_prec}%" if d_prec is not None else "",
                        "wmo_code":   d_code,
                        "type":       "forecast",
                    }
                ))

        except Exception as e:
            print(f"[WeatherSource] Parse error: {e}")

        return items
