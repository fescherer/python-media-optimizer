# Media Optimizer

A small Windows desktop app that shrinks the photos and videos in a folder before you upload them to Google Drive.

- Pick a folder and a level (Light / Medium / Heavy), then click **Start**.
- The results go to a new folder next to the original, `<folder>_optimized` (or `_optimized_2`, `_3`, … if that name is taken), with the same subfolders.
- **Your originals are never modified, moved, renamed, or deleted.**
- If an optimized file would be bigger than the original, a plain copy of the original is used instead.
- Other files (documents and so on) are copied unchanged, so the output is a complete copy of your folder.
- `log.txt` in the output folder lists every file and what happened to it.

## What each level does

| Level  | Photos: longest side | Photo quality | Videos: max resolution | Video CRF | Audio |
|--------|----------------------|---------------|------------------------|-----------|-------|
| Light  | 3840 px              | 85            | original               | 23        | 160k  |
| Medium | 2560 px              | 75            | 1080p                  | 26        | 128k  |
| Heavy  | 1920 px              | 65            | 720p                   | 30        | 96k   |

Edit `optimizer/presets.py` to change these numbers.

- Images are never enlarged. Photos are rotated according to EXIF orientation, and EXIF data (date, camera, GPS) and the file date are kept where possible.
- JPEGs stay JPEG. PNGs stay PNG only if they have transparency; otherwise they become JPEG. HEIC (iPhone) becomes JPEG. WebP stays WebP.
- **Convert images to WebP** (checkbox, off by default): every image is saved as `.webp` instead, using the `webp_quality` of the chosen level, keeping transparency and EXIF. The WebP is kept even if it is larger than the original. Name clashes (`photo.jpg` + `photo.png`) become `photo.webp` and `photo_2.webp`.
- Animated or multi-page images (animated WebP, multi-page TIFF) are copied unchanged.
- Videos become MP4 (H.264 + AAC) so Google Drive can preview them. The video resolution limit applies to the *shorter* side, so portrait phone videos are handled correctly.
- If two files end up with the same name (e.g. `photo.png` and `photo.jpg` both become `photo.jpg`), the second is saved as `photo (2).jpg`.

## For users: run the .exe

Download `ImageVideoOptimizer.exe` and double-click it. You don't need to install Python or FFmpeg.

- **Requirements:** Windows 10 or 11 (64-bit). The app also needs the Microsoft Edge WebView2 Runtime, which those versions already include. If it's missing, the app says so and offers to open the [download page](https://developer.microsoft.com/microsoft-edge/webview2/).
- **"Windows protected your PC" warning:** the .exe isn't code-signed, so Windows SmartScreen may show this the first time. Click **More info**, then **Run anyway**.
- **Slow start:** the first launch takes a few seconds while the app unpacks itself into a temp folder.

## For developers: run from source

Requires Python 3.10 or newer (built and tested with 3.13).

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

`requirements.txt` pins exact versions so every build behaves the same. To upgrade, change the versions on purpose and run the testing checklist again.

## Build the .exe

```bash
build.bat
```

`build.bat` does the following:
1. Creates `.venv` if it doesn't exist yet.
2. Installs `requirements.txt` plus a pinned PyInstaller.
3. Creates a placeholder `assets\icon.ico` if there is none (via `assets\make_icon.py`).
4. Runs `PyInstaller --clean build.spec` and writes **`dist\ImageVideoOptimizer.exe`**.

What `build.spec` takes care of:

| Item | How |
|------|-----|
| UI files | `ui/` is bundled; `resource_path()` in `app.py` finds it in `sys._MEIPASS` when frozen |
| FFmpeg | `collect_all("imageio_ffmpeg")` bundles the binary; `imageio_ffmpeg.get_ffmpeg_exe()` finds it at runtime |
| HEIC support | `collect_all("pillow_heif")` bundles libheif |
| pywebview | The standard hook bundles the WebView2 DLLs; the spec adds pywebview's `js/` files, without which the buttons do nothing |
| No console window | `console=False`, and FFmpeg is started with `CREATE_NO_WINDOW` |
| Icon | `assets/icon.ico` (replace it with your own and rebuild) |

**Expected size: about 55 MB.** Most of it is the compressed FFmpeg binary (84 MB uncompressed).

**Nothing is written next to the .exe.** At startup it unpacks into `%TEMP%\_MEIxxxx`, which is removed when the app closes. Work files go to a temp folder, WebView2 browser data goes to a temp folder (private mode), and results go next to the folder you choose.

## Testing checklist (before sharing a new build)

Ideally use a clean Windows 10/11 machine or VM **without Python installed** (e.g. Windows Sandbox).

- [ ] Copy only `ImageVideoOptimizer.exe` into an empty folder and double-click it. The window opens with the app icon and no console window.
- [ ] **Choose folder** opens the native folder picker.
- [ ] Use a test folder with JPG, PNG, HEIC (iPhone) photos, a phone video (MOV/MP4) and a non-media file. Run **Medium**:
  - [ ] Photos, HEIC → JPG and videos → MP4 all appear in `<folder>_optimized`, and they open and play correctly.
  - [ ] No black console windows flash up while videos are encoding.
  - [ ] The progress bar and "File X of Y" update, and the summary shows sizes and % saved.
  - [ ] `log.txt` lists every file. The original folder is unchanged.
- [ ] Run again: the output goes to `_optimized_2`.
- [ ] Start a run, click **Cancel**, and confirm the popup. The run stops after the current file.
- [ ] Start a run and try to close the window. You get a popup, and the app stays open.
- [ ] After closing, the folder with the .exe contains only the .exe.
- [ ] Optional: on a PC without WebView2, the app shows the "WebView2 is missing" message instead of crashing.

## Notes

- **Cancel** stops after the current file finishes, so a long video may take a moment.
- Encoding videos is slow. Light keeps the original resolution, so it takes the longest.
- Some antivirus tools flag unsigned one-file PyInstaller apps by mistake. Code-signing the .exe avoids both this and the SmartScreen warning.
