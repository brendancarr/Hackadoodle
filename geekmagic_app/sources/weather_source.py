"""
weather_source.py - Fetches current weather from Open-Meteo (no API key needed).
"""

import requests
from datetime import datetime
from geekmagic_app.sources.base import DataSource
from geekmagic_app.models.data_item import DataItem


WMO_DESCRIPTIONS = {
    0:  "Clear Sky",     1:  "Mainly Clear",  2:  "Partly Cloudy",
    3:  "Overcast",      45: "Foggy",          48: "Icy Fog",
    51: "Light Drizzle", 53: "Drizzle",        55: "Heavy Drizzle",
    61: "Light Rain",    63: "Rain",           65: "Heavy Rain",
    71: "Light Snow",    73: "Snow",           75: "Heavy Snow",
    77: "Snow Grains",   80: "Showers",        81: "Rain Showers",
    82: "Heavy Showers", 85: "Snow Showers",   86: "Heavy Snow Showers",
    95: "Thunderstorm",  96: "Thunderstorm",   99: "Thunderstorm",
}


class WeatherSource(DataSource):
    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, lat, lon, location="", units="celsius",
                 timeout=10, max_days=1):
        self.lat      = lat
        self.lon      = lon
        self.location = location
        self.units    = units
        self.timeout  = timeout
        self.max_days = max(1, min(3, max_days))

    def fetch(self):
        temp_unit = "celsius" if self.units == "celsius" else "fahrenheit"
        params = {
            "latitude":         self.lat,
            "longitude":        self.lon,
            "current":          "temperature_2m,apparent_temperature,weathercode,windspeed_10m,relativehumidity_2m",
            "daily":            "weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": temp_unit,
            "windspeed_unit":   "kmh",
            "timezone":         "auto",
            "forecast_days":    7,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def parse(self, raw):
        items = []
        sym = "\u00b0C" if self.units == "celsius" else "\u00b0F"

        try:
            # Current conditions -> item 0
            cur  = raw.get("current", {})
            temp = cur.get("temperature_2m")
            feel = cur.get("apparent_temperature")
            code = cur.get("weathercode", 0)
            wind = cur.get("windspeed_10m")
            humi = cur.get("relativehumidity_2m")
            desc = WMO_DESCRIPTIONS.get(code, "Unknown")

            items.append(DataItem(
                title    = desc,
                subtitle = f"Feels like {feel}{sym}",
                value    = f"{temp}{sym}",
                date     = datetime.now(),
                location = self.location,
                meta     = {
                    "wind":     f"{wind} km/h",
                    "humidity": f"{humi}%",
                    "wmo_code": code,
                    "type":     "current",
                }
            ))

            # Daily forecast — skip index 0 (today) to avoid duplicating current
            daily     = raw.get("daily", {})
            dates     = daily.get("time", [])[1:]
            codes     = daily.get("weathercode", [])[1:]
            temp_maxs = daily.get("temperature_2m_max", [])[1:]
            temp_mins = daily.get("temperature_2m_min", [])[1:]
            precip    = daily.get("precipitation_probability_max", [])[1:]

            for i, date_str in enumerate(dates):
                d_code = codes[i]     if i < len(codes)     else 0
                d_max  = temp_maxs[i] if i < len(temp_maxs) else None
                d_min  = temp_mins[i] if i < len(temp_mins) else None
                d_prec = precip[i]    if i < len(precip)    else None
                d_desc = WMO_DESCRIPTIONS.get(d_code, "Unknown")

                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    dt = None

                items.append(DataItem(
                    title    = d_desc,
                    subtitle = f"Low {d_min}{sym}",
                    value    = f"{d_max}{sym}",
                    date     = dt,
                    location = self.location,
                    meta     = {
                        "wind":       "",
                        "humidity":   "",
                        "wmo_code":   d_code,
                        "precip_pct": f"{d_prec}%" if d_prec is not None else "",
                        "type":       "forecast",
                    }
                ))

        except Exception as e:
            print(f"[WeatherSource] Parse error: {e}")

        # max_days=1 -> current only
        # max_days=2 -> current + tomorrow
        # max_days=3 -> current + tomorrow + day after
        return items[:self.max_days]

    def get_items(self):
        try:
            return self.parse(self.fetch())
        except Exception as e:
            print(f"[WeatherSource] Error: {e}")
            return []
