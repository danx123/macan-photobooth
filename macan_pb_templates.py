"""
macan_pb_templates.py
Frame template (grid) definitions and the 4R (4x6 inch) sheet compositor.

A "strip" is the single vertical column of N photo slots (classic photobooth
strip). The final printable 4R sheet is that strip duplicated twice, side by
side, on one 4x6 inch page -- i.e. "4R dibagi 2".
"""

from dataclasses import dataclass
from typing import List, Tuple

from PySide6.QtCore import Qt, QRect, QRectF, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QLinearGradient, QBrush

DPI = 300
SHEET_W_IN, SHEET_H_IN = 4.0, 6.0          # 4R paper
STRIP_W_IN, STRIP_H_IN = 2.0, 6.0          # 4R divided by 2 -> two strips

SHEET_W_PX = int(SHEET_W_IN * DPI)         # 1200
SHEET_H_PX = int(SHEET_H_IN * DPI)         # 1800
STRIP_W_PX = int(STRIP_W_IN * DPI)         # 600
STRIP_H_PX = int(STRIP_H_IN * DPI)         # 1800

OUTER_MARGIN = 24
SLOT_GAP = 16
HEADER_H = 70
FOOTER_H = 90


@dataclass
class FrameTemplate:
    slots: int
    name: str

    def slot_rects(self, strip_w: int = STRIP_W_PX, strip_h: int = STRIP_H_PX) -> List[QRect]:
        """Return slot rectangles (in strip pixel space), stacked vertically."""
        usable_h = strip_h - HEADER_H - FOOTER_H - OUTER_MARGIN * 2
        usable_w = strip_w - OUTER_MARGIN * 2
        n = self.slots
        total_gap = SLOT_GAP * (n - 1)
        slot_h = (usable_h - total_gap) // n
        rects = []
        y = HEADER_H + OUTER_MARGIN
        for i in range(n):
            rects.append(QRect(OUTER_MARGIN, y, usable_w, slot_h))
            y += slot_h + SLOT_GAP
        return rects


TEMPLATES: List[FrameTemplate] = [
    FrameTemplate(3, "Classic 3"),
    FrameTemplate(4, "Strip 4"),
    FrameTemplate(5, "Strip 5"),
    FrameTemplate(6, "Strip 6"),
]


def get_template(slots: int) -> FrameTemplate:
    for t in TEMPLATES:
        if t.slots == slots:
            return t
    return TEMPLATES[0]


def render_template_thumbnail(template: FrameTemplate, w: int = 140, h: int = 210,
                              accent: str = "#e0a030") -> QPixmap:
    """Small preview pixmap used on the template-selector buttons."""
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QColor("#1c1c1c"))
    painter.setPen(QPen(QColor("#555555"), 1))
    painter.drawRoundedRect(QRectF(0, 0, w - 1, h - 1), 6, 6)

    scale_x = w / STRIP_W_PX
    scale_y = h / STRIP_H_PX
    for rect in template.slot_rects():
        r = QRectF(rect.x() * scale_x, rect.y() * scale_y,
                    rect.width() * scale_x, rect.height() * scale_y)
        painter.setBrush(QColor("#3a3a3a"))
        painter.setPen(QPen(QColor(accent), 1))
        painter.drawRoundedRect(r, 3, 3)

    painter.end()
    return pm


def render_template_preview(template: FrameTemplate, overlay: QPixmap = None,
                             w: int = 200, h: int = 300, accent: str = "#e0a030") -> QPixmap:
    """Preview pixmap combining the template's slot-grid thumbnail with the
    currently selected frame/overlay image on top, so the user can see how
    the final print will look before shooting even starts."""
    base = render_template_thumbnail(template, w, h, accent)
    if overlay is not None and not overlay.isNull():
        return overlay_frame(base, overlay)
    return base


