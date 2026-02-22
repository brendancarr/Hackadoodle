"""
add_source_dialog.py - Dialog for adding or editing a source entry.

Returns a SourceConfig on accept.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QSpinBox, QCheckBox, QFileDialog, QMessageBox, QWidget
)
from PySide6.QtCore import Qt, QThread, Signal

from geekmagic_app.models.source_config import SourceConfig
from geekmagic_app.renderer.template_loader import TemplateLoader
from geekmagic_app.sources.geocoding import search_location

TEMPLATES_DIR = "geekmagic_app/templates"


class GeoWorker(QThread):
    finished = Signal(list)
    def __init__(self, query):
        super().__init__()
        self.query = query
    def run(self):
        self.finished.emit(search_location(self.query))


class AddSourceDialog(QDialog):
    """
    Dialog to configure a new source.
    Call .get_source_config() after exec() == Accepted to get the result.
    Pass an existing SourceConfig to edit= to pre-populate fields.
    """

    def __init__(self, parent=None, edit: SourceConfig = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Source" if edit else "Add Source")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._loader      = TemplateLoader(TEMPLATES_DIR)
        self._geo_worker: GeoWorker | None = None
        self._geo_results: list[dict] = []
        self._result: SourceConfig | None = None

        self._build_ui()
        self._populate_templates()

        if edit:
            self._load_existing(edit)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Source type
        self._type = QComboBox()
        self._type.addItems(["JSON (URL or file)", "ICS Calendar", "Weather (Open-Meteo)", "Current Time"])
        self._type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Type:", self._type)

        # Label
        self._label = QLineEdit()
        self._label.setPlaceholderText("Display name (auto-filled)")
        form.addRow("Label:", self._label)

        # Template
        self._template = QComboBox()
        form.addRow("Template:", self._template)

        layout.addLayout(form)

        # ── JSON / ICS fields ─────────────────────────────────────────────────
        self._file_widget = QWidget()
        fl = QFormLayout(self._file_widget)
        fl.setContentsMargins(0, 0, 0, 0)

        path_row = QHBoxLayout()
        self._path = QLineEdit()
        self._path.setPlaceholderText("https://... or local path")
        path_row.addWidget(self._path, stretch=1)
        browse = QPushButton("…")
        browse.setFixedWidth(28)
        browse.clicked.connect(self._on_browse)
        path_row.addWidget(browse)
        fl.addRow("Path:", path_row)

        self._upcoming = QCheckBox("Upcoming events only")
        self._upcoming.setChecked(True)
        fl.addRow("", self._upcoming)

        self._days_ahead = QSpinBox()
        self._days_ahead.setRange(1, 30)
        self._days_ahead.setValue(2)
        self._days_ahead.setSuffix(" day(s)")
        self._days_ahead.setToolTip(
            "1 = today only (until midnight)\n"
            "2 = today + tomorrow\n"
            "7 = this week"
        )
        fl.addRow("Show ahead:", self._days_ahead)

        layout.addWidget(self._file_widget)

        # ── Weather fields ────────────────────────────────────────────────────
        self._weather_widget = QWidget()
        wl = QFormLayout(self._weather_widget)
        wl.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("e.g. Maple Ridge, BC")
        self._search.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search, stretch=1)
        self._search_btn = QPushButton("Search")
        self._search_btn.setFixedWidth(60)
        self._search_btn.clicked.connect(self._on_search)
        search_row.addWidget(self._search_btn)
        wl.addRow("Location:", search_row)

        self._results = QComboBox()
        self._results.currentIndexChanged.connect(self._on_result_selected)
        wl.addRow("Results:", self._results)

        self._coords = QLabel("Not set")
        self._coords.setStyleSheet("color: #4fc3f7; font-size: 11px;")
        wl.addRow("", self._coords)

        self._units = QComboBox()
        self._units.addItems(["celsius", "fahrenheit"])
        wl.addRow("Units:", self._units)

        self._days = QSpinBox()
        self._days.setRange(1, 3)
        self._days.setValue(1)
        self._days.setSuffix(" day(s)")
        wl.addRow("Days:", self._days)

        layout.addWidget(self._weather_widget)

        self._weather_widget.setVisible(False)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        ok = QPushButton("Add Source" if not self.windowTitle().startswith("Edit") else "Save")
        ok.setStyleSheet("font-weight: bold; background: #2a6496; color: white; padding: 4px 12px;")
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self._on_type_changed(0)

    def _populate_templates(self):
        self._template.clear()
        for name in sorted(self._loader.list_templates()):
            self._template.addItem(name)

    def _load_existing(self, src: SourceConfig):
        """Pre-populate dialog fields from an existing SourceConfig."""
        type_map = {"json": 0, "ics": 1, "weather": 2, "time": 3}
        self._type.setCurrentIndex(type_map.get(src.type, 0))
        self._label.setText(src.label)
        idx = self._template.findText(src.template)
        if idx >= 0:
            self._template.setCurrentIndex(idx)

        if src.type in ("json", "ics"):
            self._path.setText(src.config.get("path", ""))
            self._upcoming.setChecked(src.config.get("upcoming_only", True))
            self._days_ahead.setValue(src.config.get("days_ahead", 2))
        elif src.type == "weather":
            # Fake a geo result using the saved config so _on_result_selected works
            fake = {
                "name": src.config.get("location", ""),
                "lat":  src.config.get("lat", 0.0),
                "lon":  src.config.get("lon", 0.0),
            }
            self._geo_results = [fake]
            self._results.blockSignals(True)
            self._results.clear()
            self._results.addItem(fake["name"])
            self._results.blockSignals(False)
            self._coords.setText(f"{fake['lat']:.4f}, {fake['lon']:.4f}")
            idx2 = self._units.findText(src.config.get("units", "celsius"))
            if idx2 >= 0:
                self._units.setCurrentIndex(idx2)
            # Set days AFTER type change has settled
            self._days.setValue(src.config.get("max_days", 1))

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_type_changed(self, index: int):
        is_weather = (index == 2)
        is_ics     = (index == 1)
        is_time    = (index == 3)
        is_file    = not is_weather and not is_time
        self._file_widget.setVisible(is_file)
        self._weather_widget.setVisible(is_weather)
        self._upcoming.setVisible(is_ics)
        self._days_ahead.setVisible(is_ics)

        # Only auto-suggest template when adding (not editing)
        # During edit, _load_existing sets the template explicitly after this fires
        if not self._label.text():   # label is empty only on a fresh Add
            suggestions = {0: "calendar_basic", 1: "calendar_basic",
                           2: "weather_current",  3: "clock"}
            suggested = suggestions.get(index, "calendar_basic")
            idx = self._template.findText(suggested)
            if idx >= 0:
                self._template.setCurrentIndex(idx)

    def _on_browse(self):
        is_ics = self._type.currentIndex() == 1
        f = "ICS Calendar (*.ics)" if is_ics else "JSON Files (*.json);;All Files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Select file", "", f)
        if path:
            self._path.setText(path)

    def _on_search(self):
        query = self._search.text().strip()
        if not query:
            return
        self._search_btn.setEnabled(False)
        self._search_btn.setText("…")
        self._geo_worker = GeoWorker(query)
        self._geo_worker.finished.connect(self._on_geo_done)
        self._geo_worker.start()

    def _on_geo_done(self, results: list):
        self._search_btn.setEnabled(True)
        self._search_btn.setText("Search")
        self._geo_results = results
        self._results.blockSignals(True)
        self._results.clear()
        for r in results:
            self._results.addItem(r["name"])
        self._results.blockSignals(False)
        if results:
            self._on_result_selected(0)
            self._results.setCurrentIndex(0)

    def _on_result_selected(self, index: int):
        if not self._geo_results or index < 0 or index >= len(self._geo_results):
            return
        r = self._geo_results[index]
        self._coords.setText(f"{r['lat']:.4f}, {r['lon']:.4f}")
        if not self._label.text():
            self._label.setText(f"Weather \u2014 {r['name'].split(',')[0]}")

    def _on_accept(self):
        index = self._type.currentIndex()
        label    = self._label.text().strip()
        template = self._template.currentText()

        try:
            if index == 2:   # weather
                if not self._geo_results:
                    QMessageBox.warning(self, "Missing Location",
                                        "Search and select a location first.")
                    return
                ri = self._results.currentIndex()
                r  = self._geo_results[ri]
                cfg = SourceConfig.weather(
                    lat=r["lat"], lon=r["lon"],
                    location=r["name"],
                    units=self._units.currentText(),
                    max_days=self._days.value(),
                    template=template,
                )
            elif index == 1:   # ics
                path = self._path.text().strip()
                if not path:
                    QMessageBox.warning(self, "Missing Path", "Enter a file path or URL.")
                    return
                cfg = SourceConfig.ics(
                    path=path,
                    upcoming_only=self._upcoming.isChecked(),
                    days_ahead=self._days_ahead.value(),
                    label=label,
                    template=template,
                )
            elif index == 3:   # time
                cfg = SourceConfig.time(template=template)
            else:   # json
                path = self._path.text().strip()
                if not path:
                    QMessageBox.warning(self, "Missing Path", "Enter a file path or URL.")
                    return
                cfg = SourceConfig.json(path=path, label=label, template=template)

            if label:
                cfg.label = label

            self._result = cfg
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ── Result ────────────────────────────────────────────────────────────────

    def get_source_config(self) -> SourceConfig | None:
        return self._result
