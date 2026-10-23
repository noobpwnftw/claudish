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


def tile(text, font_path, fill, background, scale=0.62, size=BIG):
    """A tile that fills the whole icon square in its background colour (a small corner radius, so it
    reads as full size next to the tray's other icons), the text centred on its ink at the given
    proportion, drawn at 4x the target size and reduced once, so each size is crisp."""
    work = size * 4
    image = Image.new("RGBA", (work, work), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, work - 1, work - 1), radius=int(work * 0.14), fill=background)
    font = ImageFont.truetype(font_path, int(work * scale))
    left, top, width, height = text_box(draw, text, font)
    draw.text(((work - width) / 2 - left, (work - height) / 2 - top), text, font=font, fill=fill)
    return image.resize((size, size), Image.LANCZOS)


def ico(text, font_path, fill, background, scale):
    """Every size drawn at that size (not one big render shrunk), into one .ico."""
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    frames = [tile(text, font_path, fill, background, scale, size) for size in sizes]
    return frames


def save_frames(frames, path):
    largest = frames[-1]
    largest.save(path, format="ICO", sizes=[f.size for f in frames], append_images=frames[:-1])


def template(text, font_path, size):
    """A macOS menu-bar template: black glyphs on clear, cropped to the ink, height `size`."""
    font = ImageFont.truetype(font_path, BIG)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, width, height = text_box(probe, text, font)
    image = Image.new("RGBA", (width + 8, height + 8), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((4 - left, 4 - top), text, font=font, fill=(0, 0, 0, 255))
    ratio = size / image.height
    return image.resize((max(1, round(image.width * ratio)), size), Image.LANCZOS)


def main():
    windows = ROOT / "platforms/windows/claudish"
    # The compare's design (owner's pick): cream "cd", and inverted on a dark taskbar; "AI" on the accent.
    save_frames(ico("cd", SERIF, INK, PAPER, 0.62), windows / "icon.ico")
    save_frames(ico("cd", SERIF, INK, PAPER, 0.62), windows / "mode-continue.ico")
    save_frames(ico("cd", SERIF, PAPER, INK, 0.62), windows / "mode-continue-dark.ico")
    save_frames(ico("AI", MONO, (255, 255, 255, 255), ACCENT, 0.54), windows / "mode-compose.ico")
    template("cd", SERIF, 16).save(ROOT / "platforms/macos/cd.png")
    template("cd", SERIF, 32).save(ROOT / "platforms/macos/cd@2x.png")
    for folder in (ROOT / "site", ROOT / "claudish/web"):
        tile("cd", SERIF, INK, PAPER, 0.62, 64).save(folder / "favicon.png")
        tile("cd", SERIF, PAPER, INK, 0.62, 64).save(folder / "favicon-dark.png")
    print("icons written")


if __name__ == "__main__":
    main()
