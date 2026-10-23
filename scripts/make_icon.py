"""Render cd_AI's icons from the wordmark's type (a serif "cd", a monospaced "AI"),
at high resolution and scaled down, so they are crisp at every size (G45; docs/design/visual.md).

  python scripts/make_icon.py        (needs Pillow and the Noto Serif / Noto Sans Mono fonts)

Writes, and these files are committed:
  platforms/windows/claudish/icon.ico            the input method (16-256 px): "cd" on cream
  platforms/windows/claudish/mode-continue.ico   continue: the same "cd" tile (-dark: inverted, for a dark taskbar)
  platforms/windows/claudish/mode-compose.ico    compose: "AI" on the accent colour
  platforms/macos/cd.png, cd@2x.png              the menu-bar template (black on clear; macOS tints it)
  site/favicon.png, claudish/web/favicon.png     the site's and the demo's icon

The fonts are open (SIL OFL): Noto Serif stands in for the site's Georgia, Noto Sans Mono for its
system monospace.
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SERIF = os.environ.get("CLAUDISH_SERIF", "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf")
MONO = os.environ.get("CLAUDISH_MONO", "/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf")
INK, PAPER, ACCENT = (31, 30, 29, 255), (250, 249, 245, 255), (217, 119, 87, 255)  # the site's tokens
BIG = 1024  # drawn at this size, then scaled down


def text_box(draw, text, font):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return left, top, right - left, bottom - top


def tile(text, font_path, fill, background, scale=0.62):
    """A rounded square with the text centred on its ink (not its line box), and a faint rim in the
    opposite tone, so a cream tile holds its edge on a light taskbar and a dark one on a dark taskbar."""
    image = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rim = (0, 0, 0, 40) if background == PAPER else (255, 255, 255, 60) if background == INK else None
    draw.rounded_rectangle((0, 0, BIG - 1, BIG - 1), radius=int(BIG * 0.22), fill=background,
                           outline=rim, width=int(BIG * 0.03) if rim else 0)
    font = ImageFont.truetype(font_path, int(BIG * scale))
    left, top, width, height = text_box(draw, text, font)
    draw.text(((BIG - width) / 2 - left, (BIG - height) / 2 - top), text, font=font, fill=fill)
    return image


def template(text, font_path, size):
    """A macOS menu-bar template: black glyphs on clear, cropped to the ink, height `size`."""
    font = ImageFont.truetype(font_path, BIG)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, width, height = text_box(probe, text, font)
    image = Image.new("RGBA", (width + 8, height + 8), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((4 - left, 4 - top), text, font=font, fill=(0, 0, 0, 255))
    ratio = size / image.height
    return image.resize((max(1, round(image.width * ratio)), size), Image.LANCZOS)


def save_ico(image, path):
    image.save(path, format="ICO", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])


def main():
    windows = ROOT / "platforms/windows/claudish"
    # Cream, the site's light look (owner's pick), and inverted for dark taskbars; the letters fill
    # the tile, so it is as big as the icons around it.
    brand = tile("cd", SERIF, INK, PAPER, scale=0.84)
    dark = tile("cd", SERIF, PAPER, INK, scale=0.84)
    save_ico(brand, windows / "icon.ico")
    save_ico(brand, windows / "mode-continue.ico")
    save_ico(dark, windows / "mode-continue-dark.ico")
    save_ico(tile("AI", MONO, (255, 255, 255, 255), ACCENT, scale=0.66), windows / "mode-compose.ico")
    template("cd", SERIF, 16).save(ROOT / "platforms/macos/cd.png")
    template("cd", SERIF, 32).save(ROOT / "platforms/macos/cd@2x.png")
    for folder in (ROOT / "site", ROOT / "claudish/web"):
        brand.resize((64, 64), Image.LANCZOS).save(folder / "favicon.png")
        dark.resize((64, 64), Image.LANCZOS).save(folder / "favicon-dark.png")
    print("icons written")


if __name__ == "__main__":
    main()
