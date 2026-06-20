import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QMovie, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"


class WallpaperWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.movie = None

        self.setWindowTitle("Personal Wallpaper")
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: black;")
        self.setCentralWidget(self.label)

        self.load_wallpaper()
        self.showFullScreen()

    def load_wallpaper(self):
        config = self.load_config()
        wallpaper = config.get("current_wallpaper", {})

        wallpaper_type = wallpaper.get("type")
        wallpaper_path = wallpaper.get("path")

        if not wallpaper_path:
            self.show_error("Config invalida: falta la ruta del fondo.")
            return

        full_path = BASE_DIR / wallpaper_path

        if wallpaper_type == "image":
            self.load_image(full_path)
        elif wallpaper_type == "gif":
            self.load_gif(full_path)
        else:
            self.show_error(f"Tipo no soportado todavia: {wallpaper_type}")

    def load_config(self):
        if not CONFIG_PATH.exists():
            self.show_error(f"No existe el archivo de config:\n{CONFIG_PATH}")
            return {}

        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            return json.load(file)

    def load_image(self, image_path):
        pixmap = QPixmap(str(image_path))

        if pixmap.isNull():
            self.show_error(f"No se pudo cargar la imagen:\n{image_path}")
            return

        screen_size = QApplication.primaryScreen().size()
        scaled_pixmap = pixmap.scaled(
            screen_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )

        self.movie = None
        self.label.setPixmap(scaled_pixmap)

    def load_gif(self, gif_path):
        movie = QMovie(str(gif_path))

        if not movie.isValid():
            self.show_error(f"No se pudo cargar el GIF:\n{gif_path}")
            return

        screen_size = QApplication.primaryScreen().size()
        movie.setScaledSize(screen_size)

        self.label.clear()
        self.label.setMovie(movie)
        self.movie = movie
        movie.start()

    def show_error(self, message):
        self.movie = None
        self.label.setPixmap(QPixmap())
        self.label.setText(message)
        self.label.setStyleSheet(
            """
            QLabel {
                background-color: #111111;
                color: white;
                font-size: 24px;
            }
            """
        )

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
