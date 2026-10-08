"""Walks the source folder, optimizes or copies each file, and tracks progress.

Safety rules:
- The source folder is only ever read (open/copy). Nothing in it is changed.
- Encoders write into a temp folder; finished files are then moved to the output.
- Nothing in the output folder is ever overwritten.
"""

import os
import shutil
import tempfile
import threading
import time

from . import gif, images, videos
from .presets import IMAGE_EXTENSIONS, PRESETS, VIDEO_EXTENSIONS

GIF_WARNING_BYTES = 50 * 1024 * 1024  # warn about GIFs bigger than this


def human_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def make_output_dir(source):
    """Create '<name>_optimized' next to the source, or '_optimized_2', '_3'... if taken."""
    parent, name = os.path.split(source)
    base = os.path.join(parent, name + "_optimized")
    path, n = base, 2
    while os.path.exists(path):
        path = f"{base}_{n}"
        n += 1
    os.makedirs(path)
    return path


def unique_path(path):
    """Return path, or 'name (2).ext', 'name (3).ext'... if it already exists."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def numbered_path(path):
    """Return path, or 'name_2.ext', 'name_3.ext'... if it already exists."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"


def copy_original(src, dst):
    """Copy a source file unchanged (copy2 reads the source and keeps its dates)."""
    dst = unique_path(dst)
    shutil.copy2(src, dst)
    return dst


