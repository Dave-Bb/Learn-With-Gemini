"""
Quick overlay test — draws pointers at known screen positions.
No Gemini needed, just tests the overlay rendering.
"""
import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from overlay import TutorOverlay, StatusWidget


def main():
    app = QApplication(sys.argv)
    overlay = TutorOverlay()
    overlay.show()

    status = StatusWidget()
    status.show()
    overlay.signals.set_status.connect(status.set_status)

    screen = app.primaryScreen().geometry()
    sw, sh = screen.width(), screen.height()
    dpr = app.primaryScreen().devicePixelRatio()

    overlay.signals.set_status.emit(f"Test — {sw}x{sh} @ {dpr}x DPI")
    print(f"Logical screen: {sw}x{sh}")
    print(f"DPI scale: {dpr}")
    print(f"Physical screen: {int(sw*dpr)}x{int(sh*dpr)}")

    # Draw test markers at known positions after a short delay
    def draw_tests():
        margin = 50

        # Corners
        overlay.signals.add_pointer.emit(margin, margin, f"Top-Left ({margin},{margin})")
        overlay.signals.add_pointer.emit(sw - margin, margin, f"Top-Right ({sw-margin},{margin})")
        overlay.signals.add_pointer.emit(margin, sh - margin, f"Bot-Left ({margin},{sh-margin})")
        overlay.signals.add_pointer.emit(sw - margin, sh - margin, f"Bot-Right ({sw-margin},{sh-margin})")

        # Center
        cx, cy = sw // 2, sh // 2
        overlay.signals.add_pointer.emit(cx, cy, f"Center ({cx},{cy})")

        # Quarter points
        overlay.signals.add_pointer.emit(sw // 4, sh // 4, f"Q1 ({sw//4},{sh//4})")
        overlay.signals.add_pointer.emit(3 * sw // 4, sh // 4, f"Q2 ({3*sw//4},{sh//4})")
        overlay.signals.add_pointer.emit(sw // 4, 3 * sh // 4, f"Q3 ({sw//4},{3*sh//4})")
        overlay.signals.add_pointer.emit(3 * sw // 4, 3 * sh // 4, f"Q4 ({3*sw//4},{3*sh//4})")

        # Text box test
        overlay.signals.add_text_box.emit(cx - 175, cy + 60, "This text box should be centered below the center dot")

        # Highlight test
        overlay.signals.add_highlight.emit(cx - 100, cy - 100, 200, 200, )

        print("All markers drawn. Check if they appear at the correct positions.")
        print("Press Ctrl+C or close to exit.")

    # Longer timeout so markers stay visible
    overlay.hint_timeout = 60

    QTimer.singleShot(500, draw_tests)
    app.exec()


if __name__ == "__main__":
    main()
