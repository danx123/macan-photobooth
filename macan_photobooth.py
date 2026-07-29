"""
Macan PhotoBooth
================
Enterprise-grade photobooth application, part of the Macan Angkasa suite.

Layout (dockable -- every panel below can be dragged/resized/floated, and
toggled from the View menu):
    [ Drive Tree | Overlay Preview | Frame Preview ] .. [ Live View ] .. [ EXIF ]
    [                 Frame Template                ] .. [    Filmstrip       ]

Menu bar + toolbar:
    File  -> Start Session, End & Compose, Export/Print, pick output folder,
             Reset Session, Exit.
    View  -> show/hide any panel, plus "Restore Default Layout".
    (The old bottom action-button row was prone to getting clipped by the
    side docks, so those actions now live in a QToolBar, which overflows
    into a ">>" menu instead of cutting text off, plus the File menu.)

Workflow:
    1. Pick a frame template (3-6 photo grid) and camera source.
       - Overlay Preview (beside Drive Tree) shows a raw, as-is look at
         whichever frame/overlay PNG you single-click in the tree, making it
         easy to tell files apart before committing to one.
       - Frame Preview shows a live mockup of the chosen template + overlay
         already composited together, so you know what the final print will
         look like before you shoot.
    2. Pick how many shots to take this session (4-6).
    3. Start the session: Auto Shot (auto-repeats for every remaining shot,
       3-2-1 the first time, then 'Ready' + 3-2-1 for each following take)
       or Manual Shot.
    4. When enough shots are collected, assign them to the template slots
       (auto-filled in order if shot count == slot count).
    5. Export renders a 4R (4x6in) sheet = two DIFFERENT sessions' strips
       side by side ("4R dibagi 2 untuk 2 session"), not one strip
       duplicated. The first session composed sits in the left half with a
       "waiting" placeholder on the right until a second session is
       composed to fill it; then the pair is saved together and the next
       sheet starts fresh.

Panel layout, camera/template/shot-count/overlay selections, and window
geometry are all persisted via QSettings and restored on next launch.
"""

import os
import sys
import uuid
from datetime import datetime
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize, QSettings
from PySide6.QtGui import QImage, QPixmap, QAction, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QComboBox, QSpinBox, QMessageBox, QFileDialog,
    QSplitter, QStatusBar, QToolBar, QSizePolicy, QGroupBox, QFormLayout,
    QDockWidget, QMenu,
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from macan_pb_style import CHARCOAL_QSS, ACCENT
from macan_pb_templates import TEMPLATES, get_template, render_strip, render_sheet, overlay_frame
from macan_pb_widgets import (
    CameraWorker, list_available_cameras, LiveViewWidget, FilmstripWidget,
    DriveTreePanel, ExifPanel, TemplateSelectorPanel, TemplatePreviewPanel,
    OverlayPreviewPanel, ComposeDialog, AboutDialog, HeaderFooterDialog,
)

APP_ORG = "MacanAngkasa"
APP_NAME = "MacanPhotoBooth"
APP_TITLE = "Macan PhotoBooth"
APP_VERSION = "v1.0"

DEFAULT_HEADER_TEXT = "MACAN PHOTOBOOTH"
DEFAULT_FOOTER_TEXT = "macan angkasa"

AUTO_SHOT_COUNTDOWN_SECS = 3
AUTO_SHOT_GAP_MS = 700  # pause between a capture finishing and the next 'Ready' countdown


class SessionState(Enum):
    """Explicit session lifecycle, replacing a pair of loosely-coupled
    booleans (`session_active` / `_auto_running`) that used to have to be
    kept in sync by hand at every call site.

    IDLE             -> no session running; Start Session is the only valid
                        action (besides setup: camera/template/overlay).
    ACTIVE           -> session started, waiting for a shot; Manual Shot and
                        Auto Shot are both valid.
    COUNTDOWN        -> a 3-2-1 (auto-shot) countdown is running; shooting
                        actions are blocked until it finishes.
    READY_TO_COMPOSE -> target shot count reached; only End & Compose is
                        valid until it's called.
    COMPOSED         -> the session was composed into a strip; Start Session
                        (for the paired 2nd session) or Export/Print are
                        valid next.
    """
    IDLE = auto()
    ACTIVE = auto()
    COUNTDOWN = auto()
    READY_TO_COMPOSE = auto()
    COMPOSED = auto()


