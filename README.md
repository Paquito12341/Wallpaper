# Personal Wallpaper

App personal tipo Wallpaper Engine hecha con Python y PySide6. Permite usar imagenes, GIFs, videos y HTML local como fondo animado en Windows.

## Opcion rapida para quien descarga el repo

1. Instalar Python 3.11 o superior.
2. Abrir PowerShell en esta carpeta.
3. Ejecutar:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

4. Abrir la app con doble clic en:

```text
Open Settings.bat
```

Ese archivo abre el panel de configuracion. Si existe un EXE compilado en `dist`, lo usa; si no, ejecuta `main.py --settings`.

## Ejecutar manualmente

Abrir fondo y panel de configuracion:

```powershell
python main.py --settings
```

Abrir solo la app en segundo plano:

```powershell
python main.py
```

## Fondos

Los fondos van en `wallpapers/`. El repo incluye ejemplos pequenos para que una descarga nueva funcione. Videos grandes o fondos personales no se suben a Git porque GitHub tiene limite de tamano.

## Crear EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

El ejecutable queda en:

```text
dist\PersonalWallpaper\PersonalWallpaper.exe
```

Despues de construir el EXE, `Open Settings.bat` lo abrira automaticamente.