def render_overlay_raw_preview(overlay: QPixmap, w: int = 200, h: int = 260) -> QPixmap:
    """Contain-fit preview of a raw overlay/frame PNG against a checkerboard
    background so transparent areas are visible. Used by the Drive Tree's
    Overlay Preview panel while browsing files -- unlike the composited
    Frame Preview, this shows the file exactly as-is (not cropped/applied to
    a strip) so it's easier to pick the right file."""
    canvas = QPixmap(w, h)
    canvas.fill(QColor("#1c1c1c"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    tile = 10
    light = QColor("#3a3a3a")
    dark = QColor("#2f2f2f")
    y = 0
    row = 0
    while y < h:
        x = 0
        col = 0
        while x < w:
            painter.fillRect(QRect(x, y, tile, tile), light if (row + col) % 2 == 0 else dark)
            x += tile
            col += 1
        y += tile
        row += 1

    if overlay is not None and not overlay.isNull():
        scaled = overlay.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        ox = (w - scaled.width()) // 2
        oy = (h - scaled.height()) // 2
        painter.drawPixmap(ox, oy, scaled)

    painter.end()
    return canvas


def _draw_cover(painter: QPainter, target: QRect, source: QPixmap):
    """Draw source pixmap into target rect using 'cover' scaling (crop overflow)."""
    if source.isNull():
        return
    src_w, src_h = source.width(), source.height()
    tgt_w, tgt_h = target.width(), target.height()
    src_ratio = src_w / src_h
    tgt_ratio = tgt_w / tgt_h

    if src_ratio > tgt_ratio:
        # source wider than target -> crop left/right
        new_w = int(src_h * tgt_ratio)
        x_off = (src_w - new_w) // 2
        src_rect = QRect(x_off, 0, new_w, src_h)
    else:
        new_h = int(src_w / tgt_ratio)
        y_off = (src_h - new_h) // 2
        src_rect = QRect(0, y_off, src_w, new_h)

    painter.drawPixmap(target, source, src_rect)


def render_strip(template: FrameTemplate, photos: List[QPixmap], accent: str = "#e0a030",
                  brand_text: str = "MACAN PHOTOBOOTH", footer_text: str = "") -> QPixmap:
    """Compose one strip (single column) with the given photos filling the slots."""
    strip = QPixmap(STRIP_W_PX, STRIP_H_PX)
    strip.fill(QColor("#101010"))
    painter = QPainter(strip)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # background panel
    painter.setBrush(QColor("#181818"))
    painter.setPen(Qt.NoPen)
    painter.drawRect(0, 0, STRIP_W_PX, STRIP_H_PX)

    # header brand
    painter.setPen(QColor(accent))
    header_font = QFont("Segoe UI", 22, QFont.Bold)
    painter.setFont(header_font)
    painter.drawText(QRect(0, 10, STRIP_W_PX, HEADER_H - 10), Qt.AlignCenter, brand_text)

    rects = template.slot_rects()
    for i, rect in enumerate(rects):
        painter.setPen(QPen(QColor(accent), 3))
        painter.setBrush(QColor("#000000"))
        painter.drawRoundedRect(rect, 4, 4)
        inner = rect.adjusted(4, 4, -4, -4)
        if i < len(photos) and photos[i] is not None and not photos[i].isNull():
            painter.save()
            path_rect = QRectF(inner)
            painter.setClipRect(inner)
            _draw_cover(painter, inner, photos[i])
            painter.restore()
        else:
            painter.setPen(QColor("#666666"))
            painter.drawText(inner, Qt.AlignCenter, f"#{i + 1}")

    # footer
    painter.setPen(QColor("#8a8a8a"))
    footer_font = QFont("Segoe UI", 11)
    painter.setFont(footer_font)
    text = footer_text or "macan angkasa"
    painter.drawText(QRect(0, STRIP_H_PX - FOOTER_H, STRIP_W_PX, FOOTER_H - 10),
                      Qt.AlignCenter, text)

    painter.end()
    return strip


def overlay_frame(strip: QPixmap, overlay: QPixmap) -> QPixmap:
    """Composite a user-picked frame/overlay image on top of the rendered
    strip. Uses cover-fit scaling so decorative borders/PNG overlays with
    transparency line up with the strip edges regardless of source aspect
    ratio. Auto-applied whenever an overlay is selected in the Drive Tree."""
    if overlay is None or overlay.isNull():
        return strip

    result = QPixmap(strip.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawPixmap(0, 0, strip)
    target = QRect(0, 0, strip.width(), strip.height())
    _draw_cover(painter, target, overlay)
    painter.end()
    return result


def render_sheet(strip_left: QPixmap, strip_right: QPixmap = None) -> QPixmap:
    """4R sheet (4x6in) = two strips side by side, one per session
    ('4R dibagi 2 untuk 2 session'). Each half of the sheet is filled by a
    *different* session's strip rather than duplicating a single session's
    strip. If the second session hasn't been composed yet, the right half
    shows a waiting placeholder so the sheet can still be previewed/exported
    with just the first session if needed."""
    sheet = QPixmap(SHEET_W_PX, SHEET_H_PX)
    sheet.fill(QColor("#ffffff"))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    painter.drawPixmap(0, 0, strip_left)

    if strip_right is not None and not strip_right.isNull():
        painter.drawPixmap(STRIP_W_PX, 0, strip_right)
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#eeeeee"))
        painter.drawRect(STRIP_W_PX, 0, STRIP_W_PX, SHEET_H_PX)
        painter.setPen(QColor("#999999"))
        painter.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
        painter.drawText(QRect(STRIP_W_PX, 0, STRIP_W_PX, SHEET_H_PX), Qt.AlignCenter,
                          "Menunggu\nsession ke-2")

    # cut guide line
    pen = QPen(QColor("#c8c8c8"))
    pen.setStyle(Qt.DashLine)
    pen.setWidth(2)
    painter.setPen(pen)
    painter.drawLine(STRIP_W_PX, 0, STRIP_W_PX, SHEET_H_PX)
    painter.end()
    return sheet
