"""
macan_pb_widgets.py
Reusable widgets for Macan PhotoBooth: camera capture thread, live view with
countdown overlay, filmstrip, drive tree, exif/metadata panel, frame
template selector, and the shot-to-slot compose dialog.
"""

import os
import time
import threading
from typing import List, Optional

import cv2
from PySide6.QtCore import Qt, QThread, Signal, QRect, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon, QFont, QPainter, QColor
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
    QListWidget, QListWidgetItem, QTreeView, QFileSystemModel, QButtonGroup,
    QDialog, QComboBox, QFormLayout, QDialogButtonBox, QSizePolicy,
    QGraphicsDropShadowEffect, QHeaderView, QLineEdit,
)

from macan_pb_templates import TEMPLATES, FrameTemplate, render_template_thumbnail


# --------------------------------------------------------------------------- #
# Camera
# --------------------------------------------------------------------------- #

def list_available_cameras(max_test: int = 6) -> List[int]:
    """Probe camera indices 0..max_test-1 and return the ones that open."""
    found = []
    for idx in range(max_test):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
        if cap is not None and cap.isOpened():
            ok, _ = cap.read()
            if ok:
                found.append(idx)
        cap.release()
    return found or [0]


class CameraWorker(QThread):
    """Continuously grabs frames from a cv2.VideoCapture on its own thread."""

    frameReady = Signal(QImage)
    error = Signal(str)
    started_ok = Signal(int, int)  # width, height

    def __init__(self, camera_index: int = 0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self._capture: Optional[cv2.VideoCapture] = None
        self._latest_frame = None  # BGR ndarray, for capture-on-demand
        # _latest_frame is written from this thread's run() loop and read
        # from grab_still() on the main/GUI thread -- guard it so a still
        # capture can never observe a half-updated reference.
        self._frame_lock = threading.Lock()

    def run(self):
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        self._capture = cv2.VideoCapture(self.camera_index, backend)
        if not self._capture.isOpened():
            self.error.emit(f"Can't open index camera {self.camera_index}")
            return

        w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
        self.started_ok.emit(w, h)

        self._running = True
        while self._running:
            ok, frame = self._capture.read()
            if not ok:
                self.msleep(20)
                continue
            with self._frame_lock:
                self._latest_frame = frame
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h_, w_, ch = rgb.shape
            qimg = QImage(rgb.data, w_, h_, ch * w_, QImage.Format_RGB888).copy()
            self.frameReady.emit(qimg)
            self.msleep(16)  # ~60fps cap, actual rate limited by camera

        if self._capture:
            self._capture.release()

    def grab_still(self) -> Optional[QImage]:
        """Return the most recent frame as a high-quality QImage snapshot."""
        with self._frame_lock:
            frame = self._latest_frame
        if frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h_, w_, ch = rgb.shape
        return QImage(rgb.data, w_, h_, ch * w_, QImage.Format_RGB888).copy()

    def stop(self):
        self._running = False
        self.wait(1500)


# --------------------------------------------------------------------------- #
# Live view + countdown overlay
# --------------------------------------------------------------------------- #

class LiveViewWidget(QFrame):
    """Central live-view panel. Shows the camera feed with a large centered
    countdown overlay for the auto-shot timer, and a brief flash on capture."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("liveViewFrame")
        self.setMinimumSize(480, 360)

        self.video_label = QLabel(self)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("Camera is not active")
        self.video_label.setStyleSheet("color:#666666; font-size:16px; background: transparent;")

        self.countdown_label = QLabel(self)
        self.countdown_label.setObjectName("countdownLabel")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.hide()

        self.ready_label = QLabel(self)
        self.ready_label.setObjectName("readyLabel")
        self.ready_label.setAlignment(Qt.AlignCenter)
        self.ready_label.hide()

        self.flash_overlay = QWidget(self)
        self.flash_overlay.setStyleSheet("background-color: white;")
        self.flash_overlay.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_label)

        self._current_pixmap: Optional[QPixmap] = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.rect()
        ready_h = int(rect.height() * 0.16)
        self.ready_label.setGeometry(rect.x(), rect.y(), rect.width(), ready_h)
        self.countdown_label.setGeometry(rect.x(), rect.y() + ready_h,
                                          rect.width(), rect.height() - ready_h)
        self.flash_overlay.setGeometry(self.rect())
        if self._current_pixmap is not None:
            self._rescale()

    def set_frame(self, image: QImage):
        self._current_pixmap = QPixmap.fromImage(image)
        self._rescale()

    def _rescale(self):
        scaled = self._current_pixmap.scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.video_label.setPixmap(scaled)

    def show_countdown(self, value: str, prefix: str = ""):
        """Show the big countdown number. On the first take of an auto-shot
        sequence `prefix` is empty (plain 3-2-1). On subsequent takes
        `prefix` is 'Ready' so the person knows another shot is coming
        (Ready, then 3-2-1 again)."""
        self.countdown_label.setText(value)
        self.countdown_label.show()
        self.countdown_label.raise_()
        if prefix:
            self.ready_label.setText(prefix)
            self.ready_label.show()
            self.ready_label.raise_()
        else:
            self.ready_label.hide()

    def hide_countdown(self):
        self.countdown_label.hide()
        self.ready_label.hide()

    def flash(self):
        self.flash_overlay.setWindowOpacity(1.0)
        self.flash_overlay.show()
        self.flash_overlay.raise_()
        QTimer.singleShot(120, self.flash_overlay.hide)

    def set_idle_text(self, text: str):
        self.video_label.setPixmap(QPixmap())
        self.video_label.setText(text)


# --------------------------------------------------------------------------- #
# Filmstrip
# --------------------------------------------------------------------------- #

class FilmstripWidget(QListWidget):
    """Horizontal strip of thumbnails for every shot taken this session."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(90, 90))
        self.setFixedHeight(110)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(8)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def add_shot(self, pixmap: QPixmap, label: str):
        icon = QIcon(pixmap.scaled(90, 90, Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation))
        item = QListWidgetItem(icon, label)
        item.setData(Qt.UserRole, pixmap)
        item.setTextAlignment(Qt.AlignHCenter)
        self.addItem(item)
        self.scrollToItem(item)

    def all_pixmaps(self) -> List[QPixmap]:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def clear_shots(self):
        self.clear()


# --------------------------------------------------------------------------- #
# Drive tree -- browse all drives/folders to pick a frame/overlay image
# --------------------------------------------------------------------------- #

FRAME_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


class DriveTreePanel(QWidget):
    """Full filesystem tree (all drives, like a normal file explorer) used to
    pick a frame/overlay image (e.g. a decorative border PNG with a
    transparent center). Single-clicking an image file sends a live preview
    (see Overlay Preview panel) so it's easy to check the right file was
    found; double-clicking selects it and the selection is auto-applied on
    top of the composed strip -- no extra confirmation step needed."""

    frameImageSelected = Signal(str)  # absolute path, or "" to clear
    frameImagePreviewRequested = Signal(str)  # absolute path, for raw preview only

    def __init__(self, parent=None):
        super().__init__(parent)

        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.model.setNameFilters([f"*{ext}" for ext in FRAME_IMAGE_EXTS])
        self.model.setNameFilterDisables(False)  # hide non-matching files entirely

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(""))  # "" -> Computer/drives root
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.clicked.connect(self._on_single_clicked)
        self.tree.doubleClicked.connect(self._on_double_clicked)

        # Long file/folder names used to get clipped with "..." because the
        # name column auto-stretched to the panel width. Let the column size
        # itself to the actual content instead, and reveal a horizontal
        # scrollbar so nothing gets silently cut off.
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.setTextElideMode(Qt.ElideNone)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.setHorizontalScrollMode(QTreeView.ScrollPerPixel)

        self.hint_label = QLabel(
            "Click image to preview, double-click to auto-apply\n"
            "to composite result (transparent PNG is recommended)."
        )
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color:#9a9a9a; font-size:11px; padding:6px 6px 2px 6px;")

        self.selected_label = QLabel("Frame overlay: (none)")
        self.selected_label.setWordWrap(True)
        self.selected_label.setStyleSheet("color:#e0a030; font-size:11px; padding:0 6px 4px 6px;")

        self.clear_btn = QPushButton("Clear Overlay")
        self.clear_btn.clicked.connect(self.clear_selection)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.tree, stretch=1)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.selected_label)
        layout.addWidget(self.clear_btn)

    def _on_single_clicked(self, index):
        if self.model.isDir(index):
            return
        path = self.model.filePath(index)
        if path.lower().endswith(FRAME_IMAGE_EXTS):
            self.frameImagePreviewRequested.emit(path)

    def _on_double_clicked(self, index):
        if self.model.isDir(index):
            return
        path = self.model.filePath(index)
        if path.lower().endswith(FRAME_IMAGE_EXTS):
            self.selected_label.setText(f"Frame overlay: {os.path.basename(path)}")
            self.frameImageSelected.emit(path)

    def clear_selection(self):
        self.selected_label.setText("Frame overlay: (none)")
        self.frameImageSelected.emit("")

    def set_overlay_label_from_path(self, path: str):
        """Sync the label text without re-emitting frameImageSelected -- used
        when restoring a persisted overlay selection on startup."""
        if path:
            self.selected_label.setText(f"Frame overlay: {os.path.basename(path)}")
        else:
            self.selected_label.setText("Frame overlay: (none)")

    def refresh(self):
        root = self.model.rootPath()
        self.model.setRootPath("")
        self.model.setRootPath(root)
        self.tree.setRootIndex(self.model.index(""))


