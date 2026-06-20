import json
import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QMovie, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"


class WallpaperWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.movie = None
        self.media_player = None
        self.audio_output = None
        self.video_widget = None

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
        elif wallpaper_type == "video":
            self.load_video(full_path)
        else:
            self.show_error(f"Tipo no soportado todavia: {wallpaper_type}")

    def load_config(self):
        if not CONFIG_PATH.exists():
            self.show_error(f"No existe el archivo de config:\n{CONFIG_PATH}")
            return {}

        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            return json.load(file)

    def load_image(self, image_path):
        self.stop_media()
        self.ensure_label_view()

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

        self.label.setPixmap(scaled_pixmap)

    def load_gif(self, gif_path):
        self.stop_media()
        self.ensure_label_view()

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

    def load_video(self, video_path):
        self.stop_media()

        if not video_path.exists():
            self.show_error(f"No existe el video:\n{video_path}")
            return

        self.video_widget = QVideoWidget()
        self.setCentralWidget(self.video_widget)

        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.0)

        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl.fromLocalFile(str(video_path)))
        self.media_player.mediaStatusChanged.connect(self.handle_media_status)
        self.media_player.play()

    def handle_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia and self.media_player is not None:
            self.media_player.setPosition(0)
            self.media_player.play()

    def ensure_label_view(self):
        if self.centralWidget() is not self.label:
            self.setCentralWidget(self.label)

        self.label.setText("")
        self.label.setStyleSheet("background-color: black;")

    def stop_media(self):
        if self.media_player is not None:
            self.media_player.stop()

        self.media_player = None
        self.audio_output = None
        self.video_widget = None
        self.movie = None

    def show_error(self, message):
        self.stop_media()
        self.ensure_label_view()
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
