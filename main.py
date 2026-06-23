import json
import sys
import winreg
import ctypes
import win32api
import win32con
import win32com.client
import win32event
import win32gui
import winerror
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_PATH = BASE_DIR / "config.json"
RELOAD_SIGNAL_PATH = BASE_DIR / "reload.flag"
SHOW_SETTINGS_SIGNAL_PATH = BASE_DIR / "show_settings.flag"
ASSETS_DIR = BASE_DIR / "assets"
DEBUG = False
STARTUP_APP_NAME = "PersonalWallpaper"
STARTUP_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_SHORTCUT_NAME = "PersonalWallpaper.lnk"
APP_MUTEX_NAME = "PersonalWallpaperAppMutex"
APP_USER_MODEL_ID = "Ramon.PersonalWallpaper"
SETTINGS_ARGS = {"--settings", "--setting", "--config", "--steings"}
PERSONALIZE_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
DWM_REGISTRY_PATH = r"Software\Microsoft\Windows\DWM"
ACCENT_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
WINDOWS_THEME_MODES = {
    "No cambiar": "unchanged",
    "Oscuro": "dark",
    "Claro": "light",
}
ACCENT_COLOR_PRESETS = {
    "No cambiar": "",
    "Cian": "#00d4ff",
    "Azul": "#2563eb",
    "Morado": "#7c3aed",
    "Rosa": "#ec4899",
    "Rojo": "#ef4444",
    "Verde": "#22c55e",
    "Ambar": "#f59e0b",
}


def create_app_icon():
    for logo_name in ("logo.png", "app.png", "logo.ico", "app.ico"):
        logo_path = ASSETS_DIR / logo_name
        if logo_path.exists():
            if logo_path.suffix.lower() == ".png":
                pixmap = QPixmap(str(logo_path))
                if not pixmap.isNull():
                    icon = QIcon()
                    for size in (16, 24, 32, 48, 64, 128, 256):
                        icon.addPixmap(
                            pixmap.scaled(
                                size,
                                size,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation,
                            )
                        )
                    return icon

            icon = QIcon(str(logo_path))
            if not icon.isNull():
                return icon

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#00d4ff"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(8, 10, 48, 34, 8, 8)
    painter.setBrush(QColor("#7c3aed"))
    painter.drawRect(28, 44, 8, 8)
    painter.drawRoundedRect(20, 52, 24, 4, 2, 2)
    painter.setBrush(QColor("#ffffff"))
    painter.drawEllipse(42, 14, 10, 10)
    painter.end()

    return QIcon(pixmap)


def set_windows_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        pass


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


def signal_show_settings():
    SHOW_SETTINGS_SIGNAL_PATH.write_text("show\n", encoding="utf-8")


def is_settings_requested(args):
    return any(arg in SETTINGS_ARGS for arg in args)


