"""Colours for tables in Discord ```ansi code blocks (SPEC §9; embed format C-5).

Discord renders a small set of SGR codes in its own fixed palette, which differs
between themes. Never use `30` (black on the dark code-block background); `37` is
dimmer than the default text, so it serves as the secondary colour. Mobile
clients show the text uncoloured; the columns still line up because a code block
uses a monospaced font.
"""

HEADING = "1;37"  # column headings
MUTED = "0;37"  # rank, table, SoS, rules, the losing player
STRONG = "1"  # player in standings, the winning player: bold, default colour
PLAIN = "0"  # player without a decided result (ID, unreported, bye)
SCORE = "1;33"  # points, scores
CORP = "0;34"  # Corp ID
RUNNER = "0;35"  # Runner ID

RESET = "\x1b[0m"
RULE = "─"


def sgr(style: str) -> str:
    return f"\x1b[{style}m"


def rule(width: int) -> str:
    return f"{sgr(MUTED)}{RULE * width}{RESET}"
