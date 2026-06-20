import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


class WallpaperWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Personal Wallpaper")
        self.setWindowFlags(Qt.FramelessWindowHint)

        label = QLabel("Wallpaper app running\nPress Esc to close")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                background-color: #111111;
                color: white;
                font-size: 32px;
            }
        """)

        self.setCentralWidget(label)
        self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()


def main():
    app = QApplication(sys.argv)
    window = WallpaperWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()