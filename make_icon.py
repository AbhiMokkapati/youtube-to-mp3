"""One-off script: generates icon.ico (red rounded-square with a white play
triangle, YouTube-style) used by the desktop shortcut."""

from PIL import Image, ImageDraw

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

margin = 8
draw.rounded_rectangle(
    [margin, margin, SIZE - margin, SIZE - margin],
    radius=64, fill=(224, 33, 33, 255),
)

w, h = 76, 96
cx, cy = SIZE / 2 + 6, SIZE / 2
draw.polygon(
    [(cx - w / 2, cy - h / 2), (cx - w / 2, cy + h / 2), (cx + w / 2, cy)],
    fill=(255, 255, 255, 255),
)

img.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote icon.ico")
