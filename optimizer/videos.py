"""Video optimization with FFmpeg (binary bundled by imageio-ffmpeg)."""

import os
import subprocess

import imageio_ffmpeg

# Hide the console window FFmpeg would otherwise open on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _scale_filter(max_height):
    """Build the FFmpeg scale filter.

    "1080p" means the shorter side, so portrait phone videos are limited by width.
    Never upscales; width/height are kept even, which H.264 requires.
    -2 means "keep the aspect ratio, rounded to an even number".
    """
    if max_height is None:
        return "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    h = max_height
    return (
        f"scale=w='if(gte(iw,ih),-2,trunc(min(iw,{h})/2)*2)'"
        f":h='if(gte(iw,ih),trunc(min(ih,{h})/2)*2,-2)'"
    )


def optimize_video(src, work_dir, preset):
    """Re-encode one video to H.264/AAC MP4 inside work_dir. Returns the new file's path."""
    out_path = os.path.join(work_dir, "video.mp4")
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", src,                       # FFmpeg only reads the source
        "-map", "0:v:0", "-map", "0:a:0?",  # first video stream + first audio stream if any
        "-map_metadata", "0",            # keep creation date etc.
        "-vf", _scale_filter(preset["video_max_height"]),
        "-c:v", "libx264", "-preset", "medium", "-crf", str(preset["video_crf"]),
        "-pix_fmt", "yuv420p",           # most compatible; Google Drive can preview it
        "-c:a", "aac", "-b:a", preset["audio_bitrate"],
        "-movflags", "+faststart",
        out_path,
    ]
    result = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("FFmpeg failed: " + (error[-1] if error else f"exit code {result.returncode}"))
    return out_path