class Runner:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._state = self._new_state()

    @staticmethod
    def _new_state(status="idle"):
        return {
            "status": status,     # idle | running | done | cancelled | error
            "total": 0,
            "index": 0,           # number of the file being processed (1-based)
            "current": "",
            "processed": 0,       # optimized
            "skipped": 0,         # copied unchanged
            "failed": 0,
            "original_bytes": 0,
            "new_bytes": 0,
            "webp": False,        # "Convert images to WebP" option
            "webp_converted": 0,
            "gif": False,         # "Transform videos to GIF" option
            "gif_converted": 0,
            "gif_large": 0,       # GIFs over 50 MB or bigger than their video
            "output_dir": "",
            "message": "",
            "cancel_requested": False,
        }

    # ---- called from the UI thread -------------------------------------------------

    def get_progress(self):
        with self._lock:
            return dict(self._state)

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, source, level, to_webp=False, to_gif=False):
        if self.is_running():
            raise RuntimeError("Already running.")
        if level not in PRESETS:
            raise ValueError(f"Unknown level: {level}")
        source = os.path.normpath(os.path.abspath(source or ""))
        if not os.path.isdir(source):
            raise ValueError("Folder not found.")
        if os.path.dirname(source) == source:
            raise ValueError("Please choose a folder, not a whole drive.")

        self._cancel.clear()
        with self._lock:
            self._state = self._new_state("running")
            self._state["webp"] = bool(to_webp)
            self._state["gif"] = bool(to_gif)
        self._thread = threading.Thread(
            target=self._run, args=(source, PRESETS[level], level, bool(to_webp), bool(to_gif)), daemon=True)
        self._thread.start()

    def cancel(self):
        """Stop after the current file."""
        self._cancel.set()
        self._update(cancel_requested=True)

    # ---- background thread ---------------------------------------------------------

    def _update(self, **changes):
        with self._lock:
            self._state.update(changes)

    def _add(self, **amounts):
        with self._lock:
            for key, value in amounts.items():
                self._state[key] += value

    def _run(self, source, preset, level, to_webp, to_gif):
        try:
            self._process_folder(source, preset, level, to_webp, to_gif)
        except Exception as e:  # e.g. output folder can't be created
            self._update(status="error", message=str(e))

    def _process_folder(self, source, preset, level, to_webp, to_gif):
        # List everything first, so the new output folder can never end up in the list.
        rel_dirs, rel_files = [], []
        for dirpath, dirnames, filenames in os.walk(source):
            dirnames.sort()
            for d in dirnames:
                rel_dirs.append(os.path.relpath(os.path.join(dirpath, d), source))
            for f in sorted(filenames):
                rel_files.append(os.path.relpath(os.path.join(dirpath, f), source))

        output = make_output_dir(source)
        for d in rel_dirs:  # same subfolder structure, including empty folders
            os.makedirs(os.path.join(output, d), exist_ok=True)
        self._update(total=len(rel_files), output_dir=output)

        log_path = os.path.join(output, "log.txt")
        with open(log_path, "w", encoding="utf-8") as log, \
                tempfile.TemporaryDirectory(prefix="optimizer_", ignore_cleanup_errors=True) as tmp:
            log.write(f"Source: {source}\nOutput: {output}\nLevel:  {level}\n")
            webp = f"on (quality {preset['webp_quality']})" if to_webp else "off"
            log.write(f"Convert images to WebP: {webp}\n")
            gif_setting = f"on (max width {preset['gif_max_width']} px, {preset['gif_fps']} fps)" if to_gif else "off"
            log.write(f"Transform videos to GIF: {gif_setting}\n")
            log.write(f"Started {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            for i, rel in enumerate(rel_files, 1):
                if self._cancel.is_set():
                    break
                self._update(index=i, current=rel)
                status, detail, orig_size, new_size, out_rel = self._process_file(
                    source, output, rel, preset, tmp, to_webp, to_gif)
                arrow = f" -> {out_rel}" if out_rel and out_rel != rel else ""

                if status == "CANCELLED":  # stopped mid-file: nothing was written for it
                    log.write(f"{status:<10} {rel}  {detail}\n")
                    break

                counter = {"OPTIMIZED": "processed", "SKIPPED": "skipped", "FAILED": "failed"}[status]
                converted = int(status == "OPTIMIZED" and to_webp and out_rel.lower().endswith(".webp"))
                made_gif = status == "OPTIMIZED" and to_gif and out_rel.lower().endswith(".gif")
                gif_large = made_gif and (new_size > GIF_WARNING_BYTES or new_size > orig_size)
                self._add(**{counter: 1}, original_bytes=orig_size, new_bytes=new_size, webp_converted=converted,
                          gif_converted=int(made_gif), gif_large=int(gif_large))
                log.write(f"{status:<10} {rel}{arrow}  ({human_size(orig_size)} -> {human_size(new_size)})  {detail}\n")
                if gif_large:
                    reasons = [r for r, hit in (("over 50 MB", new_size > GIF_WARNING_BYTES),
                                                ("larger than the original video", new_size > orig_size)) if hit]
                    log.write(f"{'WARNING':<10} {out_rel} is {human_size(new_size)}: {' and '.join(reasons)}\n")
                log.flush()

            s = self.get_progress()
            cancelled = self._cancel.is_set()
            log.write("\n" + ("CANCELLED by user - output is incomplete.\n" if cancelled else ""))
            log.write(
                f"Finished {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Optimized: {s['processed']}  Copied unchanged: {s['skipped']}  Failed: {s['failed']}\n"
                f"Size: {human_size(s['original_bytes'])} -> {human_size(s['new_bytes'])}\n"
            )
            if to_webp:
                log.write(f"Converted to WebP: {s['webp_converted']}\n")
            if to_gif:
                log.write(f"Converted to GIF: {s['gif_converted']}\n")
                if s["gif_large"]:
                    log.write(f"GIFs over 50 MB or larger than the original video: {s['gif_large']}\n")
        self._update(status="cancelled" if cancelled else "done", current="")

    def _process_file(self, source, output, rel, preset, tmp, to_webp=False, to_gif=False):
        """Handle one file. Returns (status, detail, original_size, new_size, output_relpath)."""
        src = os.path.join(source, rel)
        dst = os.path.join(output, rel)
        ext = os.path.splitext(rel)[1].lower()
        orig_size = 0
        try:
            orig_size = os.path.getsize(src)

            # Forced conversions (WebP / GIF) are kept even when bigger, and get "_2" names on clashes.
            forced = (to_webp and ext in IMAGE_EXTENSIONS) or (to_gif and ext in VIDEO_EXTENSIONS)
            if ext in IMAGE_EXTENSIONS:
                optimize = lambda s, w, p: images.optimize_image(s, w, p, to_webp=to_webp)
            elif ext in VIDEO_EXTENSIONS and to_gif:
                optimize = lambda s, w, p: gif.video_to_gif(s, w, p, should_cancel=self._cancel.is_set)
            elif ext in VIDEO_EXTENSIONS:
                optimize = videos.optimize_video
            else:
                out = copy_original(src, dst)
                return "SKIPPED", "unsupported type, copied as-is", orig_size, orig_size, os.path.relpath(out, output)

            work = tempfile.mkdtemp(dir=tmp)  # per-file scratch folder
            try:
                try:
                    result = optimize(src, work, preset)
                except images.KeepOriginal as e:
                    out = copy_original(src, dst)
                    return "SKIPPED", str(e), orig_size, orig_size, os.path.relpath(out, output)
                except gif.Cancelled as e:
                    return "CANCELLED", str(e), orig_size, 0, ""

                new_size = os.path.getsize(result)
                # With WebP/GIF conversion on, the converted file is kept even if it came out bigger.
                if new_size >= orig_size and not forced:
                    out = copy_original(src, dst)
                    return "SKIPPED", "optimized file was not smaller, copied original", \
                        orig_size, orig_size, os.path.relpath(out, output)

                # Output may have a new extension (e.g. .heic -> .jpg, .mov -> .mp4).
                wanted = os.path.splitext(dst)[0] + os.path.splitext(result)[1]
                # WebP/GIF: 'photo.jpg' + 'photo.png' (or 'clip.mp4' + 'clip.mov') clash, so number the second one.
                out = numbered_path(wanted) if forced else unique_path(wanted)
                shutil.move(result, out)
                st = os.stat(src)
                os.utime(out, (st.st_atime, st.st_mtime))  # keep the original file date
                saved = 100 * (1 - new_size / orig_size) if orig_size else 0
                kept_as = os.path.splitext(out)[1].lstrip(".").upper()
                detail = f"saved {saved:.0f}%" if saved >= 0 else f"{-saved:.0f}% larger (kept as {kept_as})"
                if forced and out != wanted:
                    detail += f"; {os.path.basename(wanted)} already taken, renamed to {os.path.basename(out)}"
                return "OPTIMIZED", detail, orig_size, new_size, os.path.relpath(out, output)
            finally:
                shutil.rmtree(work, ignore_errors=True)

        except Exception as e:
            # Keep the output complete: fall back to a plain copy of the original.
            try:
                out = copy_original(src, dst)
                return "FAILED", f"{e} (original copied)", orig_size, orig_size, os.path.relpath(out, output)
            except Exception as copy_error:
                return "FAILED", f"{e}; copy also failed: {copy_error}", orig_size, 0, ""
