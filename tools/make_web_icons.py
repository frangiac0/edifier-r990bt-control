"""Generate the phone remote icons (web/) from the app icon drawing."""

from pathlib import Path

from PIL import Image, ImageDraw

WEB = Path(__file__).resolve().parent.parent / "web"
BG = (246, 247, 249, 255)


def speaker(size: int, scale: float = 1.0) -> Image.Image:
    # Same drawing as edifier_ctl.gui.make_icon_image, drawn large for sharp edges.
    big = size * 4
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = big / 64 * scale
    off = big * (1 - scale) / 2
    box = lambda *v: tuple(off + x * s for x in v)  # noqa: E731
    d.rounded_rectangle(box(14, 4, 50, 60), radius=8 * s, fill=(29, 33, 41, 255))
    d.ellipse(box(22, 30, 42, 50), fill=(31, 111, 235, 255))
    d.ellipse(box(28, 36, 36, 44), fill=(29, 33, 41, 255))
    d.ellipse(box(28, 12, 36, 20), fill=(31, 111, 235, 255))
    return img.resize((size, size), Image.LANCZOS)


def on_background(size: int, scale: float) -> Image.Image:
    bg = Image.new("RGBA", (size, size), BG)
    bg.alpha_composite(speaker(size, scale))
    return bg


on_background(192, 0.86).save(WEB / "icon-192.png")
on_background(512, 0.86).save(WEB / "icon-512.png")
on_background(512, 0.62).save(WEB / "icon-maskable-512.png")  # safe zone for masks
print("icons written")