def get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def default_output_dir() -> str:
    path = os.path.join(get_app_dir(), "PhotoBooth_Output")
    os.makedirs(path, exist_ok=True)
    return path


def panel_frame(title: str, content: QWidget) -> QFrame:
    """Wrap any widget in the standard titled panel chrome (still used inside
    dock widgets / the central widget for a consistent look)."""
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    if title:
        title_label = QLabel(title)
        title_label.setObjectName("panelTitle")
        layout.addWidget(title_label)
    layout.addWidget(content)
    return frame


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 720)
        self.setDockOptions(
            QMainWindow.AnimatedDocks | QMainWindow.AllowNestedDocks
            | QMainWindow.AllowTabbedDocks
        )
        icon_path = "camera.ico"
        if hasattr(sys, "_MEIPASS"):
            icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings(APP_ORG, APP_NAME)
        self.output_dir = self.settings.value("output_dir", default_output_dir())
        os.makedirs(self.output_dir, exist_ok=True)

        self.camera_worker: CameraWorker | None = None
        self.frame_overlay_path: str | None = None
        self.frame_overlay_pixmap: QPixmap | None = None
        self.header_text: str = DEFAULT_HEADER_TEXT
        self.footer_text: str = DEFAULT_FOOTER_TEXT
        self.session_state = SessionState.IDLE
        self.session_id = None
        self.session_dir = None
        self.shots_taken: list[QPixmap] = []
        self.shots_target = 4
        self.countdown_value = 0
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._tick_countdown)
        self._auto_running = False
        self._countdown_prefix = ""

        # Up to 2 composed session strips waiting to be printed together on
        # one 4R sheet ("4R dibagi 2 untuk 2 session").
        self.pair_strips: list[dict] = []
        self.current_strip: Optional[QPixmap] = None
        self.current_sheet: Optional[QPixmap] = None

        self._build_ui()
        self._setup_remote_shutter_shortcuts()
        self._populate_cameras()
        self._load_persisted_settings()
        self._refresh_shot_count_range()
        self._update_exif_static()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        # ---- Central widget: setup bar + live view + shot controls -------
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        setup_bar = self._build_setup_bar()
        root.addWidget(setup_bar)

        self.live_view = LiveViewWidget()

        controls_row = QHBoxLayout()
        self.btn_auto = QPushButton("Auto Shot with Timer")
        self.btn_auto.setObjectName("primaryButton")
        self.btn_auto.clicked.connect(self._start_auto_shot)

        self.btn_manual = QPushButton("Manual Shot")
        self.btn_manual.setToolTip(
            "Shortcut: Space / Enter, or camera remote shutter button "
            "(Volume Up/Down, Page Up/Down, Media Play) -- no need to click the mouse."
        )
        self.btn_manual.clicked.connect(self._manual_shot)

        for b in (self.btn_auto, self.btn_manual):
            b.setMinimumHeight(46)
            b.setEnabled(False)
        controls_row.addWidget(self.btn_auto)
        controls_row.addWidget(self.btn_manual)

        center_col = QVBoxLayout()
        center_col.setSpacing(8)
        center_col.addWidget(self.live_view, stretch=1)
        center_col.addLayout(controls_row)
        center_widget = QWidget()
        center_widget.setLayout(center_col)
        live_panel = panel_frame("LIVE VIEW", center_widget)
        root.addWidget(live_panel, stretch=1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready. Select a frame template & camera, then start the session.")

        # ---- Dockable panels ------------------------------------------------
        self.drive_tree = DriveTreePanel()
        self.drive_tree.frameImageSelected.connect(self._on_frame_overlay_selected)
        self.drive_tree.frameImagePreviewRequested.connect(self._on_frame_overlay_preview)
        self.dock_drive = self._make_dock("DRIVE TREE", "dockDriveTree", self.drive_tree)

        # Beside the Drive Tree: a raw preview of whatever overlay PNG was
        # just clicked, so it's easy to tell files apart before applying one.
        self.overlay_preview = OverlayPreviewPanel()
        self.dock_overlay_preview = self._make_dock(
            "OVERLAY PREVIEW", "dockOverlayPreview", self.overlay_preview
        )

        self.template_preview = TemplatePreviewPanel()
        self.dock_preview = self._make_dock("FRAME PREVIEW", "dockFramePreview", self.template_preview)

        self.exif_panel = ExifPanel()
        self.dock_exif = self._make_dock("EXIF METADATA", "dockExif", self.exif_panel)

        # Frame Template moved down to sit alongside the Filmstrip.
        self.template_selector = TemplateSelectorPanel()
        self.template_selector.templateChosen.connect(self._on_template_changed)
        self.dock_template_selector = self._make_dock(
            "FRAME TEMPLATE", "dockTemplateSelector", self.template_selector
        )

        self.filmstrip = FilmstripWidget()
        self.dock_filmstrip = self._make_dock("FILMSTRIP", "dockFilmstrip", self.filmstrip)

        # Bottom corners default to the side dock areas, which is what made
        # the Filmstrip look squeezed/pushed down before -- hand them to the
        # bottom area instead so Filmstrip runs the full window width.
        self.setCorner(Qt.BottomLeftCorner, Qt.BottomDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)

        # Left column: Drive Tree alone, wide, full height.
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_drive)

        # Right column: Overlay Preview, Exif Metadata, Frame Template, and
        # Frame Preview all tabbed together, with Overlay Preview up front.
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_overlay_preview)
        self.tabifyDockWidget(self.dock_overlay_preview, self.dock_exif)
        self.tabifyDockWidget(self.dock_exif, self.dock_template_selector)
        self.tabifyDockWidget(self.dock_template_selector, self.dock_preview)
        self.dock_overlay_preview.raise_()

        # Bottom: Filmstrip alone, spanning the full width.
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_filmstrip)

        self.resizeDocks([self.dock_drive], [260], Qt.Horizontal)
        self.resizeDocks([self.dock_overlay_preview], [340], Qt.Horizontal)
        self.resizeDocks([self.dock_filmstrip], [110], Qt.Vertical)

        # ---- Menu bar + toolbar ---------------------------------------------
        # (built last so View menu can reference the docks above, and so the
        # session-control actions that used to crowd/clip the setup bar live
        # in a toolbar that overflows gracefully instead of getting cut off)
        self._build_menu_and_toolbar()

        # Snapshot the just-built layout so "Restore Default Layout" has
        # something to go back to, before any persisted settings are applied.
        self._default_window_state = self.saveState()
        self._default_window_geometry = self.saveGeometry()

    def _make_dock(self, title: str, object_name: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(object_name)  # required for saveState()/restoreState() to work
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        dock.dockLocationChanged.connect(lambda *_: self._save_persisted_settings())
        return dock

    def _build_setup_bar(self) -> QFrame:
        """Just the controls picked before/while shooting (camera + shot
        count). Session actions (Start/End/Export/Reset/Output folder) live
        in the File menu + toolbar instead -- keeping this bar short means it
        never gets squeezed and clipped by the side docks."""
        bar = QFrame()
        bar.setObjectName("panel")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        layout.addWidget(QLabel("Camera Source:"))
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self._on_camera_selected)
        layout.addWidget(self.camera_combo)

        self.btn_refresh_cams = QPushButton("Refresh")
        self.btn_refresh_cams.clicked.connect(self._populate_cameras)
        layout.addWidget(self.btn_refresh_cams)

        layout.addSpacing(20)
        layout.addWidget(QLabel("Shot Count:"))
        self.shot_count_combo = QComboBox()
        for n in (4, 5, 6):
            self.shot_count_combo.addItem(f"{n} take", n)
        self.shot_count_combo.currentIndexChanged.connect(self._refresh_shot_count_range)
        layout.addWidget(self.shot_count_combo)

        layout.addStretch(1)
        return bar

    def _build_menu_and_toolbar(self):
        # ---- Shared actions (used by both the File menu and the toolbar) --
        self.btn_start_session = QAction("Start Session", self)
        self.btn_start_session.triggered.connect(self._start_session)

        self.btn_end_session = QAction("End && Compose", self)
        self.btn_end_session.setEnabled(False)
        self.btn_end_session.triggered.connect(self._end_session_and_compose)

        self.btn_export = QAction("Export / Print", self)
        self.btn_export.setEnabled(False)
        self.btn_export.triggered.connect(self._export_and_print)

        self.btn_reset = QAction("Reset Session", self)
        self.btn_reset.triggered.connect(self._reset_session)

        self.btn_choose_output = QAction("Select Output Folder…", self)
        self.btn_choose_output.triggered.connect(self._choose_output_dir)

        self.btn_set_header_footer = QAction("Set Header/Footer…", self)
        self.btn_set_header_footer.triggered.connect(self._set_header_footer)

        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)

        # ---- Menu bar --------------------------------------------------------
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.btn_start_session)
        file_menu.addAction(self.btn_end_session)
        file_menu.addAction(self.btn_export)
        file_menu.addSeparator()
        file_menu.addAction(self.btn_choose_output)
        file_menu.addAction(self.btn_set_header_footer)
        file_menu.addSeparator()
        file_menu.addAction(self.btn_reset)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)

        view_menu = menubar.addMenu("&View")
        for dock in (
            self.dock_drive, self.dock_overlay_preview, self.dock_preview,
            self.dock_exif, self.dock_template_selector, self.dock_filmstrip,
        ):
            view_menu.addAction(dock.toggleViewAction())

        view_menu.addSeparator()
        act_restore_layout = QAction("Restore Default Layout", self)
        act_restore_layout.triggered.connect(self._restore_default_layout)
        view_menu.addAction(act_restore_layout)

        about_menu = menubar.addMenu("&About")
        act_about = QAction(f"About {APP_TITLE}", self)
        act_about.triggered.connect(self._show_about_dialog)
        about_menu.addAction(act_about)

        # ---- Toolbar (same actions as File menu, for one-click access) -----
        toolbar = QToolBar("Session Controls", self)
        toolbar.setObjectName("sessionToolbar")  # required for saveState()/restoreState()
        toolbar.setMovable(False)
        toolbar.addAction(self.btn_start_session)
        toolbar.addAction(self.btn_end_session)
        toolbar.addAction(self.btn_export)
        toolbar.addSeparator()
        toolbar.addAction(self.btn_reset)
        toolbar.addAction(self.btn_choose_output)
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        view_menu.addAction(toolbar.toggleViewAction())

    def _restore_default_layout(self):
        self.restoreState(self._default_window_state)
        self.statusBar().showMessage("Window layout is restored to default.")

    def _show_about_dialog(self):
        dialog = AboutDialog(APP_TITLE, APP_VERSION, accent=ACCENT, parent=self)
        dialog.exec()

    def _set_header_footer(self):
        """File > Set Header/Footer… -- lets the user override the brand
        text printed at the top of the strip and the small text printed at
        the bottom. Persisted via QSettings and applied to every strip
        composed from now on (see render_strip in macan_pb_templates.py)."""
        dialog = HeaderFooterDialog(self.header_text, self.footer_text, parent=self)
        if dialog.exec() != HeaderFooterDialog.Accepted:
            return
        self.header_text = dialog.header_text() or DEFAULT_HEADER_TEXT
        self.footer_text = dialog.footer_text() or DEFAULT_FOOTER_TEXT
        self._save_persisted_settings()
        self.statusBar().showMessage("Header/Footer updated. Applies to strips composed from now on.")

    def _setup_remote_shutter_shortcuts(self):
        """Wire up common Bluetooth/USB camera-shutter remotes so Manual Shot
        can be triggered without touching the mouse. Most cheap shutter
        remotes (e.g. the classic 'AB Shutter3' style) just emulate a
        keyboard press -- usually Volume Up/Down, Page Up/Down, or
        Enter/Space -- so binding all of them covers the common models plus
        a plain keyboard/Space for anyone testing without a remote."""
        remote_keys = [
            Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter,
            Qt.Key_VolumeUp, Qt.Key_VolumeDown,
            Qt.Key_PageUp, Qt.Key_PageDown,
            Qt.Key_MediaPlay, Qt.Key_MediaTogglePlayPause,
        ]
        self._remote_shutter_shortcuts = []
        for key in remote_keys:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(self._manual_shot)
            self._remote_shutter_shortcuts.append(shortcut)

    # ------------------------------------------------------------------ #
    # QSettings persistence
    # ------------------------------------------------------------------ #

    def _load_persisted_settings(self):
        saved_slots = self.settings.value("template_slots", TEMPLATES[0].slots, type=int)
        if saved_slots in self.template_selector._buttons:
            self.template_selector._buttons[saved_slots].setChecked(True)
            self._on_template_changed(saved_slots)

        saved_shots = self.settings.value("shot_count", 4, type=int)
        idx = self.shot_count_combo.findData(saved_shots)
        if idx >= 0:
            self.shot_count_combo.setCurrentIndex(idx)

        saved_cam = self.settings.value("camera_index", None)
        if saved_cam is not None:
            idx = self.camera_combo.findData(int(saved_cam))
            if idx >= 0:
                self.camera_combo.setCurrentIndex(idx)

        self.header_text = self.settings.value("header_text", DEFAULT_HEADER_TEXT) or DEFAULT_HEADER_TEXT
        self.footer_text = self.settings.value("footer_text", DEFAULT_FOOTER_TEXT) or DEFAULT_FOOTER_TEXT

        saved_overlay = self.settings.value("overlay_path", "")
        if saved_overlay and os.path.exists(saved_overlay):
            pixmap = QPixmap(saved_overlay)
            if not pixmap.isNull():
                self.frame_overlay_path = saved_overlay
                self.frame_overlay_pixmap = pixmap
                self.drive_tree.set_overlay_label_from_path(saved_overlay)
                self.exif_panel.update_field("overlay", os.path.basename(saved_overlay))
                self.template_preview.update_preview(
                    get_template(self.template_selector.selected_slots()),
                    self.frame_overlay_pixmap, accent=ACCENT,
                )
                self.overlay_preview.show_preview(saved_overlay)

        geometry = self.settings.value("window_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("window_state")
        if state is not None:
            self.restoreState(state)

    def _save_persisted_settings(self):
        self.settings.setValue("template_slots", self.template_selector.selected_slots())
        shot_count = self.shot_count_combo.currentData()
        if shot_count is not None:
            self.settings.setValue("shot_count", shot_count)
        cam_idx = self.camera_combo.currentData()
        if cam_idx is not None:
            self.settings.setValue("camera_index", cam_idx)
        self.settings.setValue("overlay_path", self.frame_overlay_path or "")
        self.settings.setValue("header_text", self.header_text)
        self.settings.setValue("footer_text", self.footer_text)

    # ------------------------------------------------------------------ #
    # Camera handling
    # ------------------------------------------------------------------ #

    def _populate_cameras(self):
        self.statusBar().showMessage("Looking for a camera…")
        QApplication.processEvents()
        cams = list_available_cameras()
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        for idx in cams:
            self.camera_combo.addItem(f"Camera {idx}", idx)
        self.camera_combo.blockSignals(False)
        self.statusBar().showMessage(f"Founded {len(cams)} camera.")
        if cams:
            self._on_camera_selected(0)

    def _on_camera_selected(self, _index: int):
        if self.camera_worker is not None:
            self.camera_worker.frameReady.disconnect(self.live_view.set_frame)
            self.camera_worker.stop()
            self.camera_worker = None

        cam_index = self.camera_combo.currentData()
        if cam_index is None:
            return

        self.camera_worker = CameraWorker(cam_index)
        self.camera_worker.frameReady.connect(self.live_view.set_frame)
        self.camera_worker.error.connect(self._on_camera_error)
        self.camera_worker.started_ok.connect(self._on_camera_started)
        self.camera_worker.start()
        self._save_persisted_settings()

    def _on_camera_started(self, w: int, h: int):
        self.exif_panel.update_field("camera", self.camera_combo.currentText())
        self.exif_panel.update_field("resolution", f"{w} x {h}")
        self.btn_start_session.setEnabled(True)
        self.statusBar().showMessage("Camera is active. Ready to start session.")

    def _on_camera_error(self, message: str):
        self.live_view.set_idle_text(message)
        self.btn_start_session.setEnabled(False)
        QMessageBox.warning(self, APP_TITLE, message)

    # ------------------------------------------------------------------ #
    # Template / shot-count setup
    # ------------------------------------------------------------------ #

    def _on_template_changed(self, slots: int):
        template = get_template(slots)
        self.exif_panel.update_field("template", template.name)
        self.template_preview.update_preview(template, self.frame_overlay_pixmap, accent=ACCENT)
        self._refresh_shot_count_range()
        self._save_persisted_settings()

    def _refresh_shot_count_range(self, *_args):
        slots = self.template_selector.selected_slots()
        # shot count must be at least the number of slots
        target = self.shot_count_combo.currentData() or 4
        if target < slots:
            target = slots
        self.shots_target = target
        self.exif_panel.update_field("shots", f"0 / {self.shots_target}")
        self._save_persisted_settings()

    def _update_exif_static(self):
        self.exif_panel.update_field("template", get_template(self.template_selector.selected_slots()).name)
        self.exif_panel.update_field("output", self.output_dir)
        if not self.frame_overlay_path:
            self.exif_panel.update_field("overlay", "(none)")

    def _on_frame_overlay_preview(self, path: str):
        """Single-click in the Drive Tree: just show the raw file in the
        Overlay Preview panel beside it -- doesn't apply anything yet."""
        self.overlay_preview.show_preview(path)

    def _on_frame_overlay_selected(self, path: str):
        template = get_template(self.template_selector.selected_slots())

        if not path:
            self.frame_overlay_path = None
            self.frame_overlay_pixmap = None
            self.exif_panel.update_field("overlay", "(none)")
            self.template_preview.update_preview(template, None, accent=ACCENT)
            self.overlay_preview.clear_preview()
            self.statusBar().showMessage("Overlay frame removed.")
            self._save_persisted_settings()
            return

        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, APP_TITLE, f"Failed to open image:\n{path}")
            return

        self.frame_overlay_path = path
        self.frame_overlay_pixmap = pixmap
        self.exif_panel.update_field("overlay", os.path.basename(path))
        self.template_preview.update_preview(template, pixmap, accent=ACCENT)
        self.overlay_preview.show_preview(path)
        self.statusBar().showMessage(
            f"Frame overlay '{os.path.basename(path)}' selected — will auto-apply when composing."
        )
        self._save_persisted_settings()

    def _choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.output_dir)
        if path:
            self.output_dir = path
            self.settings.setValue("output_dir", path)
            self.exif_panel.update_field("output", path)

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #

    def _start_session(self):
        if self.camera_worker is None:
            QMessageBox.warning(self, APP_TITLE, "Camera is not active.")
            return
        if self.session_state not in (SessionState.IDLE, SessionState.COMPOSED):
            # A session is already in progress -- ignore duplicate triggers
            # (e.g. a stray remote/keyboard event) instead of clobbering it.
            return

        self.session_state = SessionState.ACTIVE
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        self.session_dir = os.path.join(self.output_dir, self.session_id)
        os.makedirs(self.session_dir, exist_ok=True)

        self.shots_taken = []
        self.shots_target = self.shot_count_combo.currentData() or 4
        slots = self.template_selector.selected_slots()
        if self.shots_target < slots:
            self.shots_target = slots

        self.filmstrip.clear_shots()
        self.template_selector.set_enabled_all(False)
        self.camera_combo.setEnabled(False)
        self.shot_count_combo.setEnabled(False)

        self.btn_start_session.setEnabled(False)
        self.btn_auto.setEnabled(True)
        self.btn_manual.setEnabled(True)
        self.btn_end_session.setEnabled(False)

        pair_slot = len(self.pair_strips) + 1
        self.exif_panel.update_many({
            "session": f"{self.session_id} (sheet 4R: sesi {pair_slot}/2)",
            "shots": f"0 / {self.shots_target}",
            "output": self.session_dir,
        })
        self.statusBar().showMessage(
            f"Session dimulai. Template: {get_template(slots).name}. Target: {self.shots_target} shot."
        )

    def _start_auto_shot(self):
        """Runs the whole remaining shot count automatically: 3-2-1 for the
        very first take of the session, then 'Ready' + 3-2-1 for every take
        after that, with a short pause between each capture."""
        if self.session_state != SessionState.ACTIVE:
            return
        self._auto_running = True
        self.btn_auto.setEnabled(False)
        self.btn_manual.setEnabled(False)
        first_take = len(self.shots_taken) == 0
        self._begin_countdown(first=first_take)

    def _begin_countdown(self, first: bool):
        self.session_state = SessionState.COUNTDOWN
        self._countdown_prefix = "" if first else "Ready"
        self.countdown_value = AUTO_SHOT_COUNTDOWN_SECS
        self._show_current_countdown()
        self.countdown_timer.start(1000)

    def _show_current_countdown(self):
        self.live_view.show_countdown(str(self.countdown_value), prefix=self._countdown_prefix)

    def _tick_countdown(self):
        self.countdown_value -= 1
        if self.countdown_value > 0:
            self._show_current_countdown()
            return

        self.countdown_timer.stop()
        self.live_view.hide_countdown()
        # _capture_shot() advances session_state to READY_TO_COMPOSE itself
        # once the target shot count is reached.
        self._capture_shot()

        if self.session_state == SessionState.READY_TO_COMPOSE or not self._auto_running:
            self._auto_running = False
            if self.session_state == SessionState.COUNTDOWN:
                self.session_state = SessionState.ACTIVE
            still_active = self.session_state == SessionState.ACTIVE
            self.btn_auto.setEnabled(still_active)
            self.btn_manual.setEnabled(still_active)
        else:
            # More shots still needed for this session -- automatically queue
            # the next take: 'Ready' then 3-2-1 again.
            self.session_state = SessionState.ACTIVE  # transient, until the next countdown begins
            QTimer.singleShot(AUTO_SHOT_GAP_MS, lambda: self._begin_countdown(first=False))

    def _manual_shot(self):
        if self.session_state != SessionState.ACTIVE:
            return
        self._auto_running = False
        self._capture_shot()

    def _capture_shot(self):
        if self.camera_worker is None:
            return
        image = self.camera_worker.grab_still()
        if image is None:
            QMessageBox.warning(self, APP_TITLE, "No frames from the camera yet, please try again..")
            return

        self.live_view.flash()
        pixmap = QPixmap.fromImage(image)
        self.shots_taken.append(pixmap)

        shot_no = len(self.shots_taken)
        label = f"Shot #{shot_no}"
        self.filmstrip.add_shot(pixmap, label)

        if self.session_dir:
            path = os.path.join(self.session_dir, f"shot_{shot_no:02d}.png")
            image.save(path, "PNG")

        self.exif_panel.update_many({
            "shots": f"{shot_no} / {self.shots_target}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.statusBar().showMessage(f"Shot #{shot_no} saved.")

        if self._is_done():
            self.session_state = SessionState.READY_TO_COMPOSE
            self.btn_auto.setEnabled(False)
            self.btn_manual.setEnabled(False)
            self.btn_end_session.setEnabled(True)
            self.statusBar().showMessage(
                f"Target {self.shots_target} shot achieved. Click 'End & Compose' to continue."
            )

    def _is_done(self) -> bool:
        return len(self.shots_taken) >= self.shots_target

    def _end_session_and_compose(self):
        if self.session_state != SessionState.READY_TO_COMPOSE:
            return

        slots = self.template_selector.selected_slots()
        template = get_template(slots)

        if len(self.shots_taken) == 0:
            QMessageBox.warning(self, APP_TITLE, "No shots have been taken yet.")
            return

        if len(self.shots_taken) == template.slots:
            chosen = list(self.shots_taken)
        else:
            dialog = ComposeDialog(template, self.shots_taken, self)
            if dialog.exec() != ComposeDialog.Accepted:
                self.statusBar().showMessage("Drafting cancelled.")
                return
            chosen = dialog.chosen_pixmaps()

        self.current_strip = render_strip(
            template, chosen, accent=ACCENT,
            brand_text=self.header_text, footer_text=self.footer_text,
        )

        overlay_note = ""
        if self.frame_overlay_pixmap is not None:
            self.current_strip = overlay_frame(self.current_strip, self.frame_overlay_pixmap)
            overlay_note = f" (frame overlay '{os.path.basename(self.frame_overlay_path)}' auto-applied)"

        # A new pair always starts fresh once the previous pair was exported
        # (pair_strips is cleared after export); if not yet exported and
        # already has 2, replace it defensively.
        if len(self.pair_strips) >= 2:
            self.pair_strips = []
        self.pair_strips.append({"strip": self.current_strip, "session_id": self.session_id})
        self._rebuild_pair_sheet()

        pair_slot = len(self.pair_strips)
        self.btn_end_session.setEnabled(False)
        self.btn_export.setEnabled(True)
        self.session_state = SessionState.COMPOSED
        self.exif_panel.update_field(
            "session", f"{self.session_id} (sheet 4R: sesi {pair_slot}/2)"
        )
        if pair_slot < 2:
            self.statusBar().showMessage(
                f"Composition session 1/2 complete{overlay_note}. Start the session again for the 2nd session, "
                f"or Export now to print session 1 only."
            )
        else:
            self.statusBar().showMessage(
                f"Composition session 2/2 finished{overlay_note}. Complete 4R sheet, ready to export/print."
            )

    def _rebuild_pair_sheet(self):
        if len(self.pair_strips) == 0:
            self.current_sheet = None
            return
        strip_left = self.pair_strips[0]["strip"]
        strip_right = self.pair_strips[1]["strip"] if len(self.pair_strips) > 1 else None
        self.current_sheet = render_sheet(strip_left, strip_right)

    def _export_and_print(self):
        if self.current_sheet is None:
            return

        sheet_id = "_".join(s["session_id"] for s in self.pair_strips) or (self.session_id or "sheet")
        out_path = os.path.join(self.output_dir, f"{sheet_id}_4R.png")
        self.current_sheet.save(out_path, "PNG")
        self.exif_panel.update_field("output", out_path)

        complete_pair = len(self.pair_strips) >= 2
        if complete_pair:
            self.statusBar().showMessage(f"Sheet 4R (2 sessions) saved: {out_path}")
        else:
            self.statusBar().showMessage(
                f"Sheet 4R (sessions 1/2, waiting for the 2nd session) saved: {out_path}"
            )

        answer = QMessageBox.question(
            self, APP_TITLE,
            f"Sheet 4R saved in:\n{out_path}\n\nPrint now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._print_sheet()

        if complete_pair:
            # This 4R sheet is done -- start a fresh pair for the next print.
            self.pair_strips = []
            self.current_sheet = None
            self.btn_export.setEnabled(False)

    def _print_sheet(self):
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.Accepted:
            return
        from PySide6.QtGui import QPainter as _QPainter
        painter = _QPainter(printer)
        page_rect = printer.pageRect(QPrinter.DevicePixel)
        scaled = self.current_sheet.scaled(
            int(page_rect.width()), int(page_rect.height()),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        x = (page_rect.width() - scaled.width()) / 2
        y = (page_rect.height() - scaled.height()) / 2
        painter.drawPixmap(int(x), int(y), scaled)
        painter.end()
        self.statusBar().showMessage("Sent to printer.")

    def _reset_session(self):
        """Hard reset: clears the in-progress session AND any composed pair
        waiting to be printed."""
        self.countdown_timer.stop()
        self._auto_running = False
        self.live_view.hide_countdown()
        self.session_state = SessionState.IDLE
        self.shots_taken = []
        self.current_strip = None
        self.current_sheet = None
        self.pair_strips = []
        self.filmstrip.clear_shots()
        self.template_selector.set_enabled_all(True)
        self.camera_combo.setEnabled(True)
        self.shot_count_combo.setEnabled(True)
        self.btn_start_session.setEnabled(self.camera_worker is not None)
        self.btn_auto.setEnabled(False)
        self.btn_manual.setEnabled(False)
        self.btn_end_session.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.exif_panel.update_many({
            "session": "-", "shots": f"0 / {self.shots_target}",
            "timestamp": "-",
        })
        self.statusBar().showMessage("Session reset.")

    # ------------------------------------------------------------------ #
    def closeEvent(self, event):
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        self._save_persisted_settings()
        if self.camera_worker is not None:
            self.camera_worker.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(CHARCOAL_QSS)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
