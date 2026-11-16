"""Render cd_AI's icons from the wordmark's type (a serif "cd", a monospaced "AI"),
at high resolution and scaled down, so they are crisp at every size (G45; docs/design/design.md).

  python scripts/make_icon.py        (needs Pillow and the Noto Serif / Noto Sans Mono fonts)

Writes, and these files are committed:
  platforms/windows/claudish/icon.ico            the input method (16-256 px): "cd" on cream
  platforms/windows/claudish/mode-continue.ico   continue: the same "cd" tile
  platforms/windows/claudish/mode-compose.ico    compose: "AI" on the accent colour
  platforms/macos/cd.png, cd@2x.png              the menu-bar template: a tile with "cd" cut out, as macOS's
                                                 own "A" (black on clear; macOS tints it); continue
  platforms/macos/ai.png, ai@2x.png              compose's: the same tile with "AI"
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


def tile(text, font_path, fill, background, scale=0.72, size=BIG):
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
    """A macOS input-source template, as the system's own "A": a filled rounded tile with the text
    cut out of it (clear), black elsewhere, so macOS tints it for the menu bar and the input menu.
    `size` is the canvas height (16 at 1x): the tile fills it, as the system's does, a third wider
    than tall, the text's ink centred at 60% of the tile's height (the "A" letter's share)."""
    work = size * 16  # drawn large, reduced once
    tall, wide = work, round(work * 4 / 3)
    image = Image.new("L", (wide, work), 0)
    draw = ImageDraw.Draw(image)
    top = 0
    draw.rounded_rectangle((0, top, wide - 1, top + tall - 1), radius=round(tall * 0.22), fill=255)
    points = round(tall * 0.78)
    font = ImageFont.truetype(font_path, points)
    left, ink_top, width, height = text_box(draw, text, font)
    font = ImageFont.truetype(font_path, round(points * tall * 0.6 / height))  # ink 60% of the tile
    left, ink_top, width, height = text_box(draw, text, font)
    draw.text(((wide - width) / 2 - left, (work - height) / 2 - ink_top), text, font=font, fill=0)
    alpha = image.resize((round(wide / 16), size), Image.LANCZOS)
    black = Image.new("RGBA", alpha.size, (0, 0, 0, 255))
    black.putalpha(alpha)
    return black


def main():
    windows = ROOT / "platforms/windows/claudish"
    # One cream "cd" tile in both themes, never inverted: a tile the colour of the surface it sits on
    # vanishes (ink on a dark taskbar or tab strip, cream on a white tab), leaving only the letters at
    # half the square. Cream shows as a full square on dark surfaces; on light ones the letters, at 80%
    # of the width, fill the slot. "AI" on the accent shows on both.
    save_frames(ico("cd", SERIF, INK, PAPER, 0.72), windows / "icon.ico")
    save_frames(ico("cd", SERIF, INK, PAPER, 0.72), windows / "mode-continue.ico")
    save_frames(ico("AI", MONO, (255, 255, 255, 255), ACCENT, 0.66), windows / "mode-compose.ico")
    template("cd", SERIF, 16).save(ROOT / "platforms/macos/cd.png")
    template("cd", SERIF, 32).save(ROOT / "platforms/macos/cd@2x.png")
    template("AI", MONO, 16).save(ROOT / "platforms/macos/ai.png")
    template("AI", MONO, 32).save(ROOT / "platforms/macos/ai@2x.png")
    for folder in (ROOT / "site", ROOT / "claudish/web"):
        tile("cd", SERIF, INK, PAPER, 0.72, 64).save(folder / "favicon.png")
    print("icons written")


if __name__ == "__main__":
    main()
