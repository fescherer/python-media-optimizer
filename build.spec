# PyInstaller spec: builds dist/ImageVideoOptimizer.exe (one file, no console window).
# Run with:  python -m PyInstaller --noconfirm --clean build.spec   (or just use build.bat)

import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = SPECPATH  # folder containing this spec file

datas = [(os.path.join(ROOT, "ui"), "ui")]  # index.html, style.css, app.js
binaries = []
hiddenimports = []

# imageio_ffmpeg: the bundled ffmpeg-*.exe plus the "binaries" subpackage that
#   get_ffmpeg_exe() uses to find it.
# pillow_heif: its compiled extension and libheif DLLs.
for package in ("imageio_ffmpeg", "pillow_heif"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# pywebview: the standard hook bundles its WebView2 DLLs (webview/lib) but not the
# JavaScript files it injects into the page (webview/js). Without them the
# window.pywebview.api bridge never appears and the buttons do nothing.
datas += collect_data_files("webview", subdir="js")
hiddenimports += ["webview.platforms.winforms", "webview.platforms.edgechromium", "clr"]

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "cefpython3"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ImageVideoOptimizer",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    console=False,   # --windowed: no console window
    upx=False,       # UPX often breaks DLLs and triggers antivirus false positives
    runtime_tmpdir=None,  # unpack into the user's %TEMP%, never next to the .exe
)
