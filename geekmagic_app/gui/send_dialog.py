"""
send_dialog.py - Tile ordering dialog shown before sending to device.

Shows all rendered tiles as thumbnails in a drag-to-reorder list.
User can reorder, then click Send to push them all to the device.

Tile order is saved back to AppConfig when Send is clicked.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QProgressBar,
    QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QIcon

from PIL import Image
import io

from geekmagic_app.device.device import SmallTVDevice
from geekmagic_app.models.source_config import SourceConfig


THUMB_SIZE = 120   # thumbnail size in the dialog list


class SendAllWorker(QThread):
    progress = Signal(int, int)    # current, total
    finished = Signal(bool, str)   # ok, message

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
            progress_cb=lambda cur, tot: self.progress.emit(cur, tot)
        )
        self.finished.emit(ok, msg)


class SendDialog(QDialog):
    """
    Modal dialog showing rendered tiles in drag-to-reorder order.

    Args:
        tiles:      list of (SourceConfig, list[PIL Image]) tuples
        device_ip:  IP to send to
        brightness: brightness level
        interval:   slideshow interval in seconds
        parent:     parent widget
    """

    # Emits the final tile order (list of source indices) when send succeeds
    order_confirmed = Signal(list)

    def __init__(self, tiles, device_ip: str, brightness: int,
                 interval: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send All \u2014 Arrange Tiles")
        self.setMinimumSize(520, 520)
        self.setModal(True)

        self._tiles      = tiles       # [(SourceConfig, [Image, ...]), ...]
        self._device_ip  = device_ip
        self._brightness = brightness
        self._interval   = interval
        self._worker: SendAllWorker | None = None

        # Flatten tiles into a single ordered list of (label, image) entries
        # Each source may produce 1..N images
        self._entries: list[tuple[str, Image.Image]] = []
        for src_cfg, images in tiles:
            for i, img in enumerate(images):
                suffix = f" ({i+1})" if len(images) > 1 else ""
                self._entries.append((src_cfg.label + suffix, img))

        self._build_ui()
        self._populate_list()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Instructions
        lbl = QLabel("Drag tiles to reorder. This is the order they'll cycle on the device.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #aaa; font-size: 12px;")
        layout.addWidget(lbl)

        # Tile list — drag to reorder
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setDefaultDropAction(Qt.MoveAction)
        self._list.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self._list.setSpacing(4)
        self._list.setStyleSheet("""
            QListWidget { background: #111; border: 1px solid #333; }
            QListWidget::item { background: #1a1a2e; border: 1px solid #333;
                                margin: 3px; border-radius: 4px; padding: 6px; }
            QListWidget::item:selected { background: #2a3f5f; border: 1px solid #4fc3f7; }
            QListWidget::item:hover { background: #222; }
        """)
        layout.addWidget(self._list, stretch=1)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { border: none; background: #333; }"
            "QProgressBar::chunk { background: #4CAF50; }"
        )
        layout.addWidget(self._progress)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status)

        # Buttons
        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()

        count = sum(len(imgs) for _, imgs in self._tiles)
        self._send_btn = QPushButton(f"\u25b6\u25b6  Send {count} Tile(s) to Device")
        self._send_btn.setFixedHeight(40)
        self._send_btn.setStyleSheet(
            "font-weight: bold; font-size: 13px; "
            "background: #3a7a3a; color: white; border-radius: 4px; padding: 0 16px;"
        )
        self._send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self._send_btn)
        layout.addLayout(btn_row)

    def _populate_list(self):
        """Add all tiles to the list as draggable thumbnail items."""
        self._list.clear()
        for label, img in self._entries:
            item = QListWidgetItem()
            item.setText(f"  {label}")
            item.setIcon(QIcon(self._pil_to_pixmap(img, THUMB_SIZE)))
            item.setSizeHint(QSize(THUMB_SIZE + 160, THUMB_SIZE + 16))
            self._list.addItem(item)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _pil_to_pixmap(self, img: Image.Image, size: int) -> QPixmap:
        thumb = img.copy()
        thumb.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        thumb.save(buf, format="PNG")
        buf.seek(0)
        qimg = QImage.fromData(buf.read())
        return QPixmap.fromImage(qimg)

    def _ordered_images(self) -> list[Image.Image]:
        """Return images in the current list order."""
        images = []
        for i in range(self._list.count()):
            label = self._list.item(i).text().strip()
            for entry_label, img in self._entries:
                if entry_label == label:
                    images.append(img)
                    break
        return images

    def _set_sending(self, sending: bool):
        self._send_btn.setEnabled(not sending)
        self._cancel_btn.setEnabled(not sending)
        self._send_btn.setText("Uploading…" if sending else
                               f"▶▶  Send {self._list.count()} Tile(s) to Device")

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_send(self):
        images = self._ordered_images()
        if not images:
            return

        self._set_sending(True)
        self._progress.setValue(0)
        self._status.setText(f"Uploading {len(images)} tile(s)…")

        device = SmallTVDevice(ip=self._device_ip)
        self._worker = SendAllWorker(device, images, self._interval, self._brightness)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        self._status.setText(f"Uploading {current}/{total}…")

    def _on_finished(self, ok: bool, msg: str):
        self._set_sending(False)
        self._progress.setValue(100 if ok else 0)
        self._status.setText(msg)
        if ok:
            self._status.setStyleSheet("color: #4CAF50; font-size: 11px;")
            # Emit the final label order for the caller to save
            order = [self._list.item(i).text().strip()
                     for i in range(self._list.count())]
            self.order_confirmed.emit(order)
