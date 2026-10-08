"""Video -> animated GIF with FFmpeg (binary bundled by imageio-ffmpeg)."""

import os
import subprocess
import time

import imageio_ffmpeg

# Hide the console window FFmpeg would otherwise open on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Cancelled(Exception):
    """Raised when the user cancels while a GIF is being made."""


def video_to_gif(src, work_dir, preset, should_cancel=lambda: False):
    """Convert one video to a GIF inside work_dir. Returns the new file's path.

    Uses a palette made from the video itself for good colors. Never upscales:
    videos narrower than gif_max_width keep their width. FFmpeg only reads the source.
    If should_cancel() becomes true, FFmpeg is stopped and Cancelled is raised;
    the unfinished GIF stays in work_dir, which the caller deletes.
    """
    out_path = os.path.join(work_dir, "video.gif")
    err_path = os.path.join(work_dir, "ffmpeg_errors.txt")
    fps, width = preset["gif_fps"], preset["gif_max_width"]
    filters = (
        f"fps={fps},scale=w='min(iw,{width})':h=-1:flags=lanczos,"
        "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5"
    )
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", src,
        "-map", "0:v:0", "-an",   # GIFs have no sound
        "-vf", filters,
        "-loop", "0",             # loop forever
        out_path,
    ]
    # Errors go to a file so a full pipe can never block FFmpeg.
    with open(err_path, "wb") as err:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err, creationflags=_NO_WINDOW
        )
        # Wait, but check for Cancel a few times per second.
        while proc.poll() is None:
            if should_cancel():
                proc.kill()
                proc.wait()  # make sure it has exited, so its files can be deleted
                raise Cancelled("cancelled while making the GIF; unfinished GIF deleted")
            time.sleep(0.2)

    if proc.returncode != 0:
        with open(err_path, encoding="utf-8", errors="replace") as f:
            lines = f.read().strip().splitlines()
        raise RuntimeError("FFmpeg failed: " + (lines[-1] if lines else f"exit code {proc.returncode}"))
    return out_path