# --------------------------------------------------------------------------- #
# EXIF / metadata panel
# --------------------------------------------------------------------------- #

class ExifPanel(QWidget):
    """Shows session / capture metadata. Not real EXIF (source is a live
    camera feed) -- surfaces the equivalent session info instead."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: dict[str, QLabel] = {}
        self.form = QFormLayout(self)
        self.form.setContentsMargins(8, 4, 8, 8)
        self.form.setLabelAlignment(Qt.AlignLeft)

        fields = [
            ("camera", "Camera Source"),
            ("resolution", "Resolution"),
            ("template", "Frame Template"),
            ("overlay", "Frame Overlay"),
            ("shots", "Shots Taken"),
            ("timestamp", "Last Capture"),
            ("session", "Session ID"),
            ("output", "Output Path"),
        ]
        for key, caption in fields:
            key_label = QLabel(caption)
            key_label.setStyleSheet("color:#9a9a9a;")
            val_label = QLabel("-")
            val_label.setWordWrap(True)
            self.rows[key] = val_label
            self.form.addRow(key_label, val_label)

    def update_field(self, key: str, value: str):
        if key in self.rows:
            self.rows[key].setText(value)

    def update_many(self, values: dict):
        for k, v in values.items():
            self.update_field(k, v)


# --------------------------------------------------------------------------- #
# Overlay preview (raw file preview, sits beside the Drive Tree)
# --------------------------------------------------------------------------- #

class OverlayPreviewPanel(QWidget):
    """Raw, contain-fit, checkerboard preview of whichever frame/overlay PNG
    is currently clicked in the Drive Tree. This is a plain look at the file
    itself (transparency included) so it's easy to tell files apart before
    double-clicking to actually apply one -- distinct from the Frame Preview
    panel, which shows the template mockup with the overlay composited on
    top of it."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(140, 200)
        self.preview_label.setStyleSheet("background: transparent;")

        self.caption_label = QLabel("Click on the image in the Drive Tree to preview")
        self.caption_label.setObjectName("framePreviewCaption")
        self.caption_label.setAlignment(Qt.AlignCenter)
        self.caption_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.preview_label, stretch=1)
        layout.addWidget(self.caption_label)

        self._overlay: Optional[QPixmap] = None
        self._path: str = ""

    def show_preview(self, path: str):
        from macan_pb_templates import render_overlay_raw_preview
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.caption_label.setText("Failed to open image.")
            return
        self._overlay = pixmap
        self._path = path
        self._redraw()
        self.caption_label.setText(os.path.basename(path))

    def clear_preview(self):
        self._overlay = None
        self._path = ""
        self.preview_label.setPixmap(QPixmap())
        self.caption_label.setText("Click on the image in the Drive Tree to preview")

    def _redraw(self):
        if self._overlay is None:
            return
        from macan_pb_templates import render_overlay_raw_preview
        size = self.preview_label.size()
        w = max(size.width(), 140)
        h = max(size.height(), 200)
        self.preview_label.setPixmap(render_overlay_raw_preview(self._overlay, w, h))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._redraw()


