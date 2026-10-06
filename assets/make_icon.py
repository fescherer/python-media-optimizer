"""Draw a simple placeholder app icon (assets/icon.ico). Replace icon.ico with your own anytime.

Run: python assets/make_icon.py
"""

import os

from PIL import Image, ImageDraw

SIZE = 256
BLUE = (37, 99, 235)
WHITE = (255, 255, 255)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Blue rounded square background
d.rounded_rectangle((8, 8, 248, 248), radius=52, fill=BLUE)

# White "photo" frame with a sun and mountains
d.rounded_rectangle((44, 60, 212, 188), radius=14, outline=WHITE, width=12)
d.ellipse((150, 82, 180, 112), fill=WHITE)
d.polygon([(56, 176), (108, 112), (146, 160), (166, 138), (200, 176)], fill=WHITE)

# Small "shrink" chevrons below the frame
d.polygon([(100, 204), (156, 204), (128, 232)], fill=WHITE)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Wrote", out)