def default_config():
    return {
        "current_wallpaper": {
            "type": "image",
            "path": "wallpapers/fondo1.jpg",
        },
        "windows_theme": {
            "apply": False,
            "mode": "unchanged",
            "accent_color": "",
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


def accent_color_to_registry_value(hex_color):
    clean_color = hex_color.strip().lstrip("#")
    if len(clean_color) != 6:
        return None

    try:
        red = int(clean_color[0:2], 16)
        green = int(clean_color[2:4], 16)
        blue = int(clean_color[4:6], 16)
    except ValueError:
        return None

    return 0xFF000000 | (blue << 16) | (green << 8) | red


def set_registry_dword(root, path, name, value):
    with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE) as registry_key:
        winreg.SetValueEx(registry_key, name, 0, winreg.REG_DWORD, value)


def broadcast_windows_theme_change():
    win32gui.SendMessageTimeout(
        win32con.HWND_BROADCAST,
        win32con.WM_SETTINGCHANGE,
        0,
        "ImmersiveColorSet",
        win32con.SMTO_ABORTIFHUNG,
        1000,
    )


def apply_windows_theme_settings(config):
    windows_theme = config.get("windows_theme", {})

    if not windows_theme.get("apply", False):
        return

    mode = windows_theme.get("mode", "unchanged")
    if mode in {"dark", "light"}:
        light_value = 1 if mode == "light" else 0
        set_registry_dword(
            winreg.HKEY_CURRENT_USER,
            PERSONALIZE_REGISTRY_PATH,
            "AppsUseLightTheme",
            light_value,
        )
        set_registry_dword(
            winreg.HKEY_CURRENT_USER,
            PERSONALIZE_REGISTRY_PATH,
            "SystemUsesLightTheme",
            light_value,
        )

    accent_value = accent_color_to_registry_value(windows_theme.get("accent_color", ""))
    if accent_value is not None:
        set_registry_dword(
            winreg.HKEY_CURRENT_USER,
            DWM_REGISTRY_PATH,
            "ColorizationColor",
            accent_value,
        )
        set_registry_dword(
            winreg.HKEY_CURRENT_USER,
            ACCENT_REGISTRY_PATH,
            "AccentColorMenu",
            accent_value,
        )
        set_registry_dword(
            winreg.HKEY_CURRENT_USER,
            ACCENT_REGISTRY_PATH,
            "StartColorMenu",
            accent_value,
        )

    broadcast_windows_theme_change()


def enable_startup():
    python_executable = Path(sys.executable)
    app_script = BASE_DIR / "main.py"

    if getattr(sys, "frozen", False):
        command = f'"{python_executable}"'
    else:
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

    create_startup_shortcut()


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

    shortcut_path = get_startup_shortcut_path()
    if shortcut_path.exists():
        shortcut_path.unlink()


def get_startup_shortcut_path():
    startup_folder = Path(
        win32com.client.Dispatch("WScript.Shell").SpecialFolders("Startup")
    )
    return startup_folder / STARTUP_SHORTCUT_NAME


def create_startup_shortcut():
    shortcut_path = get_startup_shortcut_path()
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))

    if getattr(sys, "frozen", False):
        shortcut.TargetPath = str(Path(sys.executable))
        shortcut.Arguments = ""
        shortcut.WorkingDirectory = str(BASE_DIR)
    else:
        shortcut.TargetPath = str(Path(sys.executable))
        shortcut.Arguments = f'"{BASE_DIR / "main.py"}"'
        shortcut.WorkingDirectory = str(BASE_DIR)

    shortcut.Description = "Personal Wallpaper"
    shortcut.Save()


