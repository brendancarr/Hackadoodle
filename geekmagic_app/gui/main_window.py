"""
main_window.py - The main application window for Hackadoodle.

Layout (mirrors the spec):
    ┌─────────────────────────────────────────────────────┐
    │  Left: Sources  │  Center: Preview  │  Right: Data  │
    ├─────────────────────────────────────────────────────┤
    │           Bottom: Device + Send button              │
    └─────────────────────────────────────────────────────┘

Qt concepts used here (VB equivalents in brackets):
    QMainWindow     = Form
    QWidget         = Panel / UserControl
    QVBoxLayout     = vertical arrangement of controls
    QHBoxLayout     = horizontal arrangement of controls
    QPushButton     = Button
    QLabel          = Label
    QLineEdit       = TextBox
    QListWidget     = ListBox
    QSplitter       = resizable divider between panels
    QPixmap         = how Qt holds an image for display
    signal/slot     = event / event handler (e.g. clicked → on_send_clicked)
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QComboBox, QSpinBox, QStatusBar,
    QFileDialog, QMessageBox, QSizePolicy, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QFont, QColor

from pathlib import Path
from PIL import Image
import io

# Our own modules
from geekmagic_app.renderer.template_loader import TemplateLoader
from geekmagic_app.renderer.renderer import Renderer
from geekmagic_app.sources.json_source import JsonSource
from geekmagic_app.sources.ics_source import IcsSource
from geekmagic_app.device.device import SmallTVDevice
from geekmagic_app.models.data_item import DataItem

TEMPLATES_DIR = Path("geekmagic_app/templates")
FONTS_DIR     = Path("geekmagic_app/fonts")


# ── Background worker for send (keeps UI responsive) ─────────────────────────

class SendWorker(QThread):
    """
    Sends image(s) to the device on a background thread.
    This prevents the UI from freezing during the upload.

    In VB terms: this is like using a BackgroundWorker component.
    """
    finished = Signal(bool, str)    # (success, message)
    progress = Signal(int, int)     # (current, total) — for progress bar

    def __init__(self, device: SmallTVDevice, images: list, interval: int = 10, send_all: bool = False):
        super().__init__()
        self.device   = device
        self.images   = images
        self.interval = interval
        self.send_all = send_all

    def run(self):
        if self.send_all:
            ok, msg = self.device.send_all(
                self.images,
                interval=self.interval,
                progress_cb=lambda cur, tot: self.progress.emit(cur, tot)
            )
        else:
            self.progress.emit(0, 1)
            ok, msg = self.device.send_image(self.images[0])
            self.progress.emit(1, 1)
        self.finished.emit(ok, msg)


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hackadoodle")
        self.setMinimumSize(900, 600)

        # App state
        self._items: list[DataItem] = []       # loaded data items
        self._current_item: DataItem | None = None
        self._current_image: Image.Image | None = None
        self._send_worker: SendWorker | None = None

        # Core engine objects
        self._loader   = TemplateLoader(TEMPLATES_DIR)
        self._renderer = Renderer(fonts_dir=FONTS_DIR)

        # Build UI
        self._build_ui()
        self._refresh_templates()

        self.status("Ready")

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        """Assemble all panels into the main window."""

        # Central widget — everything lives inside this
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        # ── Top area: three-panel splitter ────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_sources_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.addWidget(self._build_data_panel())
        splitter.setSizes([220, 320, 260])   # initial column widths
        root_layout.addWidget(splitter, stretch=1)

        # ── Bottom area: device controls + progress ───────────────────────────
        root_layout.addWidget(self._build_device_panel())
        root_layout.addWidget(self._build_progress_bar())

        # ── Status bar (bottom of window, built into QMainWindow) ─────────────
        self.setStatusBar(QStatusBar())

    def _build_sources_panel(self) -> QGroupBox:
        """Left panel — configure and load a data source."""
        box = QGroupBox("Source")
        layout = QVBoxLayout(box)

        # Source type dropdown
        self._source_type = QComboBox()
        self._source_type.addItems(["JSON (URL or file)", "ICS Calendar (URL or file)"])
        self._source_type.currentIndexChanged.connect(self._on_source_type_changed)
        layout.addWidget(QLabel("Type:"))
        layout.addWidget(self._source_type)

        # URL / file path input
        layout.addWidget(QLabel("URL or file path:"))
        path_row = QHBoxLayout()
        self._source_path = QLineEdit()
        self._source_path.setPlaceholderText("https://... or C:\\path\\to\\file")
        self._source_path.setText("sample_data/events.json")
        path_row.addWidget(self._source_path, stretch=1)
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(32)
        browse_btn.setToolTip("Browse for a local file")
        browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # ICS-only option (hidden until ICS selected)
        self._upcoming_only_label = QLabel("Show upcoming events only:")
        self._upcoming_only = QComboBox()
        self._upcoming_only.addItems(["Yes", "No"])
        self._upcoming_only_label.setVisible(False)
        self._upcoming_only.setVisible(False)
        layout.addWidget(self._upcoming_only_label)
        layout.addWidget(self._upcoming_only)

        # Load button
        load_btn = QPushButton("Load Source")
        load_btn.clicked.connect(self._on_load_source)
        load_btn.setStyleSheet("font-weight: bold;")
        layout.addWidget(load_btn)

        # Template picker
        layout.addSpacing(8)
        layout.addWidget(QLabel("Template:"))
        self._template_combo = QComboBox()
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        layout.addWidget(self._template_combo)

        layout.addStretch()
        return box

    def _build_preview_panel(self) -> QGroupBox:
        """Center panel — shows the rendered 240×240 image."""
        box = QGroupBox("Preview")
        layout = QVBoxLayout(box)
        layout.setAlignment(Qt.AlignHCenter)

        # Image display — scaled up 2x so 240px doesn't look tiny on screen
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(QSize(240, 240))
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet(
            "background: #111; border: 1px solid #444;"
        )
        self._preview_label.setText("No preview")
        layout.addWidget(self._preview_label, alignment=Qt.AlignHCenter)

        # Nav buttons to step through items
        nav_row = QHBoxLayout()
        self._prev_btn = QPushButton("◀ Prev")
        self._prev_btn.clicked.connect(self._on_prev_item)
        self._prev_btn.setEnabled(False)
        self._next_btn = QPushButton("Next ▶")
        self._next_btn.clicked.connect(self._on_next_item)
        self._next_btn.setEnabled(False)
        nav_row.addWidget(self._prev_btn)
        nav_row.addWidget(self._next_btn)
        layout.addLayout(nav_row)

        self._item_index_label = QLabel("")
        self._item_index_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._item_index_label)

        layout.addStretch()
        return box

    def _build_data_panel(self) -> QGroupBox:
        """Right panel — shows the raw field values of the current item."""
        box = QGroupBox("Data")
        layout = QVBoxLayout(box)

        self._data_list = QListWidget()
        self._data_list.setStyleSheet("font-family: monospace; font-size: 11px;")
        self._data_list.currentRowChanged.connect(self._on_data_item_selected)
        layout.addWidget(self._data_list)

        return box

    def _build_device_panel(self) -> QGroupBox:
        """Bottom panel — device IP, connection test, send button."""
        box = QGroupBox("Device")
        layout = QHBoxLayout(box)
        box.setFixedHeight(90)

        # IP address
        layout.addWidget(QLabel("IP Address:"))
        self._device_ip = QLineEdit()
        self._device_ip.setPlaceholderText("10.0.0.195")
        self._device_ip.setText("10.0.0.195")
        self._device_ip.setFixedWidth(140)
        layout.addWidget(self._device_ip)

        # Ping button
        ping_btn = QPushButton("Test Connection")
        ping_btn.clicked.connect(self._on_ping)
        layout.addWidget(ping_btn)

        # Connection status indicator
        self._conn_status = QLabel("●")
        self._conn_status.setStyleSheet("color: #888; font-size: 18px;")
        self._conn_status.setToolTip("Grey = untested, Green = connected, Red = failed")
        layout.addWidget(self._conn_status)

        layout.addStretch()

        # Brightness
        layout.addWidget(QLabel("Brightness:"))
        self._brightness = QSpinBox()
        self._brightness.setRange(0, 100)
        self._brightness.setValue(80)
        self._brightness.setSuffix("%")
        self._brightness.setFixedWidth(70)
        layout.addWidget(self._brightness)

        layout.addSpacing(16)

        # Slideshow interval
        layout.addWidget(QLabel("Interval (s):"))
        self._interval = QSpinBox()
        self._interval.setRange(3, 300)
        self._interval.setValue(10)
        self._interval.setSuffix("s")
        self._interval.setFixedWidth(65)
        self._interval.setToolTip("Seconds between slides in slideshow mode")
        layout.addWidget(self._interval)

        layout.addSpacing(8)

        # Send current button
        self._send_btn = QPushButton("▶  Send Current")
        self._send_btn.setFixedHeight(48)
        self._send_btn.setFixedWidth(140)
        self._send_btn.setStyleSheet(
            "font-weight: bold; font-size: 13px; "
            "background: #2a6496; color: white; border-radius: 4px;"
        )
        self._send_btn.setToolTip("Send only the currently previewed image")
        self._send_btn.clicked.connect(self._on_send)
        self._send_btn.setEnabled(False)
        layout.addWidget(self._send_btn)

        # Send all button
        self._send_all_btn = QPushButton("▶▶  Send All")
        self._send_all_btn.setFixedHeight(48)
        self._send_all_btn.setFixedWidth(130)
        self._send_all_btn.setStyleSheet(
            "font-weight: bold; font-size: 13px; "
            "background: #3a7a3a; color: white; border-radius: 4px;"
        )
        self._send_all_btn.setToolTip("Render and upload all items as a slideshow")
        self._send_all_btn.clicked.connect(self._on_send_all)
        self._send_all_btn.setEnabled(False)
        layout.addWidget(self._send_all_btn)

        return box

    def _build_progress_bar(self) -> QProgressBar:
        """Thin progress bar shown during multi-image uploads."""
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { border: none; background: #333; }"
            "QProgressBar::chunk { background: #4CAF50; }"
        )
        return self._progress

    # ── Helpers ───────────────────────────────────────────────────────────────

    def status(self, msg: str):
        """Write a message to the status bar at the bottom of the window."""
        self.statusBar().showMessage(msg)

    def _refresh_templates(self):
        """Populate the template dropdown from the templates folder."""
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        for name in sorted(self._loader.list_templates()):
            self._template_combo.addItem(name)
        self._template_combo.blockSignals(False)

    def _render_current(self):
        """Render the current item with the current template and update preview."""
        if not self._current_item:
            return
        template_name = self._template_combo.currentText()
        if not template_name:
            return
        try:
            template = self._loader.load(template_name)
            img = self._renderer.render(template, self._current_item)
            self._current_image = img
            self._update_preview(img)
            self._send_btn.setEnabled(True)
            self._send_all_btn.setEnabled(len(self._items) > 0)
        except Exception as e:
            self.status(f"Render error: {e}")

    def _render_all(self) -> list:
        """Render every item and return a list of PIL Images."""
        template_name = self._template_combo.currentText()
        if not template_name:
            return []
        template = self._loader.load(template_name)
        images = []
        for item in self._items:
            try:
                images.append(self._renderer.render(template, item))
            except Exception as e:
                print(f"Render skipped for '{item.title}': {e}")
        return images

    def _update_preview(self, img: Image.Image):
        """Convert a PIL Image to a QPixmap and display it in the preview label."""
        # PIL → bytes → QImage → QPixmap
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qimg = QImage.fromData(buf.read())
        pixmap = QPixmap.fromImage(qimg)
        # Scale up to fill the 240×240 label (nearest-neighbor for crisp pixels)
        pixmap = pixmap.scaled(
            240, 240,
            Qt.KeepAspectRatio,
            Qt.FastTransformation
        )
        self._preview_label.setPixmap(pixmap)

    def _show_item(self, index: int):
        """Display item at index: update preview and data panel."""
        if not self._items or index < 0 or index >= len(self._items):
            return
        self._current_item = self._items[index]
        self._render_current()
        self._populate_data_panel(self._current_item)
        self._item_index_label.setText(f"{index + 1} of {len(self._items)}")
        self._prev_btn.setEnabled(index > 0)
        self._next_btn.setEnabled(index < len(self._items) - 1)
        self._current_index = index

    def _populate_data_panel(self, item: DataItem):
        """Fill the right panel with the field values of the current item."""
        self._data_list.clear()
        fields = [
            ("title",    item.title),
            ("subtitle", item.subtitle),
            ("value",    item.value),
            ("date",     str(item.date) if item.date else ""),
            ("location", item.location or ""),
        ]
        for key, val in fields:
            if val:
                entry = QListWidgetItem(f"{key}: {val}")
                self._data_list.addItem(entry)
        for key, val in item.meta.items():
            entry = QListWidgetItem(f"[{key}]: {val}")
            entry.setForeground(QColor("#888"))
            self._data_list.addItem(entry)

    # ── Event handlers (slots) ────────────────────────────────────────────────
    # These are equivalent to Button1_Click handlers in VB.

    def _on_source_type_changed(self, index: int):
        is_ics = (index == 1)
        self._upcoming_only_label.setVisible(is_ics)
        self._upcoming_only.setVisible(is_ics)
        if is_ics:
            if not self._source_path.text().endswith(".ics"):
                self._source_path.setText("sample_data/calendar.ics")
        else:
            if not self._source_path.text().endswith(".json"):
                self._source_path.setText("sample_data/events.json")

    def _on_browse(self):
        """Open a file picker dialog."""
        is_ics = self._source_type.currentIndex() == 1
        filter_str = "ICS Calendar (*.ics)" if is_ics else "JSON Files (*.json)"
        path, _ = QFileDialog.getOpenFileName(self, "Select file", "", filter_str)
        if path:
            self._source_path.setText(path)

    def _on_load_source(self):
        """Load data from the configured source and populate the data panel."""
        path = self._source_path.text().strip()
        if not path:
            self.status("Enter a URL or file path first")
            return

        self.status("Loading...")
        try:
            if self._source_type.currentIndex() == 1:
                upcoming = self._upcoming_only.currentText() == "Yes"
                source = IcsSource(path, upcoming_only=upcoming)
            else:
                source = JsonSource(path)

            items = source.get_items()

            if not items:
                self.status("No items found in source")
                return

            self._items = items
            self._current_index = 0
            self._show_item(0)
            self.status(f"Loaded {len(items)} item(s) from source")

        except FileNotFoundError:
            self.status(f"File not found: {path}")
            QMessageBox.warning(self, "Load Error", f"File not found:\n{path}")
        except Exception as e:
            self.status(f"Load error: {e}")
            QMessageBox.warning(self, "Load Error", str(e))

    def _on_template_changed(self, _index: int):
        """Re-render when the user picks a different template."""
        self._render_current()

    def _on_prev_item(self):
        self._show_item(self._current_index - 1)

    def _on_next_item(self):
        self._show_item(self._current_index + 1)

    def _on_data_item_selected(self, row: int):
        """Clicking a row in the data panel navigates to that item."""
        # (Currently the data panel shows fields, not a list of items.
        #  This hook is here for future use when we add a full item list.)
        pass

    def _on_ping(self):
        """Test the device connection and update the indicator dot."""
        ip = self._device_ip.text().strip()
        if not ip:
            self.status("Enter a device IP address first")
            return
        self.status(f"Pinging {ip}...")
        device = SmallTVDevice(ip=ip)
        ok, msg = device.ping()
        if ok:
            self._conn_status.setStyleSheet("color: #4CAF50; font-size: 18px;")  # green
        else:
            self._conn_status.setStyleSheet("color: #f44336; font-size: 18px;")  # red
        self.status(msg)

    def _on_send(self):
        """Send the currently previewed image to the device."""
        if not self._current_image:
            self.status("Nothing to send — load a source first")
            return
        ip = self._device_ip.text().strip()
        if not ip:
            self.status("Enter a device IP address first")
            return

        self._set_sending(True)
        self.status(f"Sending current image to {ip}...")
        self._progress.setValue(0)

        device = SmallTVDevice(ip=ip)
        device.set_brightness(self._brightness.value())

        self._send_worker = SendWorker(device, [self._current_image], send_all=False)
        self._send_worker.progress.connect(self._on_progress)
        self._send_worker.finished.connect(self._on_send_finished)
        self._send_worker.start()

    def _on_send_all(self):
        """Render all items and send as a slideshow."""
        if not self._items:
            self.status("No items loaded — load a source first")
            return
        ip = self._device_ip.text().strip()
        if not ip:
            self.status("Enter a device IP address first")
            return

        self.status(f"Rendering {len(self._items)} item(s)...")
        images = self._render_all()
        if not images:
            self.status("Nothing rendered — check template")
            return

        self._set_sending(True)
        self._progress.setValue(0)
        self.status(f"Uploading {len(images)} image(s) to {ip}...")

        device = SmallTVDevice(ip=ip)
        device.set_brightness(self._brightness.value())

        self._send_worker = SendWorker(
            device, images,
            interval=self._interval.value(),
            send_all=True
        )
        self._send_worker.progress.connect(self._on_progress)
        self._send_worker.finished.connect(self._on_send_finished)
        self._send_worker.start()

    def _on_progress(self, current: int, total: int):
        """Update the progress bar during multi-image upload."""
        if total > 0:
            self._progress.setValue(int(current / total * 100))

    def _on_send_finished(self, ok: bool, msg: str):
        """Called when the background send thread completes."""
        self._set_sending(False)
        self._progress.setValue(100 if ok else 0)
        if ok:
            self._conn_status.setStyleSheet("color: #4CAF50; font-size: 18px;")
        self.status(msg)

    def _set_sending(self, sending: bool):
        """Enable/disable send buttons and update their labels."""
        self._send_btn.setEnabled(not sending)
        self._send_all_btn.setEnabled(not sending)
        self._send_btn.setText("Sending…" if sending else "▶  Send Current")
        self._send_all_btn.setText("Uploading…" if sending else "▶▶  Send All")
