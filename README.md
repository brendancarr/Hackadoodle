# Hackadoodle
For the GeekMagic Ultra - a Windows desktop app that pulls structured data from sources, maps it into visual templates, renders 240×240 images, and uploads them to a GeekMagic Ultra device. 

Core pipeline Data Source → Normalized Data → Template Mapping → Renderer → PNG → Device Upload 

Everything in the app exists to support one of those stages.

# Tech Stack

1. Python 3.x
2. PySide6 (Qt Widgets UI)
3. Pillow (image rendering)
4. requests (HTTP)
5. icalendar (ICS parsing)
6. feedparser (RSS later)
7. PyInstaller (EXE build)

# Project Structure
```
geekmagic_app/
  gui/
  sources/
  templates/
  renderer/
  device/
  models/
  main.py
```
# Data model
```
{
  "title": str,
  "subtitle": str,
  "value": str|float,
  "date": datetime|str,
  "image": str|None,
  "location": str|None,
  "meta": dict
}
```
# Data source system

Each source #  plugin class.

Interface:
```
class DataSource:
    def fetch(self): ...
    def parse(self, raw): ...
    def get_items(self) -> list[dict]
```
Initial sources:

- JSON URL
- ICS calendar URL/file

Future:

- RSS
- IMAP email?
- REST auth APIs
- Scraper

# Template system

Templates are JSON files describing layout zones.

Example:
```
{
  "name": "calendar_basic",
  "background": "#000000",
  "zones": [
    {"field": "title", "x": 10, "y": 10, "font": "bold18", "color": "#ffffff"},
    {"field": "date", "x": 10, "y": 40, "font": "regular14"}
  ]
}
```
Template Rules:

absolute positioning (240×240)
zones bind to fields
renderer interprets
templates are user-editable files

# Renderer

Input:

- template
- data item

Output:

- 240×240 PNG

Responsibilities:

- draw background
- draw text
- draw images (scaled)
- clipping
- truncation
- formatting filters

Filters v1:

- date_short
- currency
- upper
- lower
- truncate(n)

# Device module

Responsibilities:

- auto-find device on network?
- upload image
- clear images
- list images (optional)
- connection test

Config:

- device_ip
- slot
- timeout

# GUI structure (Qt)

Main window sections:

- Left: Sources
- Center: Template preview
- Right: Field mapping / data view
- Bottom: Device + actions

# Coding order (important)

- renderer
- template loader
- JSON source
- preview CLI test
- device upload
- Qt UI shell
- source UI
- mapping UI
