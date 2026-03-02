"""
Transparent overlay window for Learn With Gemini.
Renders arrows, text boxes, and highlight regions on top of the user's screen.
Click-through so it never interferes with normal interaction.
Also provides a status bar and subtitle display.
"""

import math
import time
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QMenu,
    QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QFont,
    QBrush,
    QPainterPath,
    QPolygonF,
    QAction,
)


class OverlaySignals(QObject):
    """Signals for communicating from async threads to the Qt overlay."""
    add_pointer = pyqtSignal(int, int, str)         # x, y, label
    add_text_box = pyqtSignal(int, int, str)         # x, y, text
    add_highlight = pyqtSignal(int, int, int, int)   # x, y, w, h
    add_highlight_labeled = pyqtSignal(int, int, int, int, str)  # x, y, w, h, label
    clear_all = pyqtSignal()
    set_target = pyqtSignal(int, int)                # calibration target x, y
    clear_target = pyqtSignal()
    set_status = pyqtSignal(str)                     # status text
    set_subtitle = pyqtSignal(str)                   # subtitle text from Gemini
    mic_active = pyqtSignal(bool)                    # mic picking up sound
    speaker_active = pyqtSignal(bool)                # audio playing back
    # Tutorial plan signals
    set_tutorial = pyqtSignal(str, object)           # title, list of step strings
    set_current_step = pyqtSignal(int)               # 1-based step number
    complete_step = pyqtSignal(int)                   # 1-based step number
    uncomplete_step = pyqtSignal(int)                 # 1-based step number — undo completion
    set_current_task = pyqtSignal(str)               # instruction text
    # Connection lifecycle
    connection_ready = pyqtSignal()                  # fired when Gemini session is live
    # Monitor selection
    monitor_changed = pyqtSignal(int, int, int)      # mss_index, logical_w, logical_h


class TutorOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = OverlaySignals()
        self.signals.add_pointer.connect(self._on_add_pointer)
        self.signals.add_text_box.connect(self._on_add_text_box)
        self.signals.add_highlight.connect(self._on_add_highlight)
        self.signals.add_highlight_labeled.connect(self._on_add_highlight_labeled)
        self.signals.clear_all.connect(self._on_clear_all)
        self.signals.set_target.connect(self._on_set_target)
        self.signals.clear_target.connect(self._on_clear_target)

        # Frameless, transparent, click-through, always on top
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Span entire primary screen
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # Active hints: list of dicts with type, params, and creation time
        self.hints = []
        self.hint_timeout = 10

        # Calibration target (persistent, not auto-cleared)
        self._target = None  # (x, y) or None

        # Periodic cleanup timer
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._cleanup_expired)
        self._cleanup_timer.start(1000)

    def reposition_to_screen(self, geo):
        """Move overlay to span the given screen geometry."""
        self.setGeometry(geo)
        self.hints.clear()
        self._target = None
        self.update()

    def _on_add_pointer(self, x, y, label):
        self.hints.append({
            "type": "pointer", "x": x, "y": y, "label": label,
            "created": time.time(),
        })
        self.update()

    def _on_add_text_box(self, x, y, text):
        self.hints.append({
            "type": "text_box", "x": x, "y": y, "text": text,
            "created": time.time(),
        })
        self.update()

    def _on_add_highlight(self, x, y, w, h):
        self.hints.append({
            "type": "highlight", "x": x, "y": y, "w": w, "h": h,
            "created": time.time(),
        })
        self.update()

    def _on_add_highlight_labeled(self, x, y, w, h, label):
        self.hints.append({
            "type": "highlight_labeled", "x": x, "y": y, "w": w, "h": h,
            "label": label, "created": time.time(),
        })
        self.update()

    def _on_set_target(self, x, y):
        self._target = (x, y)
        self.update()

    def _on_clear_target(self):
        self._target = None
        self.update()

    def _on_clear_all(self):
        self.hints.clear()
        self.update()

    def _cleanup_expired(self):
        now = time.time()
        before = len(self.hints)
        self.hints = [h for h in self.hints if now - h["created"] < self.hint_timeout]
        if len(self.hints) != before:
            self.update()

    def paintEvent(self, event):
        if not self.hints and not self._target:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw calibration target first (behind other hints)
        if self._target:
            self._draw_target(painter, self._target[0], self._target[1])

        for hint in self.hints:
            if hint["type"] == "pointer":
                self._draw_pointer(painter, hint)
            elif hint["type"] == "text_box":
                self._draw_text_box(painter, hint)
            elif hint["type"] == "highlight":
                self._draw_highlight(painter, hint)
            elif hint["type"] == "highlight_labeled":
                self._draw_highlight_labeled(painter, hint)

        painter.end()

    def _draw_pointer(self, painter, hint):
        x, y, label = hint["x"], hint["y"], hint["label"]

        # Large downward-pointing arrow — tip at (x, y), body above
        # Arrowhead triangle
        arrow_head = QPolygonF([
            QPointF(x, y),            # tip
            QPointF(x - 16, y - 30),  # left wing
            QPointF(x + 16, y - 30),  # right wing
        ])
        painter.setPen(QPen(QColor(255, 60, 60), 2))
        painter.setBrush(QBrush(QColor(255, 60, 60, 220)))
        painter.drawPolygon(arrow_head)

        # Arrow stem
        painter.setPen(QPen(QColor(255, 60, 60), 5))
        painter.drawLine(x, y - 28, x, y - 70)

        # Glow dot at the exact tip
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 80, 200)))
        painter.drawEllipse(x - 4, y - 4, 8, 8)

        # Label above the arrow
        if label:
            font = QFont("Segoe UI", 13, QFont.Weight.Bold)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(label)
            text_h = metrics.height()

            label_x = x - text_w // 2
            label_y = y - 80

            bg_rect = QRectF(label_x - 8, label_y - text_h - 2, text_w + 16, text_h + 10)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(30, 30, 30, 220)))
            painter.drawRoundedRect(bg_rect, 6, 6)

            painter.setPen(QPen(QColor(255, 255, 100)))
            painter.drawText(label_x, label_y, label)

    def _draw_text_box(self, painter, hint):
        x, y, text = hint["x"], hint["y"], hint["text"]

        font = QFont("Segoe UI", 12)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        max_width = 350
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if metrics.horizontalAdvance(test) > max_width:
                if current_line:
                    lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

        line_h = metrics.height() + 4
        box_w = max(metrics.horizontalAdvance(line) for line in lines) + 24
        box_h = line_h * len(lines) + 20

        bg_rect = QRectF(x, y, box_w, box_h)
        painter.setPen(QPen(QColor(80, 180, 255), 2))
        painter.setBrush(QBrush(QColor(20, 20, 40, 230)))
        painter.drawRoundedRect(bg_rect, 8, 8)

        painter.setPen(QPen(QColor(240, 240, 240)))
        for i, line in enumerate(lines):
            painter.drawText(x + 12, y + 18 + i * line_h, line)

    def _draw_highlight(self, painter, hint):
        x, y, w, h = hint["x"], hint["y"], hint["w"], hint["h"]

        painter.setPen(QPen(QColor(80, 255, 80), 3))
        painter.setBrush(QBrush(QColor(80, 255, 80, 30)))
        painter.drawRoundedRect(x, y, w, h, 4, 4)

    def _draw_highlight_labeled(self, painter, hint):
        x, y, w, h = hint["x"], hint["y"], hint["w"], hint["h"]

        # Center of the highlight cell
        cx = x + w // 2
        cy = y + h // 2

        # Soft transparent circle at cell center
        radius = min(w, h) // 2 + 8

        # Outer glow ring
        painter.setPen(QPen(QColor(80, 200, 255, 30), 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cx - radius - 3, cy - radius - 3,
                            (radius + 3) * 2, (radius + 3) * 2)

        # Main circle — subtle transparent fill
        painter.setPen(QPen(QColor(80, 200, 255, 100), 2))
        painter.setBrush(QBrush(QColor(80, 200, 255, 25)))
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

    def _draw_target(self, painter, x, y):
        """Draw a clear magenta calibration target — no coordinate text."""
        # Outer circle
        painter.setPen(QPen(QColor(255, 0, 255), 4))
        painter.setBrush(QBrush(QColor(255, 0, 255, 40)))
        painter.drawEllipse(x - 25, y - 25, 50, 50)

        # Crosshair lines
        painter.setPen(QPen(QColor(255, 0, 255), 2))
        painter.drawLine(x - 35, y, x + 35, y)
        painter.drawLine(x, y - 35, x, y + 35)

        # Center dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 0, 255)))
        painter.drawEllipse(x - 4, y - 4, 8, 8)


class StatusPanelWidget(QWidget):
    """Combined status bar + tutorial panel. Compact when idle, expands for tutorials."""

    exit_requested = pyqtSignal()
    move_target_requested = pyqtSignal()
    monitor_selected = pyqtSignal(int)  # Qt screen index
    end_tutorial_requested = pyqtSignal()

    HEADER_H = 44         # height of the status header section
    PANEL_W = 300         # fixed width

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._current_screen_idx = 0  # track selected monitor

        screen = QApplication.primaryScreen().geometry()
        self._screen_geo = screen
        self.setGeometry(
            screen.x() + screen.width() - self.PANEL_W - 20,
            screen.y() + 16,
            self.PANEL_W, self.HEADER_H,
        )
        self.setFixedSize(self.PANEL_W, self.HEADER_H)

        # Status state
        self._status_text = "Starting..."
        self._mic_on = False
        self._speaker_on = False

        # Tutorial state
        self._title = ""
        self._steps = []
        self._completed = set()
        self._current = 0
        self._task_text = ""

        # Drag state
        self._drag_pos = None

        # Pulse animation
        self._pulse_phase = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.start(80)

    # ── Status methods ──────────────────────────────────────────────

    def _tick_pulse(self):
        self._pulse_phase = (self._pulse_phase + 1) % 20
        if self._mic_on or self._speaker_on or "Processing" in self._status_text:
            self.update()

    def set_status(self, text: str):
        self._status_text = text
        self.update()

    def set_mic_active(self, active: bool):
        self._mic_on = active
        self.update()

    def set_speaker_active(self, active: bool):
        self._speaker_on = active
        self.update()

    # ── Tutorial methods ────────────────────────────────────────────

    def set_tutorial(self, title: str, steps):
        self._title = title
        self._steps = list(steps)
        self._completed = set()
        self._current = 1 if steps else 0
        self._resize_to_fit()
        self.update()

    def set_current_step(self, step_num: int):
        self._current = step_num
        self.update()

    def complete_step(self, step_num: int):
        self._completed.add(step_num)
        self.update()

    def uncomplete_step(self, step_num: int):
        self._completed.discard(step_num)
        self.update()

    def set_task(self, text: str):
        self._task_text = text
        self._resize_to_fit()
        self.update()

    def clear_tutorial(self):
        self._title = ""
        self._steps = []
        self._completed = set()
        self._current = 0
        self._task_text = ""
        self._resize_to_fit()
        self.update()

    # ── Layout ──────────────────────────────────────────────────────

    @staticmethod
    def _wrap_text(text, metrics, max_w):
        words = text.split()
        lines = []
        cur = ""
        for word in words:
            test = f"{cur} {word}".strip()
            if metrics.horizontalAdvance(test) > max_w:
                if cur:
                    lines.append(cur)
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines or [""]

    def _resize_to_fit(self):
        if not self._steps:
            h = self.HEADER_H
        else:
            line_h = 28
            title_h = 42
            task_h = 0
            if self._task_text:
                font = QFont("Segoe UI", 10)
                from PyQt6.QtGui import QFontMetrics
                metrics = QFontMetrics(font)
                task_lines = self._wrap_text(self._task_text, metrics, self.PANEL_W - 24)
                task_line_h = metrics.height() + 2
                task_h = 40 + len(task_lines) * task_line_h
            max_h = (self._screen_geo.height() - 120) if self._screen_geo else 900
            h = min(self.HEADER_H + title_h + len(self._steps) * line_h + 20 + task_h, max_h)
        self.setFixedSize(self.PANEL_W, h)

    def reposition_to_screen(self, geo):
        self._screen_geo = geo
        self.move(geo.x() + geo.width() - self.PANEL_W - 20, geo.y() + 16)
        self._resize_to_fit()

    # ── Painting ────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        pulse = (math.sin(self._pulse_phase * math.pi / 10) + 1) / 2

        # Background
        if self._steps:
            painter.setPen(QPen(QColor(15, 52, 96, 60), 1))
            painter.setBrush(QBrush(QColor(12, 15, 30, 220)))
            painter.drawRoundedRect(0, 0, w, h, 10, 10)
        else:
            painter.setPen(QPen(QColor(15, 52, 96), 1))
            painter.setBrush(QBrush(QColor(20, 20, 40, 220)))
            painter.drawRoundedRect(0, 0, w, h, h // 2, h // 2)

        # ── Status header ───────────────────────────────────────────
        hh = self.HEADER_H
        hcy = hh // 2  # vertical center of header

        # Mic indicator dot
        if self._mic_on:
            mic_alpha = int(150 + 105 * pulse)
            mic_size = int(10 + 4 * pulse)
            mic_color = QColor(80, 250, 123, mic_alpha)
        else:
            mic_size = 10
            mic_color = QColor(80, 80, 80)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(mic_color))
        off = (mic_size - 10) // 2
        painter.drawEllipse(14 - off, hcy - 5 - off, mic_size, mic_size)

        painter.setPen(QPen(QColor(150, 150, 150)))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(28, hcy + 4, "MIC")

        # Speaker indicator dot
        if self._speaker_on:
            spk_alpha = int(150 + 105 * pulse)
            spk_size = int(10 + 4 * pulse)
            spk_color = QColor(80, 180, 255, spk_alpha)
        else:
            spk_size = 10
            spk_color = QColor(80, 80, 80)
        painter.setBrush(QBrush(spk_color))
        off = (spk_size - 10) // 2
        painter.drawEllipse(56 - off, hcy - 5 - off, spk_size, spk_size)

        painter.setPen(QPen(QColor(150, 150, 150)))
        painter.drawText(70, hcy + 4, "OUT")

        # Status text
        status = self._status_text
        if "Listening" in status:
            color = QColor(80, 250, 123)
        elif "Speaking" in status:
            color = QColor(80, 180, 255)
        elif "Processing" in status:
            alpha = int(150 + 105 * pulse)
            color = QColor(255, 184, 108, alpha)
        elif "Error" in status or "Failed" in status:
            color = QColor(255, 85, 85)
        elif "Connecting" in status:
            alpha = int(150 + 105 * pulse)
            color = QColor(255, 184, 108, alpha)
        else:
            color = QColor(83, 168, 255)

        painter.setPen(QPen(color))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(100, hcy + 5, status)

        # ── Tutorial section (only if steps exist) ──────────────────
        if self._steps:
            # Divider below header
            painter.setPen(QPen(QColor(60, 80, 120, 100), 1))
            painter.drawLine(12, hh, w - 12, hh)

            # Title
            painter.setPen(QPen(QColor(83, 168, 255)))
            painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            painter.drawText(16, hh + 26, self._title)

            # Divider below title
            painter.setPen(QPen(QColor(60, 80, 120, 100), 1))
            painter.drawLine(16, hh + 36, w - 16, hh + 36)

            # Steps
            y_offset = hh + 48
            line_h = 28

            for i, step_text in enumerate(self._steps):
                step_num = i + 1
                is_completed = step_num in self._completed
                is_current = step_num == self._current

                if is_current and not is_completed:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor(83, 168, 255, 25)))
                    painter.drawRoundedRect(4, y_offset - 4, w - 8, line_h, 4, 4)

                ix = 16
                iy = y_offset

                if is_completed:
                    painter.setPen(QPen(QColor(80, 250, 123), 2))
                    painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
                    painter.drawText(ix, iy + 16, "\u2713")
                elif is_current:
                    painter.setPen(QPen(QColor(83, 168, 255), 2))
                    painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                    painter.drawText(ix, iy + 16, "\u25b6")
                else:
                    painter.setPen(QPen(QColor(80, 80, 100)))
                    painter.setFont(QFont("Segoe UI", 10))
                    painter.drawText(ix, iy + 15, f"{step_num}.")

                tx = 36
                max_text_w = w - tx - 12

                if is_completed:
                    painter.setPen(QPen(QColor(80, 250, 123, 150)))
                    painter.setFont(QFont("Segoe UI", 10))
                elif is_current:
                    painter.setPen(QPen(QColor(240, 240, 240)))
                    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                else:
                    painter.setPen(QPen(QColor(120, 120, 140)))
                    painter.setFont(QFont("Segoe UI", 10))

                metrics = painter.fontMetrics()
                display = metrics.elidedText(step_text, Qt.TextElideMode.ElideRight, max_text_w)
                painter.drawText(tx, iy + 16, display)

                y_offset += line_h

            # Task section
            if self._task_text:
                painter.setPen(QPen(QColor(60, 80, 120, 100), 1))
                painter.drawLine(16, y_offset + 4, w - 16, y_offset + 4)

                badge_y = y_offset + 14
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(83, 168, 255)))
                painter.drawRoundedRect(12, badge_y, 42, 20, 4, 4)
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.drawText(18, badge_y + 14, "TASK")

                painter.setPen(QPen(QColor(240, 240, 240)))
                painter.setFont(QFont("Segoe UI", 10))
                metrics = painter.fontMetrics()
                max_text_w = w - 24
                task_lines = self._wrap_text(self._task_text, metrics, max_text_w)
                task_line_h = metrics.height() + 2
                for i, line in enumerate(task_lines):
                    painter.drawText(12, badge_y + 36 + i * task_line_h, line)

        painter.end()

    # ── Interaction ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_menu(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _show_menu(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a2e;
                color: #eaeaea;
                border: 1px solid #0f3460;
                border-radius: 4px;
                padding: 4px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #0f3460;
            }
        """)

        # End Tutorial (only when a tutorial is active)
        if self._steps:
            end_action = QAction("End Tutorial", self)
            end_action.triggered.connect(self._on_end_tutorial)
            menu.addAction(end_action)
            menu.addSeparator()

        # Monitor selection submenu
        screens = QApplication.screens()
        if len(screens) > 1:
            monitor_menu = QMenu("Select Monitor", self)
            monitor_menu.setStyleSheet(menu.styleSheet())
            for i, scr in enumerate(screens):
                geo = scr.geometry()
                label = f"Monitor {i + 1}: {geo.width()}x{geo.height()}"
                if i == self._current_screen_idx:
                    label += "  (current)"
                action = QAction(label, self)
                action.triggered.connect(lambda checked, idx=i: self._on_select_monitor(idx))
                monitor_menu.addAction(action)
            menu.addMenu(monitor_menu)
            menu.addSeparator()

        move_target_action = QAction("Move Target", self)
        move_target_action.triggered.connect(self._on_move_target)
        menu.addAction(move_target_action)

        menu.addSeparator()

        exit_action = QAction("Exit Learn With Gemini", self)
        exit_action.triggered.connect(self._on_exit)
        menu.addAction(exit_action)

        menu.exec(self.mapToGlobal(event.pos()))

    def _on_end_tutorial(self):
        self.clear_tutorial()
        self.end_tutorial_requested.emit()

    def _on_select_monitor(self, idx):
        self._current_screen_idx = idx
        self.monitor_selected.emit(idx)

    def _on_move_target(self):
        self.move_target_requested.emit()

    def _on_exit(self):
        self.exit_requested.emit()
        QApplication.quit()


class SubtitleWidget(QWidget):
    """Subtitle bar at the bottom-center of the screen — draggable."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._drag_pos = None

        screen = QApplication.primaryScreen().geometry()
        self._sub_w = 700
        self._sub_h = 60
        self.setGeometry(
            screen.x() + (screen.width() - self._sub_w) // 2,
            screen.y() + screen.height() - self._sub_h - 60,
            self._sub_w, self._sub_h,
        )
        self.setFixedSize(self._sub_w, self._sub_h)

        self._text = ""
        self._visible_until = 0

        # Auto-hide timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_hide)
        self._timer.start(500)

    def reposition_to_screen(self, geo):
        """Move subtitle bar to bottom-center of the given screen geometry."""
        self.move(
            geo.x() + (geo.width() - self._sub_w) // 2,
            geo.y() + geo.height() - self._sub_h - 60,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_subtitle(self, text: str):
        self._text = text
        self._visible_until = time.time() + 8  # show for 8 seconds
        self.update()

    def _check_hide(self):
        if self._text and time.time() > self._visible_until:
            self._text = ""
            self.update()

    def paintEvent(self, event):
        if not self._text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(10, 10, 20, 200)))
        painter.drawRoundedRect(0, 0, w, h, 12, 12)

        # Subtitle text (word-wrapped)
        painter.setPen(QPen(QColor(240, 240, 240)))
        font = QFont("Segoe UI", 13)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        # Simple word wrap
        max_w = w - 32
        words = self._text.split()
        lines = []
        cur = ""
        for word in words:
            test = f"{cur} {word}".strip()
            if metrics.horizontalAdvance(test) > max_w:
                if cur:
                    lines.append(cur)
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur)

        # Only show last 2 lines
        lines = lines[-2:]
        line_h = metrics.height() + 2
        total_h = line_h * len(lines)
        start_y = (h - total_h) // 2 + metrics.ascent()

        for i, line in enumerate(lines):
            lw = metrics.horizontalAdvance(line)
            painter.drawText((w - lw) // 2, start_y + i * line_h, line)

        painter.end()


class LoadingWidget(QWidget):
    """Loading screen with spinner and status log — shown during initial connection."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().geometry()
        self._panel_w = 420
        self._panel_h = 320
        self.setGeometry(
            screen.x() + (screen.width() - self._panel_w) // 2,
            screen.y() + (screen.height() - self._panel_h) // 2,
            self._panel_w, self._panel_h,
        )
        self.setFixedSize(self._panel_w, self._panel_h)

        self._angle = 0
        self._messages = []

        # Spinner animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30fps

    def reposition_to_screen(self, geo):
        """Center loading widget on the given screen geometry."""
        self.move(
            geo.x() + (geo.width() - self._panel_w) // 2,
            geo.y() + (geo.height() - self._panel_h) // 2,
        )

    def _tick(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def add_message(self, text: str):
        self._messages.append(text)
        if len(self._messages) > 8:
            self._messages = self._messages[-8:]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background — fully opaque
        painter.setPen(QPen(QColor(15, 52, 96), 1))
        painter.setBrush(QBrush(QColor(18, 18, 36)))
        painter.drawRoundedRect(0, 0, w, h, 12, 12)

        # Title
        painter.setPen(QPen(QColor(83, 168, 255)))
        painter.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title_rect = QRectF(0, 28, w, 36)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "Learn With Gemini")

        # Subtitle
        painter.setPen(QPen(QColor(140, 140, 160)))
        painter.setFont(QFont("Segoe UI", 10))
        sub_rect = QRectF(0, 62, w, 22)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, "Setting things up...")

        # Spinner — rotating arc
        spinner_cx = w // 2
        spinner_cy = 120
        spinner_r = 22
        spinner_rect = QRectF(
            spinner_cx - spinner_r, spinner_cy - spinner_r,
            spinner_r * 2, spinner_r * 2,
        )

        # Background ring
        painter.setPen(QPen(QColor(40, 50, 80), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(spinner_rect)

        # Spinning arc
        arc_pen = QPen(QColor(83, 168, 255), 3)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(spinner_rect, int(self._angle * 16), int(90 * 16))

        # Divider
        div_y = 160
        painter.setPen(QPen(QColor(60, 80, 120, 80), 1))
        painter.drawLine(24, div_y, w - 24, div_y)

        # Status log
        painter.setFont(QFont("Segoe UI", 9))
        log_y = 176
        line_h = 18
        for i, msg in enumerate(self._messages):
            alpha = max(100, 255 - (len(self._messages) - 1 - i) * 30)
            painter.setPen(QPen(QColor(160, 175, 200, alpha)))
            painter.drawText(24, log_y + i * line_h, msg)

        painter.end()


class TopicMenuWidget(QWidget):
    """Floating topic selection menu — shown at startup before a tutorial begins."""

    topic_selected = pyqtSignal(str)

    def __init__(self, tutorials):
        super().__init__()
        self._tutorials = tutorials
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().geometry()
        self._menu_w = 440
        self._menu_h = 500
        self.setGeometry(
            screen.x() + (screen.width() - self._menu_w) // 2,
            screen.y() + (screen.height() - self._menu_h) // 2,
            self._menu_w, self._menu_h,
        )
        self.setFixedSize(self._menu_w, self._menu_h)

        self._drag_pos = None
        self._setup_ui()

    def reposition_to_screen(self, geo):
        """Center topic menu on the given screen geometry."""
        self.move(
            geo.x() + (geo.width() - self._menu_w) // 2,
            geo.y() + (geo.height() - self._menu_h) // 2,
        )

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(28, 28, 28, 28)

        # Title
        title = QLabel("Learn With Gemini")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #53a8ff; background: transparent;")
        layout.addWidget(title)

        subtitle = QLabel("Pick a tutorial or tell me what to teach!")
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888; background: transparent; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # Tutorial buttons
        btn_style = """
            QPushButton {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 12px 14px;
                color: #eaeaea;
                font-size: 13px;
                font-family: 'Segoe UI';
                text-align: left;
            }
            QPushButton:hover {
                background-color: #0f3460;
                border-color: #53a8ff;
            }
        """
        for display_name, topic_prompt in self._tutorials:
            btn = QPushButton(display_name)
            btn.setStyleSheet(btn_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, t=topic_prompt: self._select(t))
            layout.addWidget(btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333; background: transparent;")
        layout.addWidget(sep)

        # Custom input
        custom_label = QLabel("Or describe what you want to learn:")
        custom_label.setFont(QFont("Segoe UI", 10))
        custom_label.setStyleSheet("color: #888; background: transparent;")
        layout.addWidget(custom_label)

        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("e.g., How to use Git")
        self._input.setStyleSheet("""
            QLineEdit {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 10px;
                color: #eaeaea;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #53a8ff; }
        """)
        self._input.returnPressed.connect(self._select_custom)
        input_row.addWidget(self._input)

        go_btn = QPushButton("Go")
        go_btn.setFixedWidth(50)
        go_btn.setStyleSheet("""
            QPushButton {
                background-color: #53a8ff;
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover { background-color: #3d8ce0; }
        """)
        go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        go_btn.clicked.connect(self._select_custom)
        input_row.addWidget(go_btn)

        layout.addLayout(input_row)
        layout.addStretch()
        self.setLayout(layout)

    def _select(self, topic):
        self.topic_selected.emit(topic)

    def _select_custom(self):
        text = self._input.text().strip()
        if text:
            self.topic_selected.emit(text)

    def paintEvent(self, event):
        # Draw rounded background — fully opaque
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(15, 52, 96), 1))
        painter.setBrush(QBrush(QColor(18, 18, 36)))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class MonitorFlashWidget(QWidget):
    """Temporary full-screen flash on a monitor to confirm selection."""

    def __init__(self, geometry):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(geometry)

        # Auto-close after 800ms
        QTimer.singleShot(800, self._finish)

    def _finish(self):
        self.close()
        self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Semi-transparent cyan flash
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 180, 255, 50)))
        painter.drawRect(0, 0, w, h)

        # Border highlight
        painter.setPen(QPen(QColor(83, 168, 255, 180), 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(3, 3, w - 6, h - 6)

        # "SELECTED" text in center
        painter.setPen(QPen(QColor(255, 255, 255, 200)))
        painter.setFont(QFont("Segoe UI", 48, QFont.Weight.Bold))
        text_rect = QRectF(0, 0, w, h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "SELECTED")

        painter.end()
