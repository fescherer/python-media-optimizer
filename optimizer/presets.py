"""Optimization presets. Change the numbers here to tune the output."""

PRESETS = {
    "light": {
        "image_max_side": 3840,   # longest side in pixels
        "image_quality": 85,      # JPEG quality (1-100)
        "webp_quality": 85,       # WebP quality (1-100)
        "video_max_height": None, # None = keep original resolution
        "video_crf": 23,          # H.264 CRF: lower = better quality, bigger file
        "audio_bitrate": "160k",
    },
    "medium": {
        "image_max_side": 2560,
        "image_quality": 75,
        "webp_quality": 75,
        "video_max_height": 1080,
        "video_crf": 26,
        "audio_bitrate": "128k",
    },
    "heavy": {
        "image_max_side": 1920,
        "image_quality": 65,
        "webp_quality": 65,
        "video_max_height": 720,
        "video_crf": 30,
        "audio_bitrate": "96k",
    },
}

# File types we optimize (lowercase, with dot). Everything else is copied unchanged.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".webm"}
