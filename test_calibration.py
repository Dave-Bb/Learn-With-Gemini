"""
Calibration diagnostic — finds the exact offset between Qt overlay and mss capture.

Draws crosshairs at known positions on the overlay, captures the screen with mss,
then finds where the crosshairs actually appear in the capture. This tells us
the exact pixel offset between the two coordinate systems.

Also shows live cursor position for manual verification.
"""
import sys
import time
import io

import mss
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QCursor


class CalibrationOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.markers = []  # list of (x, y) in logical coords

    def set_markers(self, markers):
        self.markers = markers
        self.update()

    def paintEvent(self, event):
        if not self.markers:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for x, y in self.markers:
            # Draw bright crosshair — easy to find in capture
            pen = QPen(QColor(255, 0, 255), 3)  # Magenta, easy to detect
            painter.setPen(pen)
            # Horizontal line
            painter.drawLine(x - 30, y, x + 30, y)
            # Vertical line
            painter.drawLine(x, y - 30, x, y + 30)
            # Small filled circle at exact center
            painter.setBrush(QBrush(QColor(255, 0, 255)))
            painter.drawEllipse(x - 4, y - 4, 8, 8)

            # Label
            painter.setPen(QPen(QColor(255, 255, 0)))
            painter.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            painter.drawText(x + 15, y - 15, f"({x},{y})")

        painter.end()


