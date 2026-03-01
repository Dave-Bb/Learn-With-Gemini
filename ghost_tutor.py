"""
Ghost Tutor — Interactive AI Screen Tutor
Main entry point with launcher UI.

Usage:
    set GOOGLE_API_KEY=your-key-here
    python ghost_tutor.py
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

from overlay import GhostOverlay, StatusWidget, SubtitleWidget, TutorialPanelWidget
from audio import AudioManager
from session import GhostSession


# Predefined tutorial topics
TUTORIALS = [
    ("Screen Finder (Calibration)", "CALIBRATION_MODE"),
    ("Python: Hello World", "Guide the user through writing and running their first Python 'Hello World' program. Start from opening an IDE or text editor."),
    ("Excel: Basics", "Teach the user the basics of Microsoft Excel — opening it, entering data in cells, basic formulas like SUM, and saving."),
    ("Web Browsing", "Guide the user through basic web browsing — opening a browser, navigating to a website, using bookmarks, and tabs."),
    ("VS Code: Getting Started", "Help the user get started with Visual Studio Code — opening it, creating a file, installing extensions, and running code."),
]


class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_topic = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Ghost Tutor")
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
        title = QLabel("Ghost Tutor")
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


def run_session_thread(topic: str, overlay_signals, logical_w: int, logical_h: int):
    """Run the Gemini session in a background thread with its own event loop."""
    audio = AudioManager()
    session = GhostSession(topic, overlay_signals, audio, logical_w, logical_h)

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

    # Show launcher
    launcher = LauncherWindow()
    launcher.show()
    app.exec()

    if not launcher.selected_topic:
        print("No topic selected. Exiting.")
        return

    topic = launcher.selected_topic
    print(f"\nStarting Ghost Tutor session: {topic}\n")

    # Create overlay, status bar, and subtitle bar
    overlay_app = QApplication.instance() or QApplication(sys.argv)
    overlay = GhostOverlay()
    overlay.show()

    status = StatusWidget()
    status.show()

    subtitles = SubtitleWidget()
    subtitles.show()

    tutorial_panel = TutorialPanelWidget()
    tutorial_panel.show()

    # Wire up all signals
    overlay.signals.set_status.connect(status.set_status)
    overlay.signals.mic_active.connect(status.set_mic_active)
    overlay.signals.speaker_active.connect(status.set_speaker_active)
    overlay.signals.set_subtitle.connect(subtitles.set_subtitle)
    overlay.signals.set_tutorial.connect(tutorial_panel.set_tutorial)
    overlay.signals.set_current_step.connect(tutorial_panel.set_current_step)
    overlay.signals.complete_step.connect(tutorial_panel.complete_step)
    overlay.signals.set_current_task.connect(tutorial_panel.set_task)
    status.exit_requested.connect(overlay_app.quit)

    # Get Qt logical screen dimensions — the overlay draws in this coordinate space
    screen_geo = overlay_app.primaryScreen().geometry()
    logical_w = screen_geo.width()
    logical_h = screen_geo.height()
    dpr = overlay_app.primaryScreen().devicePixelRatio()
    print(f"Qt logical screen: {logical_w}x{logical_h} (DPR={dpr})")

    # Move target button — randomly repositions the calibration target
    def move_target():
        margin = 150
        tx = random.randint(margin, logical_w - margin)
        ty = random.randint(margin, logical_h - margin)
        overlay.signals.clear_all.emit()
        overlay.signals.set_target.emit(tx, ty)
        print(f"[calibration] Target moved to logical ({tx}, {ty})")

    status.move_target_requested.connect(move_target)

    # Start Gemini session in background thread
    thread = threading.Thread(
        target=run_session_thread,
        args=(topic, overlay.signals, logical_w, logical_h),
        daemon=True,
    )
    thread.start()

    # Run the Qt event loop (overlay stays visible)
    overlay_app.exec()


if __name__ == "__main__":
    main()
