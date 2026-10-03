"""Fonts bundled for the reply images: Noto Sans Regular and Bold (SIL Open Font
License 1.1, `OFL.txt`), which cover the Latin Extended letters in player
names and IDs. Lambda has no system fonts, so they ship in the package.
"""

from importlib import resources

from PIL import ImageFont

from cobra_bot.formatting.image import FONT_SIZE, Fonts

REGULAR = "NotoSans-Regular.ttf"
BOLD = "NotoSans-Bold.ttf"


def load() -> Fonts:
    files = resources.files(__name__)
    with (
        resources.as_file(files / REGULAR) as regular,
        resources.as_file(files / BOLD) as bold,
    ):
        return Fonts(
            ImageFont.truetype(str(regular), FONT_SIZE),
            ImageFont.truetype(str(bold), FONT_SIZE),
        )