class CursorTracker(QWidget):
    """Small window showing live cursor position."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(20, screen.height() - 80, 400, 50)
        self.setFixedSize(400, 50)

        self._text = "Move cursor..."
        timer = QTimer(self)
        timer.timeout.connect(self._update_pos)
        timer.start(50)

    def _update_pos(self):
        pos = QCursor.pos()
        self._text = f"Cursor: ({pos.x()}, {pos.y()}) logical"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(10, 10, 30, 230)))
        painter.drawRoundedRect(0, 0, w, h, 10, 10)
        painter.setPen(QPen(QColor(0, 255, 200)))
        painter.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        painter.drawText(16, 32, self._text)
        painter.end()


def find_magenta_center(img):
    """Find the center of magenta crosshairs in a PIL image."""
    pixels = img.load()
    w, h = img.size
    magenta_points = []
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y][:3]
            # Look for magenta-ish pixels (high red, low green, high blue)
            if r > 200 and g < 80 and b > 200:
                magenta_points.append((x, y))

    if not magenta_points:
        return []

    # Cluster the points into groups (one per crosshair)
    clusters = []
    used = set()
    for i, (px, py) in enumerate(magenta_points):
        if i in used:
            continue
        cluster = [(px, py)]
        used.add(i)
        for j, (qx, qy) in enumerate(magenta_points):
            if j in used:
                continue
            if abs(px - qx) < 80 and abs(py - qy) < 80:
                cluster.append((qx, qy))
                used.add(j)
        clusters.append(cluster)

    # Get center of each cluster
    centers = []
    for cluster in clusters:
        cx = sum(p[0] for p in cluster) / len(cluster)
        cy = sum(p[1] for p in cluster) / len(cluster)
        centers.append((int(cx), int(cy)))

    return sorted(centers, key=lambda p: (p[1], p[0]))


def main():
    app = QApplication(sys.argv)

    screen = app.primaryScreen()
    geo = screen.geometry()
    dpr = screen.devicePixelRatio()
    logical_w, logical_h = geo.width(), geo.height()

    print("=" * 60)
    print("CALIBRATION DIAGNOSTIC")
    print("=" * 60)
    print(f"Qt logical screen:  {logical_w} x {logical_h}")
    print(f"Qt screen position: ({geo.x()}, {geo.y()})")
    print(f"Device pixel ratio: {dpr}")
    print(f"Physical (calc):    {int(logical_w * dpr)} x {int(logical_h * dpr)}")

    # mss info
    sct = mss.mss()
    mon = sct.monitors[1]
    print(f"mss monitor[1]:     {mon}")
    print(f"mss size:           {mon['width']} x {mon['height']}")
    print(f"mss offset:         ({mon['left']}, {mon['top']})")

    # Draw crosshairs at known logical positions
    test_points = [
        (100, 100),
        (logical_w // 2, 100),
        (logical_w - 100, 100),
        (100, logical_h // 2),
        (logical_w // 2, logical_h // 2),
        (logical_w - 100, logical_h // 2),
    ]

    overlay = CalibrationOverlay()
    overlay.set_markers(test_points)
    overlay.show()

    cursor = CursorTracker()
    cursor.show()

    print(f"\nDrawing crosshairs at logical positions:")
    for x, y in test_points:
        print(f"  ({x}, {y})")

    # After a short delay, capture the screen and find where crosshairs appear
    def do_capture():
        print("\nCapturing screen with mss...")
        sct_img = sct.grab(mon)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        capture_w, capture_h = img.size
        print(f"mss capture size:   {capture_w} x {capture_h}")

        # Find crosshairs in full-res capture
        print("\nSearching for crosshairs in capture...")
        centers = find_magenta_center(img)
        print(f"Found {len(centers)} crosshairs in physical capture")

        if centers:
            print(f"\n{'Logical (drawn)':<22} {'Physical (found)':<22} {'Ratio (phys/log)':<22}")
            print("-" * 66)
            for i, (lx, ly) in enumerate(test_points):
                if i < len(centers):
                    px, py = centers[i]
                    rx = px / lx if lx else 0
                    ry = py / ly if ly else 0
                    print(f"  ({lx:4d}, {ly:4d})        ({px:4d}, {py:4d})        ({rx:.3f}, {ry:.3f})")

            # Also check thumbnail mapping
            thumb = img.copy()
            thumb.thumbnail((1024, 768))
            tw, th = thumb.size
            print(f"\nThumbnail size: {tw} x {th}")
            print(f"Scale logical→thumbnail:  {tw/logical_w:.4f}x, {th/logical_h:.4f}x")
            print(f"Scale thumbnail→logical:  {logical_w/tw:.4f}x, {logical_h/th:.4f}x")

            thumb_centers = find_magenta_center(thumb)
            print(f"Found {len(thumb_centers)} crosshairs in thumbnail")

            if thumb_centers:
                print(f"\n{'Logical (drawn)':<22} {'Thumbnail (found)':<22} {'Scaled back':<22} {'Error':<16}")
                print("-" * 82)
                scale_x = logical_w / tw
                scale_y = logical_h / th
                for i, (lx, ly) in enumerate(test_points):
                    if i < len(thumb_centers):
                        tx, ty = thumb_centers[i]
                        # Scale thumbnail coords back to logical
                        sx = int(tx * scale_x)
                        sy = int(ty * scale_y)
                        ex = sx - lx
                        ey = sy - ly
                        print(f"  ({lx:4d}, {ly:4d})        ({tx:4d}, {ty:4d})        ({sx:4d}, {sy:4d})        ({ex:+4d}, {ey:+4d})")

                print(f"\n{'='*60}")
                print("SUMMARY:")
                errors_x = []
                errors_y = []
                for i, (lx, ly) in enumerate(test_points):
                    if i < len(thumb_centers):
                        tx, ty = thumb_centers[i]
                        sx = int(tx * scale_x)
                        sy = int(ty * scale_y)
                        errors_x.append(sx - lx)
                        errors_y.append(sy - ly)
                if errors_x:
                    avg_ex = sum(errors_x) / len(errors_x)
                    avg_ey = sum(errors_y) / len(errors_y)
                    print(f"Average error X: {avg_ex:+.1f} px")
                    print(f"Average error Y: {avg_ey:+.1f} px")
                    print(f"This is the offset to SUBTRACT from scaled coordinates.")
                    if abs(avg_ex) > 5 or abs(avg_ey) > 5:
                        print(f"\n*** SIGNIFICANT OFFSET DETECTED ***")
                        print(f"Recommended fix: subtract ({int(avg_ex)}, {int(avg_ey)}) from overlay coords")
                    else:
                        print(f"\nOffset is small — scaling looks correct!")
                        print(f"Remaining error is likely Gemini's coordinate imprecision.")

        # Save capture for inspection
        img.save("calibration_capture.png")
        thumb.save("calibration_thumbnail.png")
        print(f"\nSaved: calibration_capture.png, calibration_thumbnail.png")
        print(f"\nCursor tracker active — move mouse around to verify positions.")
        print(f"Press Ctrl+C or close to exit.")

    QTimer.singleShot(1500, do_capture)
    app.exec()


if __name__ == "__main__":
    main()
