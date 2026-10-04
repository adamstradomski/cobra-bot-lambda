"""`fonts.load`: the bundled fonts the Worker draws every reply image with."""

import hashlib
from importlib import resources

import pytest
from PIL import Image, ImageDraw, ImageFont

from cobra_bot import fonts as bundled_fonts
from cobra_bot.formatting.image import FONT_SIZE, Font, Fonts

NOTDEF = "\U000f0000"  # private use, in no font: drawn as the missing-glyph box


def test_load_gives_regular_and_bold_at_the_image_font_size(fonts: Fonts) -> None:
    assert isinstance(fonts.regular, ImageFont.FreeTypeFont)
    assert isinstance(fonts.bold, ImageFont.FreeTypeFont)
    assert fonts.regular.getname() == ("Noto Sans", "Regular")
    assert fonts.bold.getname() == ("Noto Sans", "Bold")
    assert fonts.regular.size == fonts.bold.size == FONT_SIZE


def test_digest_is_the_sha256_of_both_font_files(fonts: Fonts) -> None:
    files = resources.files(bundled_fonts)
    expected = hashlib.sha256(
        (files / bundled_fonts.REGULAR).read_bytes()
        + (files / bundled_fonts.BOLD).read_bytes()
    ).hexdigest()

    assert fonts.digest == expected


def _drawn(font: Font, text: str) -> bytes:
    image = Image.new("L", (4 * FONT_SIZE, 2 * FONT_SIZE))
    ImageDraw.Draw(image).text((0, 0), text, fill=255, font=font)
    return image.tobytes()


@pytest.mark.parametrize("letter", ["ł", "Ż", "ë", "ő", "ç", "ß"])
def test_latin_extended_letters_have_glyphs(fonts: Fonts, letter: str) -> None:
    """Player names use them; a missing glyph would draw as a box."""
    for font in (fonts.regular, fonts.bold):
        assert _drawn(font, letter) != _drawn(font, NOTDEF)