class ConfigWindow(QWidget):
    def __init__(self, wallpaper_window=None, app_icon=None):
        super().__init__()

        self.wallpaper_window = wallpaper_window
        self.allow_quit = False
        self.setWindowTitle("Wallpaper Settings")
        if app_icon is not None:
            self.setWindowIcon(app_icon)
        self.setMinimumSize(960, 620)
        self.setObjectName("settingsWindow")

        self.config = load_config() or default_config()
        wallpaper = self.config.get("current_wallpaper", {})
        self.selected_path = wallpaper.get("path", "")

        self.type_select = QComboBox()
        self.type_select.setObjectName("field")
        self.type_select.addItems(["image", "gif", "video", "html"])
        self.type_select.setCurrentText(wallpaper.get("type", "image"))

        self.path_input = QLineEdit(wallpaper.get("path", ""))
        self.path_input.setObjectName("field")

        self.browse_button = QPushButton("Elegir...")
        self.browse_button.setObjectName("secondaryButton")
        self.browse_button.clicked.connect(self.choose_file)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_input)
        path_row.addWidget(self.browse_button)

        self.startup_checkbox = QCheckBox("Iniciar con Windows")
        self.startup_checkbox.setChecked(self.config.get("start_with_windows", False))

        windows_theme = self.config.get("windows_theme", {})
        self.apply_windows_theme_checkbox = QCheckBox("Aplicar tema de Windows")
        self.apply_windows_theme_checkbox.setChecked(windows_theme.get("apply", False))

        self.windows_mode_select = QComboBox()
        self.windows_mode_select.setObjectName("field")
        self.windows_mode_select.addItems(WINDOWS_THEME_MODES.keys())
        saved_mode = windows_theme.get("mode", "unchanged")
        for label, value in WINDOWS_THEME_MODES.items():
            if value == saved_mode:
                self.windows_mode_select.setCurrentText(label)
                break

        self.accent_color_select = QComboBox()
        self.accent_color_select.setObjectName("field")
        self.accent_color_select.addItems(ACCENT_COLOR_PRESETS.keys())
        saved_accent = windows_theme.get("accent_color", "")
        for label, value in ACCENT_COLOR_PRESETS.items():
            if value.lower() == saved_accent.lower():
                self.accent_color_select.setCurrentText(label)
                break

        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self.save_settings)

        title = QLabel("Wallpaper Settings")
        title.setObjectName("title")

        subtitle = QLabel("Installed")
        subtitle.setObjectName("subtitle")

        tray_note = QLabel("La X oculta esta ventana. Para cerrar la app usa el icono de bandeja.")
        tray_note.setObjectName("note")
        tray_note.setWordWrap(True)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("field")
        self.search_input.setPlaceholderText("Buscar")
        self.search_input.textChanged.connect(self.populate_wallpaper_grid)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(12)
        self.grid_container.setLayout(self.grid_layout)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(260, 170)

        self.detail_title = QLabel("Selecciona un fondo")
        self.detail_title.setObjectName("detailTitle")
        self.detail_type = QLabel("")
        self.detail_type.setObjectName("detailMeta")
        self.detail_path = QLabel("")
        self.detail_path.setObjectName("detailMeta")
        self.detail_path.setWordWrap(True)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        form.addRow("Tipo", self.type_select)
        form.addRow("Archivo", path_row)
        form.addRow("", self.apply_windows_theme_checkbox)
        form.addRow("Windows", self.windows_mode_select)
        form.addRow("Acento", self.accent_color_select)

        top_bar = QHBoxLayout()
        top_bar.addWidget(title)
        top_bar.addStretch()
        top_bar.addWidget(self.startup_checkbox)

        library_header = QHBoxLayout()
        library_header.addWidget(subtitle)
        library_header.addStretch()
        library_header.addWidget(self.search_input)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("libraryScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.grid_container)

        library_layout = QVBoxLayout()
        library_layout.addLayout(library_header)
        library_layout.addWidget(scroll_area)

        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(12)
        detail_layout.addWidget(self.preview_label)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_type)
        detail_layout.addWidget(self.detail_path)
        detail_layout.addSpacing(8)
        detail_layout.addLayout(form)
        detail_layout.addWidget(tray_note)
        detail_layout.addStretch()
        detail_layout.addWidget(self.save_button)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(18)
        content_layout.addLayout(library_layout, 3)
        content_layout.addLayout(detail_layout, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)
        layout.addLayout(top_bar)
        layout.addLayout(content_layout)
        self.setLayout(layout)
        self.apply_styles()
        self.populate_wallpaper_grid()
        self.update_detail(self.selected_path, self.type_select.currentText())

    def apply_styles(self):
        self.setStyleSheet(
            """
            QWidget#settingsWindow {
                background: #111318;
                color: #eef2ff;
                font-family: Segoe UI;
                font-size: 13px;
            }

            QLabel#title {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
            }

            QLabel#subtitle {
                color: #aeb7c8;
                font-size: 15px;
                font-weight: 600;
            }

            QLabel#detailTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: 700;
            }

            QLabel#detailMeta {
                color: #9ca8ba;
                font-size: 12px;
            }

            QLabel#preview {
                background: #07090d;
                border: 1px solid #293143;
                border-radius: 8px;
            }

            QLabel#note {
                color: #8f9bb0;
                background: #181c24;
                border: 1px solid #252b36;
                border-radius: 8px;
                padding: 9px 11px;
            }

            QComboBox#field,
            QLineEdit#field {
                background: #1b202a;
                color: #f8fafc;
                border: 1px solid #303746;
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: #2563eb;
            }

            QComboBox#field:focus,
            QLineEdit#field:focus {
                border-color: #38bdf8;
            }

            QPushButton {
                border-radius: 8px;
                padding: 8px 12px;
            }

            QPushButton#primaryButton {
                background: #2563eb;
                color: white;
                border: 1px solid #3b82f6;
                font-weight: 600;
            }

            QPushButton#primaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#secondaryButton {
                background: #242a35;
                color: #e5e7eb;
                border: 1px solid #363f50;
            }

            QPushButton#secondaryButton:hover {
                background: #2d3544;
            }

            QCheckBox {
                color: #d8dee9;
                spacing: 8px;
            }

            QCheckBox::indicator {
                width: 17px;
                height: 17px;
            }

            QScrollArea#libraryScroll {
                background: transparent;
                border: 0;
            }

            QPushButton#tileButton {
                background: #171c25;
                color: #dbe4f0;
                border: 1px solid #283143;
                border-radius: 8px;
                text-align: bottom center;
                padding: 6px;
            }

            QPushButton#tileButton:hover {
                border-color: #38bdf8;
                background: #1f2632;
            }

            QPushButton#tileButton[selected="true"] {
                border: 2px solid #38bdf8;
                background: #172033;
            }
            """
        )

    def detect_wallpaper_type(self, path):
        suffix = Path(path).suffix.lower()

        if suffix == ".gif":
            return "gif"
        if suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
            return "video"
        if suffix in {".html", ".htm"}:
            return "html"

        return "image"

    def iter_wallpaper_files(self):
        wallpaper_dir = BASE_DIR / "wallpapers"
        supported = {
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".webp",
            ".gif",
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
            ".webm",
            ".html",
            ".htm",
        }

        if not wallpaper_dir.exists():
            return []

        return [
            path
            for path in sorted(wallpaper_dir.iterdir(), key=lambda item: item.name.lower())
            if path.is_file() and path.suffix.lower() in supported
        ]

    def create_thumbnail_icon(self, path, wallpaper_type):
        pixmap = QPixmap(180, 110)
        pixmap.fill(QColor("#151b25"))

        if wallpaper_type in {"image", "gif"}:
            loaded = QPixmap(str(path))
            if not loaded.isNull():
                scaled = loaded.scaled(
                    pixmap.size(),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                painter = QPainter(pixmap)
                x = (pixmap.width() - scaled.width()) // 2
                y = (pixmap.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
                painter.end()
                return QIcon(pixmap)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#111827"))
        painter.drawRoundedRect(0, 0, 180, 110, 10, 10)
        painter.setBrush(QColor("#2563eb" if wallpaper_type == "video" else "#7c3aed"))
        painter.drawEllipse(62, 28, 56, 56)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, wallpaper_type.upper())
        painter.end()
        return QIcon(pixmap)

    def populate_wallpaper_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        search = self.search_input.text().strip().lower()
        files = [
            path
            for path in self.iter_wallpaper_files()
            if not search or search in path.name.lower()
        ]

        columns = 4
        for index, path in enumerate(files):
            wallpaper_type = self.detect_wallpaper_type(path)
            config_path = to_config_path(path)
            button = QPushButton(path.stem)
            button.setObjectName("tileButton")
            button.setCheckable(True)
            button.setProperty("selected", str(config_path == self.selected_path).lower())
            button.setIcon(self.create_thumbnail_icon(path, wallpaper_type))
            button.setIconSize(QSize(148, 88))
            button.setFixedSize(166, 132)
            button.clicked.connect(
                lambda _, selected_path=config_path, selected_type=wallpaper_type: self.select_wallpaper(
                    selected_path,
                    selected_type,
                )
            )

            row = index // columns
            column = index % columns
            self.grid_layout.addWidget(button, row, column)

        self.grid_layout.setRowStretch((len(files) // columns) + 1, 1)

    def select_wallpaper(self, path, wallpaper_type):
        self.selected_path = path
        self.path_input.setText(path)
        self.type_select.setCurrentText(wallpaper_type)
        self.update_detail(path, wallpaper_type)
        self.populate_wallpaper_grid()

    def update_detail(self, path, wallpaper_type):
        if not path:
            self.detail_title.setText("Selecciona un fondo")
            self.detail_type.setText("")
            self.detail_path.setText("")
            self.preview_label.clear()
            return

        full_path = BASE_DIR / path
        self.detail_title.setText(full_path.stem)
        self.detail_type.setText(wallpaper_type.upper())
        self.detail_path.setText(path)
        self.preview_label.setPixmap(
            self.create_thumbnail_icon(full_path, wallpaper_type).pixmap(260, 170)
        )

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
            config_path = to_config_path(path)
            wallpaper_type = self.detect_wallpaper_type(path)
            self.selected_path = config_path
            self.path_input.setText(config_path)
            self.type_select.setCurrentText(wallpaper_type)
            self.update_detail(config_path, wallpaper_type)
            self.populate_wallpaper_grid()

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
            "windows_theme": {
                "apply": self.apply_windows_theme_checkbox.isChecked(),
                "mode": WINDOWS_THEME_MODES.get(
                    self.windows_mode_select.currentText(),
                    "unchanged",
                ),
                "accent_color": ACCENT_COLOR_PRESETS.get(
                    self.accent_color_select.currentText(),
                    "",
                ),
            },
            "start_with_windows": self.startup_checkbox.isChecked(),
        }

        save_config(config)
        sync_startup_setting(config)
        apply_windows_theme_settings(config)
        if self.wallpaper_window is not None:
            self.wallpaper_window.force_reload_wallpaper()
        QMessageBox.information(
            self,
            "Guardado",
            "Configuracion guardada y aplicada.",
        )

    def closeEvent(self, event):
        if not self.allow_quit:
            event.ignore()
            self.hide()
            return

        if self.wallpaper_window is not None:
            self.wallpaper_window.close()

        event.accept()


class TrayController:
    def __init__(self, app, settings_window, wallpaper_window, app_icon):
        self.app = app
        self.settings_window = settings_window
        self.wallpaper_window = wallpaper_window
        self.show_settings_mtime = self.get_show_settings_mtime()

        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(app_icon)
        self.tray_icon.setToolTip("Wallpaper Settings")

        menu = QMenu()

        open_settings_action = QAction("Abrir settings", menu)
        open_settings_action.triggered.connect(self.open_settings)
        menu.addAction(open_settings_action)

        exit_action = QAction("Cerrar wallpaper", menu)
        exit_action.triggered.connect(self.quit_app)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.handle_activation)
        self.tray_icon.show()
        self.tray_icon.showMessage(
            "Wallpaper Settings",
            "Settings queda aqui. Usa este icono para abrirlo o cerrar el wallpaper.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

        self.show_settings_timer = QTimer()
        self.show_settings_timer.timeout.connect(self.open_settings_if_requested)
        self.show_settings_timer.start(500)

    def get_show_settings_mtime(self):
        if not SHOW_SETTINGS_SIGNAL_PATH.exists():
            return None

        return SHOW_SETTINGS_SIGNAL_PATH.stat().st_mtime

    def open_settings_if_requested(self):
        current_mtime = self.get_show_settings_mtime()

        if current_mtime is None or current_mtime == self.show_settings_mtime:
            return

        self.show_settings_mtime = current_mtime
        self.open_settings()

    def handle_activation(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_settings()

    def open_settings(self):
        self.settings_window.showNormal()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def quit_app(self):
        self.settings_window.allow_quit = True
        self.tray_icon.hide()
        self.wallpaper_window.close()
        self.settings_window.close()
        self.app.quit()


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
        apply_windows_theme_settings(config)
        self.load_wallpaper()
        self.refresh_desktop_placement()

    def force_reload_wallpaper(self):
        self.config_mtime = self.get_config_mtime()
        self.reload_signal_mtime = self.get_reload_signal_mtime()
        config = self.load_config()
        sync_startup_setting(config)
        apply_windows_theme_settings(config)
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
    settings_requested = is_settings_requested(sys.argv[1:])
    app_mutex = win32event.CreateMutex(None, False, APP_MUTEX_NAME)
    already_running = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS

    if already_running:
        if settings_requested:
            signal_show_settings()
        return

    set_windows_app_id()
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.app_mutex = app_mutex
    app.setQuitOnLastWindowClosed(False)
    app_icon = create_app_icon()
    app.setWindowIcon(app_icon)

    config = load_config()
    sync_startup_setting(config)
    apply_windows_theme_settings(config)

    wallpaper_window = WallpaperWindow()

    settings_window = ConfigWindow(wallpaper_window, app_icon)
    app.tray_controller = TrayController(app, settings_window, wallpaper_window, app_icon)
    if settings_requested:
        settings_window.show()
    else:
        settings_window.hide()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
