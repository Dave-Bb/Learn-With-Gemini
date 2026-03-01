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

from overlay import TutorOverlay, StatusWidget, SubtitleWidget, TutorialPanelWidget, TopicMenuWidget, LoadingWidget
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


def main():
    app = QApplication(sys.argv)

    print("\nStarting Learn With Gemini...\n")

    # Create overlay, status bar, subtitle bar, and tutorial panel
    overlay = TutorOverlay()
    overlay.show()

    status = StatusWidget()
    status.show()

    subtitles = SubtitleWidget()
    subtitles.show()

    tutorial_panel = TutorialPanelWidget()
    tutorial_panel.show()

    # Loading screen (shown first) and topic menu (shown after connection)
    loading = LoadingWidget()
    loading.show()
    loading.add_message("Initializing...")

    topic_menu = TopicMenuWidget(TUTORIALS)
    # topic_menu starts hidden — shown when connection is ready

    # Wire up all signals
    overlay.signals.set_status.connect(status.set_status)
    overlay.signals.set_status.connect(loading.add_message)
    overlay.signals.mic_active.connect(status.set_mic_active)
    overlay.signals.speaker_active.connect(status.set_speaker_active)
    overlay.signals.set_subtitle.connect(subtitles.set_subtitle)
    overlay.signals.set_tutorial.connect(tutorial_panel.set_tutorial)
    overlay.signals.set_current_step.connect(tutorial_panel.set_current_step)
    overlay.signals.complete_step.connect(tutorial_panel.complete_step)
    overlay.signals.set_current_task.connect(tutorial_panel.set_task)
    status.exit_requested.connect(app.quit)

    # Get Qt logical screen dimensions — the overlay draws in this coordinate space
    screen_geo = app.primaryScreen().geometry()
    logical_w = screen_geo.width()
    logical_h = screen_geo.height()
    dpr = app.primaryScreen().devicePixelRatio()
    print(f"Qt logical screen: {logical_w}x{logical_h} (DPR={dpr})")

    # Create session in greeting mode (no topic yet)
    audio = AudioManager()
    session = TutorSession(None, overlay.signals, audio, logical_w, logical_h)

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
    def move_target():
        margin = 150
        tx = random.randint(margin, logical_w - margin)
        ty = random.randint(margin, logical_h - margin)
        overlay.signals.clear_all.emit()
        overlay.signals.set_target.emit(tx, ty)
        print(f"[calibration] Target moved to logical ({tx}, {ty})")

    status.move_target_requested.connect(move_target)

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
