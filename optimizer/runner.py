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

from . import images, videos
from .presets import IMAGE_EXTENSIONS, PRESETS, VIDEO_EXTENSIONS


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

    def start(self, source, level):
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
        self._thread = threading.Thread(target=self._run, args=(source, PRESETS[level], level), daemon=True)
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

    def _run(self, source, preset, level):
        try:
            self._process_folder(source, preset, level)
        except Exception as e:  # e.g. output folder can't be created
            self._update(status="error", message=str(e))

    def _process_folder(self, source, preset, level):
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
            log.write(f"Started {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            for i, rel in enumerate(rel_files, 1):
                if self._cancel.is_set():
                    break
                self._update(index=i, current=rel)
                status, detail, orig_size, new_size, out_rel = self._process_file(source, output, rel, preset, tmp)

                counter = {"OPTIMIZED": "processed", "SKIPPED": "skipped", "FAILED": "failed"}[status]
                self._add(**{counter: 1}, original_bytes=orig_size, new_bytes=new_size)
                arrow = f" -> {out_rel}" if out_rel and out_rel != rel else ""
                log.write(f"{status:<10} {rel}{arrow}  ({human_size(orig_size)} -> {human_size(new_size)})  {detail}\n")
                log.flush()

            s = self.get_progress()
            cancelled = self._cancel.is_set()
            log.write("\n" + ("CANCELLED by user - output is incomplete.\n" if cancelled else ""))
            log.write(
                f"Finished {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Optimized: {s['processed']}  Copied unchanged: {s['skipped']}  Failed: {s['failed']}\n"
                f"Size: {human_size(s['original_bytes'])} -> {human_size(s['new_bytes'])}\n"
            )
        self._update(status="cancelled" if cancelled else "done", current="")

    def _process_file(self, source, output, rel, preset, tmp):
        """Handle one file. Returns (status, detail, original_size, new_size, output_relpath)."""
        src = os.path.join(source, rel)
        dst = os.path.join(output, rel)
        ext = os.path.splitext(rel)[1].lower()
        orig_size = 0
        try:
            orig_size = os.path.getsize(src)

            if ext in IMAGE_EXTENSIONS:
                optimize = images.optimize_image
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

                new_size = os.path.getsize(result)
                if new_size >= orig_size:
                    out = copy_original(src, dst)
                    return "SKIPPED", "optimized file was not smaller, copied original", \
                        orig_size, orig_size, os.path.relpath(out, output)

                # Output may have a new extension (e.g. .heic -> .jpg, .mov -> .mp4).
                out = unique_path(os.path.splitext(dst)[0] + os.path.splitext(result)[1])
                shutil.move(result, out)
                st = os.stat(src)
                os.utime(out, (st.st_atime, st.st_mtime))  # keep the original file date
                saved = 100 * (1 - new_size / orig_size) if orig_size else 0
                return "OPTIMIZED", f"saved {saved:.0f}%", orig_size, new_size, os.path.relpath(out, output)
            finally:
                shutil.rmtree(work, ignore_errors=True)

        except Exception as e:
            # Keep the output complete: fall back to a plain copy of the original.
            try:
                out = copy_original(src, dst)
                return "FAILED", f"{e} (original copied)", orig_size, orig_size, os.path.relpath(out, output)
            except Exception as copy_error:
                return "FAILED", f"{e}; copy also failed: {copy_error}", orig_size, 0, ""
