"""
main_window.py - The main application window for Hackadoodle.

Layout:
    ┌─────────────────────────────────────────────────────┐
    │  Left: Source list  │  Center: Preview  │  Right: Data │
    ├─────────────────────────────────────────────────────┤
    │              Bottom: Device + actions               │
    └─────────────────────────────────────────────────────┘
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QComboBox, QSpinBox, QStatusBar,
    QMessageBox, QSizePolicy, QProgressBar, QSystemTrayIcon, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap, QImage, QColor, QIcon, QPainter, QBrush

from pathlib import Path
from PIL import Image
import io

from geekmagic_app.renderer.template_loader import TemplateLoader
from geekmagic_app.renderer.renderer import Renderer
from geekmagic_app.device.device import SmallTVDevice
from geekmagic_app.models.data_item import DataItem
from geekmagic_app.models.source_config import SourceConfig
from geekmagic_app.models.app_config import AppConfig
from geekmagic_app.gui.add_source_dialog import AddSourceDialog
from geekmagic_app.gui.send_dialog import SendDialog, SendAllWorker

TEMPLATES_DIR = Path("geekmagic_app/templates")
FONTS_DIR     = Path("geekmagic_app/fonts")


# ── Background worker: fetch + render one source ──────────────────────────────

class LoadWorker(QThread):
    """Fetches items from a source on a background thread."""
    finished = Signal(list, str)   # (items, error_msg)

    def __init__(self, src_cfg: SourceConfig):
        super().__init__()
        self.src_cfg = src_cfg

    def run(self):
        try:
            source = self.src_cfg.build_source()
            items  = source.get_items()
            self.finished.emit(items, "")
        except Exception as e:
            self.finished.emit([], str(e))


class AutoSendWorker(QThread):
    """
    Renders ALL sources and uploads the full set silently.
    Used for both the 1-minute time tick and the 30-minute refresh tick.
    The caller passes a cache dict so non-time sources can reuse
    their last-rendered images between minute ticks.
    """
    finished = Signal(bool, str)

    def __init__(self, device: SmallTVDevice, images: list[Image.Image],
                 interval: int, brightness: int):
        super().__init__()
        self.device     = device
        self.images     = images
        self.interval   = interval
        self.brightness = brightness

    def run(self):
        self.device.set_brightness(self.brightness)
        ok, msg = self.device.send_all(
            self.images,
            interval=self.interval,
            progress_cb=None,
        )
        self.finished.emit(ok, msg)


# ── Tray icon helper ──────────────────────────────────────────────────────────

def _make_tray_icon() -> QIcon:
    """Draw a tiny clock icon for the system tray."""
    px = QPixmap(22, 22)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    # Circle face
    p.setBrush(QBrush(QColor("#2a6496")))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 20, 20)
    # Clock hands (simplified — just two lines)
    p.setPen(QColor("white"))
    p.drawLine(11, 11, 11, 5)   # hour hand up
    p.drawLine(11, 11, 16, 11)  # minute hand right
    p.end()
    return QIcon(px)


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hackadoodle")
        self.setMinimumSize(960, 620)

        # Persistent config
        self._cfg = AppConfig.load()

        # Runtime state
        self._items:         list[DataItem]    = []
        self._current_item:  DataItem | None   = None
        self._current_image: Image.Image | None = None
        self._current_index: int               = 0
        self._load_worker:   LoadWorker | None  = None
        self._selected_src:  int               = -1
        self._auto_workers:  list              = []

        # Cached renders: label -> Image (for non-time sources between ticks)
        self._render_cache:  dict[str, Image.Image] = {}

        # Core engine
        self._loader   = TemplateLoader(TEMPLATES_DIR)
        self._renderer = Renderer(fonts_dir=FONTS_DIR)

        self._build_ui()
        self._setup_tray()
        self._populate_sources_list()

        # Restore device settings
        self._device_ip.setText(self._cfg.device_ip)
        self._brightness.setValue(self._cfg.brightness)
        self._interval.setValue(self._cfg.interval)

        # Time source: re-render full slideshow every 30 s (for clock display)
        self._time_timer = QTimer(self)
        self._time_timer.setInterval(30 * 1000)
        self._time_timer.timeout.connect(self._on_time_tick)
        self._time_timer.start()

        # All sources: re-fetch + re-render every 30 min
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(30 * 60 * 1000)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._refresh_timer.start()

        self.status("Ready")

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_sources_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.addWidget(self._build_data_panel())
        splitter.setSizes([240, 300, 260])
        root.addWidget(splitter, stretch=1)

        root.addWidget(self._build_device_panel())
        root.addWidget(self._build_progress_bar())

        self.setStatusBar(QStatusBar())

    def _build_sources_panel(self) -> QGroupBox:
        box = QGroupBox("Sources")
        layout = QVBoxLayout(box)

        self._sources_list = QListWidget()
        self._sources_list.setAlternatingRowColors(True)
        self._sources_list.currentRowChanged.connect(self._on_source_selected)
        self._sources_list.itemDoubleClicked.connect(self._on_edit_source)
        layout.addWidget(self._sources_list, stretch=1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ Add")
        add_btn.clicked.connect(self._on_add_source)
        btn_row.addWidget(add_btn)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.clicked.connect(self._on_edit_source)
        self._edit_btn.setEnabled(False)
        btn_row.addWidget(self._edit_btn)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.clicked.connect(self._on_remove_source)
        self._remove_btn.setEnabled(False)
        btn_row.addWidget(self._remove_btn)
        layout.addLayout(btn_row)

        self._load_btn = QPushButton("Load & Preview")
        self._load_btn.setStyleSheet("font-weight: bold;")
        self._load_btn.clicked.connect(self._on_load_source)
        self._load_btn.setEnabled(False)
        layout.addWidget(self._load_btn)

        layout.addSpacing(4)
        layout.addWidget(QLabel("Template:"))
        self._template_combo = QComboBox()
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        self._refresh_templates()
        layout.addWidget(self._template_combo)

        return box

    def _build_preview_panel(self) -> QGroupBox:
        box = QGroupBox("Preview")
        layout = QVBoxLayout(box)
        layout.setAlignment(Qt.AlignHCenter)

        self._preview_label = QLabel()
        self._preview_label.setFixedSize(QSize(240, 240))
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet("background: #111; border: 1px solid #444;")
        self._preview_label.setText("No preview")
        layout.addWidget(self._preview_label, alignment=Qt.AlignHCenter)

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
        box = QGroupBox("Data")
        layout = QVBoxLayout(box)
        self._data_list = QListWidget()
        self._data_list.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self._data_list)
        return box

    def _build_device_panel(self) -> QGroupBox:
        box = QGroupBox("Device")
        layout = QHBoxLayout(box)
        box.setFixedHeight(90)

        layout.addWidget(QLabel("IP:"))
        self._device_ip = QLineEdit()
        self._device_ip.setPlaceholderText("10.0.0.195")
        self._device_ip.setFixedWidth(130)
        self._device_ip.textChanged.connect(self._on_device_settings_changed)
        layout.addWidget(self._device_ip)

        ping_btn = QPushButton("Test")
        ping_btn.clicked.connect(self._on_ping)
        layout.addWidget(ping_btn)

        self._conn_status = QLabel("●")
        self._conn_status.setStyleSheet("color: #888; font-size: 18px;")
        layout.addWidget(self._conn_status)

        layout.addStretch()

        layout.addWidget(QLabel("Brightness:"))
        self._brightness = QSpinBox()
        self._brightness.setRange(0, 100)
        self._brightness.setValue(80)
        self._brightness.setSuffix("%")
        self._brightness.setFixedWidth(70)
        self._brightness.valueChanged.connect(self._on_device_settings_changed)
        layout.addWidget(self._brightness)

        layout.addSpacing(12)

        layout.addWidget(QLabel("Interval:"))
        self._interval = QSpinBox()
        self._interval.setRange(3, 300)
        self._interval.setValue(10)
        self._interval.setSuffix("s")
        self._interval.setFixedWidth(65)
        self._interval.valueChanged.connect(self._on_device_settings_changed)
        layout.addWidget(self._interval)

        layout.addSpacing(12)

        # Minimise to tray
        tray_btn = QPushButton("⬇ Tray")
        tray_btn.setFixedHeight(48)
        tray_btn.setFixedWidth(80)
        tray_btn.setToolTip("Minimise to system tray")
        tray_btn.setStyleSheet(
            "font-size: 12px; background: #333; color: #ccc; border-radius: 4px;"
        )
        tray_btn.clicked.connect(self.hide)
        layout.addWidget(tray_btn)

        layout.addSpacing(4)

        self._send_btn = QPushButton("▶  Send Current")
        self._send_btn.setFixedHeight(48)
        self._send_btn.setFixedWidth(140)
        self._send_btn.setStyleSheet(
            "font-weight: bold; font-size: 13px; "
            "background: #2a6496; color: white; border-radius: 4px;"
        )
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._on_send_current)
        layout.addWidget(self._send_btn)

        self._send_all_btn = QPushButton("▶▶  Send All…")
        self._send_all_btn.setFixedHeight(48)
        self._send_all_btn.setFixedWidth(130)
        self._send_all_btn.setStyleSheet(
            "font-weight: bold; font-size: 13px; "
            "background: #3a7a3a; color: white; border-radius: 4px;"
        )
        self._send_all_btn.setEnabled(False)
        self._send_all_btn.clicked.connect(self._on_send_all)
        layout.addWidget(self._send_all_btn)

        return box

    def _build_progress_bar(self) -> QProgressBar:
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

    # ── System tray ───────────────────────────────────────────────────────────

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(_make_tray_icon())
        self._tray.setToolTip("Hackadoodle")

        menu = QMenu()
        menu.addAction("Show", self._restore_from_tray)
        menu.addSeparator()
        menu.addAction("Send All Now", self._on_send_all)
        menu.addSeparator()
        menu.addAction("Quit", self._quit)
        self._tray.setContextMenu(menu)

        # Single-click or double-click restores the window
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _quit(self):
        self._tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, event):
        """Intercept window close → minimise to tray instead of quitting."""
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "Hackadoodle",
            "Still running in the tray. Right-click the icon to quit.",
            QSystemTrayIcon.Information,
            2000,
        )

    # ── Sources list ──────────────────────────────────────────────────────────

    def _populate_sources_list(self):
        self._sources_list.clear()
        for src in self._cfg.sources:
            item = QListWidgetItem(f"{src.label}\n  → {src.template}")
            item.setToolTip(str(src.config))
            self._sources_list.addItem(item)
        has = len(self._cfg.sources) > 0
        self._send_all_btn.setEnabled(has)

    def _refresh_templates(self):
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        for name in sorted(self._loader.list_templates()):
            self._template_combo.addItem(name)
        self._template_combo.blockSignals(False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def status(self, msg: str):
        self.statusBar().showMessage(msg)

    def _render_current(self):
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
        except Exception as e:
            self.status(f"Render error: {e}")

    def _render_all_for_source(self, src_cfg: SourceConfig,
                                items: list[DataItem]) -> list[Image.Image]:
        template = self._loader.load(src_cfg.template)
        images = []
        for item in items:
            try:
                images.append(self._renderer.render(template, item))
            except Exception as e:
                print(f"[render] Skipped '{item.title}': {e}")
        return images

    def _render_all_sources(self, refresh_non_time: bool = True) -> list[Image.Image]:
        """
        Render every source in order. Returns a flat list of images.

        If refresh_non_time=False, reuse _render_cache for non-time sources
        (used on the 60-second time tick to avoid refetching weather/ICS).
        Time sources are always re-rendered fresh.
        """
        all_images: list[Image.Image] = []
        for src in self._cfg.sources:
            try:
                if src.type == "time":
                    # Always fresh
                    items  = src.build_source().get_items()
                    images = self._render_all_for_source(src, items)
                elif refresh_non_time or src.label not in self._render_cache:
                    items  = src.build_source().get_items()
                    images = self._render_all_for_source(src, items)
                    # Cache each image under "label:N"
                    for i, img in enumerate(images):
                        self._render_cache[f"{src.label}:{i}"] = img
                else:
                    # Pull from cache
                    images = [v for k, v in self._render_cache.items()
                              if k.startswith(f"{src.label}:")]
                all_images.extend(images)
            except Exception as e:
                print(f"[render_all] '{src.label}': {e}")
        return all_images

    def _update_preview(self, img: Image.Image):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qimg = QImage.fromData(buf.read())
        pixmap = QPixmap.fromImage(qimg)
        pixmap = pixmap.scaled(240, 240, Qt.KeepAspectRatio, Qt.FastTransformation)
        self._preview_label.setPixmap(pixmap)

    def _show_item(self, index: int):
        if not self._items or index < 0 or index >= len(self._items):
            return
        self._current_index = index
        self._current_item  = self._items[index]
        self._render_current()
        self._populate_data_panel(self._current_item)
        self._item_index_label.setText(f"{index+1} of {len(self._items)}")
        self._prev_btn.setEnabled(index > 0)
        self._next_btn.setEnabled(index < len(self._items) - 1)

    def _populate_data_panel(self, item: DataItem):
        self._data_list.clear()
        for key, val in [
            ("title",    item.title),
            ("subtitle", item.subtitle),
            ("value",    item.value),
            ("date",     str(item.date) if item.date else ""),
            ("location", item.location or ""),
        ]:
            if val:
                self._data_list.addItem(QListWidgetItem(f"{key}: {val}"))
        for key, val in item.meta.items():
            entry = QListWidgetItem(f"[{key}]: {val}")
            entry.setForeground(QColor("#888"))
            self._data_list.addItem(entry)

    def _fire_and_forget(self, images: list[Image.Image]):
        """Upload images on a background thread with no UI blocking."""
        ip = self._device_ip.text().strip()
        if not ip or not images:
            return
        device = SmallTVDevice(ip=ip)
        worker = AutoSendWorker(device, images,
                                self._interval.value(), self._brightness.value())
        self._auto_workers.append(worker)
        def _done(ok, msg):
            self.status(f"Auto-refresh: {msg}")
            if worker in self._auto_workers:
                self._auto_workers.remove(worker)
        worker.finished.connect(_done)
        worker.start()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_source_selected(self, row: int):
        self._selected_src = row
        has = row >= 0
        self._edit_btn.setEnabled(has)
        self._remove_btn.setEnabled(has)
        self._load_btn.setEnabled(has)
        if has and row < len(self._cfg.sources):
            src = self._cfg.sources[row]
            idx = self._template_combo.findText(src.template)
            if idx >= 0:
                self._template_combo.blockSignals(True)
                self._template_combo.setCurrentIndex(idx)
                self._template_combo.blockSignals(False)

    def _on_add_source(self):
        dlg = AddSourceDialog(self)
        if dlg.exec() and dlg.get_source_config():
            src = dlg.get_source_config()
            self._cfg.sources.append(src)
            self._cfg.save()
            self._populate_sources_list()
            self._sources_list.setCurrentRow(len(self._cfg.sources) - 1)
            self.status(f"Added: {src.label}")

    def _on_edit_source(self, *_):
        row = self._selected_src
        if row < 0 or row >= len(self._cfg.sources):
            return
        dlg = AddSourceDialog(self, edit=self._cfg.sources[row])
        if dlg.exec() and dlg.get_source_config():
            self._cfg.sources[row] = dlg.get_source_config()
            self._cfg.save()
            self._render_cache.clear()   # invalidate cache after edit
            self._populate_sources_list()
            self._sources_list.setCurrentRow(row)
            self.status("Source updated")

    def _on_remove_source(self):
        row = self._selected_src
        if row < 0 or row >= len(self._cfg.sources):
            return
        label = self._cfg.sources[row].label
        if QMessageBox.question(self, "Remove Source",
                f"Remove '{label}'?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._cfg.sources.pop(row)
            self._render_cache.clear()
            self._cfg.save()
            self._populate_sources_list()
            self.status(f"Removed: {label}")

    def _on_load_source(self):
        row = self._selected_src
        if row < 0 or row >= len(self._cfg.sources):
            return
        src = self._cfg.sources[row]
        self.status(f"Loading {src.label}…")
        self._load_btn.setEnabled(False)
        self._load_worker = LoadWorker(src)
        self._load_worker.finished.connect(self._on_load_done)
        self._load_worker.start()

    def _on_load_done(self, items: list, error: str):
        self._load_btn.setEnabled(True)
        if error:
            self.status(f"Load error: {error}")
            QMessageBox.warning(self, "Load Error", error)
            return
        if not items:
            self.status("No items returned from source")
            return
        self._items = items
        self._show_item(0)
        self.status(f"Loaded {len(items)} item(s)")

    def _on_template_changed(self, _=None):
        row = self._selected_src
        if 0 <= row < len(self._cfg.sources):
            self._cfg.sources[row].template = self._template_combo.currentText()
            self._render_cache.clear()
            self._cfg.save()
            self._populate_sources_list()
        self._render_current()

    def _on_prev_item(self):
        self._show_item(self._current_index - 1)

    def _on_next_item(self):
        self._show_item(self._current_index + 1)

    def _on_device_settings_changed(self):
        self._cfg.device_ip  = self._device_ip.text().strip()
        self._cfg.brightness = self._brightness.value()
        self._cfg.interval   = self._interval.value()
        self._cfg.save()

    def _on_ping(self):
        ip = self._device_ip.text().strip()
        if not ip:
            self.status("Enter a device IP first")
            return
        self.status(f"Pinging {ip}…")
        ok, msg = SmallTVDevice(ip=ip).ping()
        self._conn_status.setStyleSheet(
            f"color: {'#4CAF50' if ok else '#f44336'}; font-size: 18px;"
        )
        self.status(msg)

    def _on_send_current(self):
        if not self._current_image:
            self.status("Nothing to send — load a source first")
            return
        ip = self._device_ip.text().strip()
        if not ip:
            self.status("Enter a device IP first")
            return
        self._send_btn.setEnabled(False)
        self._send_btn.setText("Sending…")
        self._progress.setValue(0)
        self.status(f"Sending to {ip}…")

        device = SmallTVDevice(ip=ip)
        self._send_worker = SendAllWorker(
            device, [self._current_image],
            self._interval.value(), self._brightness.value()
        )
        self._send_worker.progress.connect(
            lambda c, t: self._progress.setValue(int(c / t * 100) if t else 0))
        self._send_worker.finished.connect(self._on_send_current_done)
        self._send_worker.start()

    def _on_send_current_done(self, ok: bool, msg: str):
        self._send_btn.setEnabled(True)
        self._send_btn.setText("▶  Send Current")
        self._progress.setValue(100 if ok else 0)
        self.status(msg)

    def _on_send_all(self):
        """Render all sources, open the tile-ordering dialog."""
        if not self._cfg.sources:
            self.status("No sources configured")
            return
        ip = self._device_ip.text().strip()
        if not ip:
            self.status("Enter a device IP first")
            return

        self.status("Rendering all sources…")
        self._send_all_btn.setEnabled(False)

        tiles = []
        for src in self._cfg.sources:
            try:
                items  = src.build_source().get_items()
                images = self._render_all_for_source(src, items)
                if images:
                    tiles.append((src, images))
                    # Prime the cache
                    for i, img in enumerate(images):
                        self._render_cache[f"{src.label}:{i}"] = img
            except Exception as e:
                print(f"[send_all] {src.label}: {e}")

        self._send_all_btn.setEnabled(True)

        if not tiles:
            self.status("Nothing rendered — check sources and templates")
            return

        dlg = SendDialog(
            tiles      = tiles,
            device_ip  = ip,
            brightness = self._brightness.value(),
            interval   = self._interval.value(),
            parent     = self,
        )
        dlg.order_confirmed.connect(self._on_order_confirmed)
        dlg.exec()

    def _on_order_confirmed(self, order: list):
        self._cfg.tile_order = order
        self._cfg.save()
        self.status(f"Sent {len(order)} tile(s) — order saved")
        self._conn_status.setStyleSheet("color: #4CAF50; font-size: 18px;")

    # ── Auto-refresh ──────────────────────────────────────────────────────────

    def _on_time_tick(self):
        """
        Every 60 s: re-render the full slideshow but only refetch time sources.
        Non-time sources are served from _render_cache to avoid network calls.
        """
        if not self._cfg.sources:
            return
        images = self._render_all_sources(refresh_non_time=False)
        self._fire_and_forget(images)

    def _on_refresh_tick(self):
        """
        Every 30 min: refetch and re-render everything, updating the cache.
        """
        if not self._cfg.sources:
            return
        self.status("Auto-refreshing all sources…")
        images = self._render_all_sources(refresh_non_time=True)
        self._fire_and_forget(images)
