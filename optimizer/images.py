"""Image optimization with Pillow (+ pillow-heif for iPhone HEIC photos)."""

import os

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()          # lets Image.open() read .heic/.heif
Image.MAX_IMAGE_PIXELS = None   # these are the user's own photos; allow huge panoramas

ORIENTATION_TAG = 0x0112


class KeepOriginal(Exception):
    """Raised when a file should be copied unchanged instead of optimized."""


def _has_transparency(img):
    """True if the image has at least one pixel that isn't fully opaque."""
    if img.mode in ("RGBA", "LA"):
        return img.getchannel("A").getextrema()[0] < 255
    return False


def optimize_image(src, work_dir, preset, to_webp=False):
    """Optimize one image and write the result into work_dir.

    The source is only opened for reading. Returns the path of the new file;
    its extension tells the caller the output format (.jpg, .png or .webp).
    With to_webp=True every image is saved as WebP (transparency kept).
    """
    ext = os.path.splitext(src)[1].lower()

    with Image.open(src) as im:
        # Saving would keep only the first frame, so leave animations/multi-page files alone.
        if ext not in (".heic", ".heif") and getattr(im, "n_frames", 1) > 1:
            raise KeepOriginal("animated or multi-page image, copied as-is")
        icc_profile = im.info.get("icc_profile")
        # Rotate pixels according to the EXIF orientation (returns a new, loaded image).
        img = ImageOps.exif_transpose(im)

    # Keep the EXIF data (date, camera, GPS...), but the pixels are upright now.
    exif = img.getexif()
    if ORIENTATION_TAG in exif:
        exif[ORIENTATION_TAG] = 1
    exif_bytes = exif.tobytes() if len(exif) else None

    # Palette / 1-bit / 16-bit images: convert to a normal mode so resizing works well.
    if img.mode not in ("RGB", "RGBA", "L", "LA", "CMYK"):
        has_alpha = "transparency" in img.info or img.mode == "PA"
        img = img.convert("RGBA" if has_alpha else "RGB")

    # Pick the output format.
    if to_webp:
        fmt, out_ext = "WEBP", ".webp"
        if _has_transparency(img):
            img = img.convert("RGBA")       # WebP stores RGB(A); keep the transparency
        elif img.mode != "RGB":
            if img.mode == "CMYK":
                icc_profile = None          # a CMYK profile doesn't fit RGB pixels
            img = img.convert("RGB")       # no real transparency: drop the alpha channel
    elif ext == ".webp":
        fmt, out_ext = "WEBP", ".webp"
    elif _has_transparency(img):
        fmt, out_ext = "PNG", ".png"        # PNG (or BMP/TIFF) with real transparency
    else:
        fmt = "JPEG"
        out_ext = ".jpeg" if ext == ".jpeg" else ".jpg"
        if img.mode not in ("RGB", "L", "CMYK"):
            img = img.convert("RGB")       # alpha is fully opaque here, safe to drop

    # Shrink only: thumbnail() keeps the aspect ratio and never upscales.
    max_side = preset["image_max_side"]
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    if fmt == "JPEG":
        options = {"quality": preset["image_quality"], "optimize": True, "progressive": True}
    elif fmt == "WEBP":
        options = {"quality": preset["webp_quality"], "method": 6}
    else:
        options = {"optimize": True}
    if icc_profile:
        options["icc_profile"] = icc_profile
    if exif_bytes and fmt != "PNG":
        options["exif"] = exif_bytes

    out_path = os.path.join(work_dir, "image" + out_ext)
    try:
        img.save(out_path, fmt, **options)
    except (ValueError, OSError):
        # Some files carry EXIF/ICC blocks too big for the format; retry without them.
        options.pop("exif", None)
        options.pop("icc_profile", None)
        img.save(out_path, fmt, **options)
    return out_path
