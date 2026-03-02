"""
Learn With Gemini — Interactive AI Screen Tutor
Main entry point with launcher UI.

Usage:
    set GOOGLE_API_KEY=your-key-here
    python learn_with_gemini.py
"""

import sys
import asyncio
import random
import threading

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor, QPalette

import mss

from overlay import TutorOverlay, StatusPanelWidget, SubtitleWidget, TopicMenuWidget, LoadingWidget, MonitorFlashWidget
from audio import AudioManager
from session import TutorSession


# Predefined tutorial topics
TUTORIALS = [
    ("Google Sheets: Budget Tracker", "Walk the user through creating a simple monthly budget in Google Sheets. Open Chrome, go to sheets.google.com, create a new spreadsheet, add income and expense rows with labels, enter some example numbers, and use the SUM formula to calculate totals."),
    ("Windows: Change Your Wallpaper", "Guide the user through changing their Windows desktop wallpaper. Right-click the desktop, open Personalize settings, browse backgrounds, pick a new wallpaper, and confirm the change."),
    ("Snipping Tool: Take a Screenshot", "Teach the user how to take and save a screenshot using the Windows Snipping Tool. Open Snipping Tool from the Start menu, choose a snip mode, capture a region of the screen, and save the image."),
    ("Paint: Draw a Smiley Face", "Guide the user through drawing a simple smiley face in Microsoft Paint. Open Paint from the Start menu, use the circle tool for the head, add two eyes, draw a curved mouth, pick colors, and save the drawing."),
    ("Chrome: Install an Extension", "Help the user install a browser extension in Google Chrome. Open Chrome, navigate to the Chrome Web Store, search for an extension like 'Dark Reader', click Add to Chrome, and confirm the installation."),
    ("Notepad: Write & Save a File", "Guide the user through creating and saving a text file with Notepad. Open Notepad from the Start menu, type a short message, use File > Save As to pick a location and filename, and verify the file was saved."),
]


