import json
import sys
import winreg
import win32con
import win32gui
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
RELOAD_SIGNAL_PATH = BASE_DIR / "reload.flag"
DEBUG = False
STARTUP_APP_NAME = "PersonalWallpaper"
STARTUP_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def prepare_desktop_workerw():
    progman = win32gui.FindWindow("Progman", None)

    # Ask Explorer to create the extra WorkerW layer used for live wallpapers.
    for message_param in (0, 0xD):
        win32gui.SendMessageTimeout(
            progman,
            0x052C,
            message_param,
            0,
            win32con.SMTO_NORMAL,
            1000,
        )

    return progman


def find_desktop_icon_parent():
    progman = prepare_desktop_workerw()
    icon_parent = None
    shell_view = None

    def enum_windows(hwnd, _):
        nonlocal icon_parent, shell_view

        found_shell_view = win32gui.FindWindowEx(
            hwnd,
            0,
            "SHELLDLL_DefView",
            None,
        )

        if found_shell_view:
            icon_parent = hwnd
            shell_view = found_shell_view

    win32gui.EnumWindows(enum_windows, None)
    return icon_parent or progman, shell_view


def load_config():
    if not CONFIG_PATH.exists():
        return {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
        file.write("\n")

    signal_reload()


def signal_reload():
    RELOAD_SIGNAL_PATH.write_text("reload\n", encoding="utf-8")


def default_config():
    return {
        "current_wallpaper": {
            "type": "image",
            "path": "wallpapers/fondo1.jpg",
        },
        "start_with_windows": False,
    }


def to_config_path(path):
    absolute_path = Path(path).resolve()

    try:
        return str(absolute_path.relative_to(BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(absolute_path)


def sync_startup_setting(config):
    if config.get("start_with_windows", False):
        enable_startup()
    else:
        disable_startup()


def enable_startup():
    python_executable = Path(sys.executable)
    app_script = BASE_DIR / "main.py"
    command = f'"{python_executable}" "{app_script}"'

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        STARTUP_REGISTRY_PATH,
        0,
        winreg.KEY_SET_VALUE,
    ) as registry_key:
        winreg.SetValueEx(
            registry_key,
            STARTUP_APP_NAME,
            0,
            winreg.REG_SZ,
            command,
        )


def disable_startup():
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as registry_key:
            winreg.DeleteValue(registry_key, STARTUP_APP_NAME)
    except FileNotFoundError:
        pass


class ConfigWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Wallpaper Settings")
        self.setMinimumWidth(520)

        self.config = load_config() or default_config()
        wallpaper = self.config.get("current_wallpaper", {})

        self.type_select = QComboBox()
        self.type_select.addItems(["image", "gif", "video", "html"])
        self.type_select.setCurrentText(wallpaper.get("type", "image"))

        self.path_input = QLineEdit(wallpaper.get("path", ""))

        self.browse_button = QPushButton("Elegir...")
        self.browse_button.clicked.connect(self.choose_file)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_input)
        path_row.addWidget(self.browse_button)

        self.startup_checkbox = QCheckBox("Iniciar con Windows")
        self.startup_checkbox.setChecked(self.config.get("start_with_windows", False))

        self.save_button = QPushButton("Guardar")
        self.save_button.clicked.connect(self.save_settings)

        form = QFormLayout()
        form.addRow("Tipo", self.type_select)
        form.addRow("Archivo", path_row)
        form.addRow("", self.startup_checkbox)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        self.setLayout(layout)

    def choose_file(self):
        selected_type = self.type_select.currentText()
        filters = {
            "image": "Imagenes (*.png *.jpg *.jpeg *.bmp *.webp)",
            "gif": "GIFs (*.gif)",
            "video": "Videos (*.mp4 *.mov *.avi *.mkv *.webm)",
            "html": "HTML (*.html *.htm)",
        }

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Elegir fondo",
            str(BASE_DIR / "wallpapers"),
            filters.get(selected_type, "Todos los archivos (*.*)"),
        )

        if path:
            self.path_input.setText(to_config_path(path))

    def save_settings(self):
        wallpaper_path = self.path_input.text().strip()

        if not wallpaper_path:
            QMessageBox.warning(self, "Falta archivo", "Elige un archivo de fondo.")
            return

        config = {
            "current_wallpaper": {
                "type": self.type_select.currentText(),
                "path": wallpaper_path,
            },
            "start_with_windows": self.startup_checkbox.isChecked(),
        }

        save_config(config)
        sync_startup_setting(config)
        QMessageBox.information(
            self,
            "Guardado",
            "Configuracion guardada. El fondo se actualizara si la app principal esta abierta.",
        )


class WallpaperWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.config_mtime = self.get_config_mtime()
        self.reload_signal_mtime = self.get_reload_signal_mtime()

        self.setWindowTitle("Personal Wallpaper")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )

        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        self.web_view.loadFinished.connect(self.on_web_load_finished)
        try:
            playback_gesture_setting = QWebEngineSettings.PlaybackRequiresUserGesture
        except AttributeError:
            playback_gesture_setting = (
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture
            )
        self.web_view.settings().setAttribute(playback_gesture_setting, False)
        self.setCentralWidget(self.web_view)

        self.load_wallpaper()
        self.showFullScreen()
        QTimer.singleShot(100, self.attach_to_desktop)
        QTimer.singleShot(1000, self.attach_to_desktop)

        self.config_timer = QTimer(self)
        self.config_timer.timeout.connect(self.reload_wallpaper_if_config_changed)
        self.config_timer.start(1000)

    def get_config_mtime(self):
        if not CONFIG_PATH.exists():
            return None

        return CONFIG_PATH.stat().st_mtime

    def get_reload_signal_mtime(self):
        if not RELOAD_SIGNAL_PATH.exists():
            return None

        return RELOAD_SIGNAL_PATH.stat().st_mtime

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
            self.load_media_html(full_path, "image")
        elif wallpaper_type == "gif":
            self.load_media_html(full_path, "image")
        elif wallpaper_type == "video":
            self.load_media_html(full_path, "video")
        elif wallpaper_type == "html":
            self.load_html(full_path)
        else:
            self.show_error(f"Tipo no soportado todavia: {wallpaper_type}")

    def reload_wallpaper_if_config_changed(self):
        current_mtime = self.get_config_mtime()
        current_signal_mtime = self.get_reload_signal_mtime()

        config_changed = current_mtime is not None and current_mtime != self.config_mtime
        reload_requested = (
            current_signal_mtime is not None
            and current_signal_mtime != self.reload_signal_mtime
        )

        if not config_changed and not reload_requested:
            return

        self.config_mtime = current_mtime
        self.reload_signal_mtime = current_signal_mtime
        config = self.load_config()
        sync_startup_setting(config)
        self.load_wallpaper()
        self.refresh_desktop_placement()

    def load_config(self):
        config = load_config()

        if not config:
            self.show_error(f"No existe el archivo de config:\n{CONFIG_PATH}")
            return {}

        return config

    def load_media_html(self, media_path, media_type):
        if not media_path.exists():
            self.show_error(f"No existe el archivo:\n{media_path}")
            return

        media_url = QUrl.fromLocalFile(str(media_path)).toString()
        body = self.build_video_html(media_url) if media_type == "video" else self.build_image_html(media_url)
        html = f"""
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            html, body {{
              margin: 0;
              width: 100%;
              height: 100%;
              overflow: hidden;
              background: black;
            }}
            img, video {{
              width: 100vw;
              height: 100vh;
              object-fit: cover;
              display: block;
            }}
          </style>
        </head>
        <body>
          {body}
        </body>
        </html>
        """
        self.web_view.setHtml(html, QUrl.fromLocalFile(str(BASE_DIR)))
        self.refresh_desktop_placement()

    def build_image_html(self, media_url):
        return f'<img src="{media_url}">'

    def build_video_html(self, media_url):
        return (
            f'<video src="{media_url}" autoplay loop muted playsinline '
            'preload="auto"></video>'
        )

    def load_html(self, html_path):
        if not html_path.exists():
            self.show_error(f"No existe el HTML:\n{html_path}")
            return

        self.web_view.load(QUrl.fromLocalFile(str(html_path)))
        self.refresh_desktop_placement()

    def show_error(self, message):
        escaped_message = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        html = f"""
        <!doctype html>
        <html>
        <body style="margin:0;background:#111;color:white;font:24px sans-serif;display:grid;place-items:center;height:100vh;">
          <div>{escaped_message}</div>
        </body>
        </html>
        """
        self.web_view.setHtml(html, QUrl.fromLocalFile(str(BASE_DIR)))
        self.refresh_desktop_placement()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def refresh_desktop_placement(self):
        self.showFullScreen()
        QTimer.singleShot(100, self.attach_to_desktop)
        QTimer.singleShot(1000, self.attach_to_desktop)

    def on_web_load_finished(self, _):
        self.web_view.page().runJavaScript(
            "const v = document.querySelector('video'); if (v) { v.muted = true; v.play().catch(() => {}); }"
        )
        self.refresh_desktop_placement()

    def attach_to_desktop(self):
        desktop_hwnd, shell_view_hwnd = find_desktop_icon_parent()
        window_hwnd = int(self.winId())

        if DEBUG:
            print(f"Wallpaper HWND: {window_hwnd}")
            print(f"Desktop HWND: {desktop_hwnd}")
            print(f"Shell view HWND: {shell_view_hwnd}")

        win32gui.SetParent(window_hwnd, desktop_hwnd)

        style = win32gui.GetWindowLong(window_hwnd, win32con.GWL_STYLE)
        style = style & ~win32con.WS_POPUP
        style = style | win32con.WS_VISIBLE | win32con.WS_CHILD
        win32gui.SetWindowLong(
            window_hwnd,
            win32con.GWL_STYLE,
            style,
        )

        extended_style = win32gui.GetWindowLong(window_hwnd, win32con.GWL_EXSTYLE)
        extended_style = extended_style & ~win32con.WS_EX_APPWINDOW
        extended_style = (
            extended_style
            | win32con.WS_EX_NOACTIVATE
            | win32con.WS_EX_TOOLWINDOW
        )
        win32gui.SetWindowLong(
            window_hwnd,
            win32con.GWL_EXSTYLE,
            extended_style,
        )

        screen = QApplication.primaryScreen().geometry()
        win32gui.SetWindowPos(
            window_hwnd,
            win32con.HWND_TOP,
            screen.x(),
            screen.y(),
            screen.width(),
            screen.height(),
            win32con.SWP_FRAMECHANGED | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
        )

        if shell_view_hwnd:
            win32gui.SetWindowPos(
                shell_view_hwnd,
                win32con.HWND_TOP,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE
                | win32con.SWP_SHOWWINDOW,
            )

        actual_parent = win32gui.GetParent(window_hwnd)
        if DEBUG:
            print(f"Actual parent HWND: {actual_parent}")


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)

    settings_args = {"--settings", "--setting", "--config", "--steings"}
    if any(arg in settings_args for arg in sys.argv[1:]):
        window = ConfigWindow()
        window.show()
        sys.exit(app.exec())

    config = load_config()
    sync_startup_setting(config)

    window = WallpaperWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
