"""Media Optimizer: shrink the photos and videos in a folder before uploading them to Google Drive."""

import os
import subprocess
import sys
import threading

import webview

from optimizer.runner import Runner


WEBVIEW2_DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"


def resource_path(relative):
    """Find bundled files both when run as a script and inside a PyInstaller .exe.

    A one-file .exe unpacks itself into a temp folder (sys._MEIPASS) at startup.
    That folder is read-only for our purposes: never write anything there.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def message_box(text, title="Media Optimizer", yes_no=False):
    """Native Windows message box (works before/without any window). Returns True for OK/Yes."""
    import ctypes
    MB_YESNO, MB_ICONWARNING, IDOK, IDYES = 0x04, 0x30, 1, 6
    flags = MB_ICONWARNING | (MB_YESNO if yes_no else 0)
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags) in (IDOK, IDYES)


def webview2_installed():
    """Check the registry for the Microsoft Edge WebView2 Runtime (same keys Microsoft documents)."""
    import winreg
    client = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    places = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\{client}"),  # 64-bit Windows
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\{client}"),              # 32-bit Windows
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\{client}"),               # per-user install
    ]
    for root, path in places:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            pass
    return False


class Api:
    """Methods JavaScript can call as window.pywebview.api.<name>().

    Attributes starting with '_' are not exposed to JavaScript.
    """

    def __init__(self):
        self._window = None
        self._runner = Runner()

    def pick_folder(self):
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

    def start(self, folder, level):
        try:
            self._runner.start(folder, level)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def cancel(self):
        self._runner.cancel()

    def get_progress(self):
        return self._runner.get_progress()

    def _on_closing(self):
        """Window close (X / Alt+F4): block it while a run is in progress."""
        if not self._runner.is_running():
            return True
        # This runs on the UI thread; evaluate_js waits for that same thread,
        # so show the in-page message from another thread.
        threading.Thread(target=self._window.evaluate_js, args=("showCloseBlocked()",), daemon=True).start()
        return False  # returning False keeps the window open

    def open_output(self):
        path = self._runner.get_progress()["output_dir"]
        if not path or not os.path.isdir(path):
            return
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


def main():
    # Without WebView2, pywebview silently falls back to old Internet Explorer,
    # which can't run this UI. Explain and offer the download instead.
    if sys.platform == "win32" and not webview2_installed():
        if message_box(
            "This app needs the Microsoft Edge WebView2 Runtime, which is missing on this PC.\n\n"
            "It's a free, small download from Microsoft. Open the download page now?",
            yes_no=True,
        ):
            os.startfile(WEBVIEW2_DOWNLOAD_URL)
        return

    api = Api()
    window = webview.create_window(
        "Media Optimizer",
        url=resource_path(os.path.join("ui", "index.html")),
        js_api=api,
        width=640,
        height=760,
        min_size=(520, 640),
    )
    api._window = window
    window.events.closing += api._on_closing
    # private_mode keeps WebView2's browser data in a temp folder that is deleted
    # on exit, so nothing is ever written next to the .exe.
    webview.start(gui="edgechromium", private_mode=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # A --windowed .exe has no console, so show startup errors instead of vanishing.
        if sys.platform == "win32":
            message_box(f"The app could not start:\n\n{e}")
        raise