class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_topic = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Learn With Gemini")
        self.setFixedSize(QSize(520, 560))
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                color: #eaeaea;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 16px 14px;
                min-height: 20px;
                font-size: 14px;
                font-family: 'Segoe UI', sans-serif;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #0f3460;
                border-color: #53a8ff;
            }
            QLineEdit {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                color: #eaeaea;
            }
            QLineEdit:focus {
                border-color: #53a8ff;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel("Learn With Gemini")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #53a8ff; margin-bottom: 4px;")
        layout.addWidget(title)

        subtitle = QLabel("What would you like to learn today?")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888; margin-bottom: 16px;")
        layout.addWidget(subtitle)

        # Predefined tutorial buttons
        for display_name, topic_prompt in TUTORIALS:
            btn = QPushButton(display_name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, t=topic_prompt: self._start(t))
            layout.addWidget(btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        layout.addWidget(sep)

        # Custom topic input
        custom_label = QLabel("Or describe what you want to learn:")
        custom_label.setFont(QFont("Segoe UI", 11))
        custom_label.setStyleSheet("color: #888;")
        layout.addWidget(custom_label)

        input_row = QHBoxLayout()
        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("e.g., How to use Git for version control")
        self.custom_input.returnPressed.connect(self._start_custom)
        input_row.addWidget(self.custom_input)

        go_btn = QPushButton("Go")
        go_btn.setFixedWidth(60)
        go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        go_btn.setStyleSheet("""
            QPushButton {
                background-color: #53a8ff;
                color: white;
                font-weight: bold;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #3d8ce0;
            }
        """)
        go_btn.clicked.connect(self._start_custom)
        input_row.addWidget(go_btn)

        layout.addLayout(input_row)
        layout.addStretch()

        self.setLayout(layout)

    def _start_custom(self):
        text = self.custom_input.text().strip()
        if text:
            self._start(text)

    def _start(self, topic: str):
        self.selected_topic = topic
        self.close()


def run_session_thread(session):
    """Run the Gemini session in a background thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(session.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


def build_monitor_map(app):
    """Build a mapping from Qt screen index to mss monitor index.

    mss.monitors[0] is the virtual combined screen; [1..N] are real monitors.
    Qt screens are returned by QApplication.screens().
    We match them by comparing the top-left position of each.
    """
    qt_screens = app.screens()
    with mss.mss() as sct:
        mss_monitors = sct.monitors[1:]  # skip virtual screen at index 0

    mapping = []  # list of (qt_index, mss_index_1based)
    for qi, scr in enumerate(qt_screens):
        geo = scr.geometry()
        dpr = scr.devicePixelRatio()
        # Qt gives logical coords; mss may give physical coords on scaled displays
        qt_x, qt_y = geo.x(), geo.y()
        best_mss = None
        best_dist = float("inf")
        for mi, mon in enumerate(mss_monitors):
            # Try matching both logical and physical positions
            dx = abs(mon["left"] - qt_x)
            dy = abs(mon["top"] - qt_y)
            dist = dx + dy
            if dist < best_dist:
                best_dist = dist
                best_mss = mi + 1  # mss index is 1-based
            # Also try with DPR scaling
            dx2 = abs(mon["left"] - int(qt_x * dpr))
            dy2 = abs(mon["top"] - int(qt_y * dpr))
            dist2 = dx2 + dy2
            if dist2 < best_dist:
                best_dist = dist2
                best_mss = mi + 1
        mapping.append((qi, best_mss or 1))
        scr_name = scr.name()
        print(f"[monitor] Qt screen {qi} '{scr_name}' {geo.width()}x{geo.height()} "
              f"@ ({qt_x},{qt_y}) -> mss monitor {best_mss}")

    return mapping


def main():
    app = QApplication(sys.argv)

    print("\nStarting Learn With Gemini...\n")

    # Build Qt screen -> mss monitor mapping
    monitor_map = build_monitor_map(app)

    # Find the Qt primary screen index
    qt_screens = app.screens()
    primary = app.primaryScreen()
    primary_idx = 0
    for i, scr in enumerate(qt_screens):
        if scr == primary:
            primary_idx = i
            break

    # Look up matching mss index for the primary screen
    initial_mss_idx = 1  # fallback
    for qi, mi in monitor_map:
        if qi == primary_idx:
            initial_mss_idx = mi
            break

    screen_geo = primary.geometry()
    logical_w = screen_geo.width()
    logical_h = screen_geo.height()
    dpr = primary.devicePixelRatio()
    print(f"[monitor] Primary: Qt screen {primary_idx}, mss monitor {initial_mss_idx}")
    print(f"[monitor] Logical: {logical_w}x{logical_h} (DPR={dpr})")

    # Create overlay, combined status/tutorial panel, subtitle bar
    overlay = TutorOverlay()
    overlay.show()

    status_panel = StatusPanelWidget()
    status_panel._current_screen_idx = primary_idx
    status_panel.show()

    subtitles = SubtitleWidget()
    subtitles.show()

    # Loading screen (shown first) and topic menu (shown after connection)
    loading = LoadingWidget()
    loading.show()
    loading.add_message("Initializing...")

    topic_menu = TopicMenuWidget(TUTORIALS)
    # topic_menu starts hidden — shown when connection is ready

    # Wire up all signals
    overlay.signals.set_status.connect(status_panel.set_status)
    overlay.signals.set_status.connect(loading.add_message)
    overlay.signals.mic_active.connect(status_panel.set_mic_active)
    overlay.signals.speaker_active.connect(status_panel.set_speaker_active)
    overlay.signals.set_subtitle.connect(subtitles.set_subtitle)
    overlay.signals.set_tutorial.connect(status_panel.set_tutorial)
    overlay.signals.set_current_step.connect(status_panel.set_current_step)
    overlay.signals.complete_step.connect(status_panel.complete_step)
    overlay.signals.uncomplete_step.connect(status_panel.uncomplete_step)
    overlay.signals.set_current_task.connect(status_panel.set_task)
    status_panel.exit_requested.connect(app.quit)

    # Create session with the correct mss monitor index
    audio = AudioManager()
    session = TutorSession(None, overlay.signals, audio, logical_w, logical_h,
                           mss_index=initial_mss_idx)

    # Transition: loading → topic menu when connection is ready
    def on_connection_ready():
        loading.hide()
        topic_menu.show()

    overlay.signals.connection_ready.connect(on_connection_ready)

    # Wire topic selection → session + hide menu
    def on_topic_selected(topic):
        topic_menu.hide()
        session.set_topic(topic)
        print(f"[menu] Topic selected: {topic}")

    topic_menu.topic_selected.connect(on_topic_selected)

    # Move target button — randomly repositions the calibration target
    # Uses current logical dimensions (updated on monitor switch)
    current_dims = {"w": logical_w, "h": logical_h}

    def move_target():
        margin = 150
        tx = random.randint(margin, current_dims["w"] - margin)
        ty = random.randint(margin, current_dims["h"] - margin)
        overlay.signals.clear_all.emit()
        overlay.signals.set_target.emit(tx, ty)
        print(f"[calibration] Target moved to logical ({tx}, {ty})")

    status_panel.move_target_requested.connect(move_target)

    # Monitor selection handler
    # Keep a reference to the flash widget so it doesn't get garbage collected
    flash_ref = {"widget": None}

    def on_monitor_selected(qt_screen_idx):
        screens = app.screens()
        if qt_screen_idx < 0 or qt_screen_idx >= len(screens):
            return

        scr = screens[qt_screen_idx]
        geo = scr.geometry()

        # Look up mss index
        mss_idx = 1
        for qi, mi in monitor_map:
            if qi == qt_screen_idx:
                mss_idx = mi
                break

        print(f"[monitor] User selected Qt screen {qt_screen_idx} -> mss monitor {mss_idx} "
              f"({geo.width()}x{geo.height()} @ {geo.x()},{geo.y()})")

        # Flash the selected monitor
        flash_ref["widget"] = MonitorFlashWidget(geo)
        flash_ref["widget"].show()

        # Reposition all widgets to the selected monitor
        overlay.reposition_to_screen(geo)
        status_panel.reposition_to_screen(geo)
        subtitles.reposition_to_screen(geo)
        loading.reposition_to_screen(geo)
        topic_menu.reposition_to_screen(geo)

        # Update session's monitor and logical dimensions
        new_w = geo.width()
        new_h = geo.height()
        current_dims["w"] = new_w
        current_dims["h"] = new_h
        session.set_monitor(mss_idx, new_w, new_h)

    status_panel.monitor_selected.connect(on_monitor_selected)

    # End tutorial handler — show topic menu again
    def on_end_tutorial():
        topic_menu.show()
        overlay.signals.clear_all.emit()
        session._plan_steps = None
        print("[menu] Tutorial ended, returning to topic selection")

    status_panel.end_tutorial_requested.connect(on_end_tutorial)

    # Start Gemini session in background thread (connects immediately in greeting mode)
    thread = threading.Thread(
        target=run_session_thread,
        args=(session,),
        daemon=True,
    )
    thread.start()

    # Run the Qt event loop
    app.exec()


if __name__ == "__main__":
    main()