# --------------------------------------------------------------------------- #
# Frame template preview (replaces the template selector's old top-row slot)
# --------------------------------------------------------------------------- #

class TemplatePreviewPanel(QWidget):
    """Live preview combining the currently selected frame template's slot
    grid with the currently selected frame/overlay image, so the person can
    see what the final print will look like before a single photo is taken.
    Updates whenever the template selection or the overlay changes."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(140, 210)
        self.preview_label.setStyleSheet("background: transparent;")

        self.caption_label = QLabel("Select a template & overlay to see a preview.")
        self.caption_label.setObjectName("framePreviewCaption")
        self.caption_label.setAlignment(Qt.AlignCenter)
        self.caption_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.preview_label, stretch=1)
        layout.addWidget(self.caption_label)

        self._template: Optional[FrameTemplate] = None
        self._overlay: Optional[QPixmap] = None
        self._accent = "#e0a030"

    def update_preview(self, template: FrameTemplate, overlay: Optional[QPixmap] = None,
                        accent: str = "#e0a030"):
        from macan_pb_templates import render_template_preview
        self._template = template
        self._overlay = overlay
        self._accent = accent

        size = self.preview_label.size()
        w = max(size.width(), 140)
        h = max(size.height(), 210)
        pixmap = render_template_preview(template, overlay, w, h, accent)
        self.preview_label.setPixmap(pixmap)

        has_overlay = overlay is not None and not overlay.isNull()
        self.caption_label.setText(
            f"{template.name} ({template.slots} foto)" + (" + frame overlay" if has_overlay else "")
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._template is not None:
            self.update_preview(self._template, self._overlay, self._accent)


# --------------------------------------------------------------------------- #
# Frame template selector
# --------------------------------------------------------------------------- #

class TemplateSelectorPanel(QWidget):
    """Pick the frame layout (3-6 grid) BEFORE the shooting session starts."""

    templateChosen = Signal(int)  # slot count

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(8)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        self._buttons = {}
        for template in TEMPLATES:
            btn = QPushButton()
            btn.setObjectName("templateButton")
            btn.setCheckable(True)
            btn.setIconSize(QSize(96, 144))
            btn.setIcon(QIcon(render_template_thumbnail(template, 96, 144)))
            btn.setText(f"  {template.name} ({template.slots} foto)")
            btn.setLayoutDirection(Qt.LeftToRight)
            btn.setMinimumHeight(60)
            btn.clicked.connect(lambda _=False, t=template.slots: self._on_clicked(t))
            self.group.addButton(btn)
            self._buttons[template.slots] = btn
            layout.addWidget(btn)

        layout.addStretch(1)
        # default selection
        self._buttons[TEMPLATES[0].slots].setChecked(True)

    def _on_clicked(self, slots: int):
        self.templateChosen.emit(slots)

    def selected_slots(self) -> int:
        for slots, btn in self._buttons.items():
            if btn.isChecked():
                return slots
        return TEMPLATES[0].slots

    def set_enabled_all(self, enabled: bool):
        for btn in self._buttons.values():
            btn.setEnabled(enabled)


# --------------------------------------------------------------------------- #
# Compose dialog (assign captured shots to template slots)
# --------------------------------------------------------------------------- #

class ComposeDialog(QDialog):
    """When more shots were taken than there are template slots, let the user
    pick which shot goes in which slot before final composition/printing."""

    def __init__(self, template: FrameTemplate, pixmaps: List[QPixmap], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arrange Shot Results into Frames")
        self.template = template
        self.pixmaps = pixmaps
        self.combos: List[QComboBox] = []

        layout = QVBoxLayout(self)
        info = QLabel(
            f"Template '{template.name}' need {template.slots} photo. "
            f"You have {len(pixmaps)} shots. Select a photo for each slot:"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        for slot_idx in range(template.slots):
            combo = QComboBox()
            for i in range(len(pixmaps)):
                combo.addItem(f"Shot #{i + 1}", i)
            # default: fill sequentially, wrapping if fewer shots than slots
            default_idx = slot_idx % max(len(pixmaps), 1)
            combo.setCurrentIndex(default_idx)
            self.combos.append(combo)
            form.addRow(f"Slot {slot_idx + 1}", combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen_pixmaps(self) -> List[QPixmap]:
        result = []
        for combo in self.combos:
            idx = combo.currentData()
            result.append(self.pixmaps[idx])
        return result


# --------------------------------------------------------------------------- #
# Header/Footer dialog
# --------------------------------------------------------------------------- #

class HeaderFooterDialog(QDialog):
    """Lets the user set the brand/header text and footer text that get
    printed on every rendered strip (see macan_pb_templates.render_strip)."""

    def __init__(self, header_text: str = "", footer_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Header / Footer")
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        info = QLabel(
            "This text is printed directly on the composed strip: the header "
            "sits at the top of every strip, the footer at the bottom."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#9a9a9a; font-size:12px;")
        layout.addWidget(info)

        form = QFormLayout()
        self.header_edit = QLineEdit(header_text)
        self.header_edit.setPlaceholderText("MACAN PHOTOBOOTH")
        self.header_edit.setMaxLength(60)
        form.addRow("Header", self.header_edit)

        self.footer_edit = QLineEdit(footer_text)
        self.footer_edit.setPlaceholderText("macan angkasa")
        self.footer_edit.setMaxLength(60)
        form.addRow("Footer", self.footer_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Ok).setObjectName("primaryButton")
        layout.addWidget(buttons)

    def header_text(self) -> str:
        return self.header_edit.text().strip()

    def footer_text(self) -> str:
        return self.footer_edit.text().strip()


# --------------------------------------------------------------------------- #
# About dialog
# --------------------------------------------------------------------------- #

class AboutDialog(QDialog):
    """Simple branded 'About' dialog, part of the Macan Angkasa app suite."""

    def __init__(self, app_title: str, version: str, accent: str = "#e0a030", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {app_title}")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(6)

        title = QLabel(app_title)
        title.setStyleSheet(f"color:{accent}; font-size:20px; font-weight:800;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        version_label = QLabel(version)
        version_label.setStyleSheet("color:#9a9a9a; font-size:12px;")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        layout.addSpacing(10)

        desc = QLabel(
            "Photobooth application for photo sessions with strip templates, frames "
            "overlay, and automatic 4R print composition."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color:#e6e6e6; font-size:13px;")
        layout.addWidget(desc)

        layout.addSpacing(10)

        credits = QLabel("Part of Macan Angkasa Suite")
        credits.setAlignment(Qt.AlignCenter)
        credits.setStyleSheet("color:#9a9a9a; font-size:11px;")
        layout.addWidget(credits)

        layout.addSpacing(16)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Ok).setObjectName("primaryButton")
        layout.addWidget(buttons)
