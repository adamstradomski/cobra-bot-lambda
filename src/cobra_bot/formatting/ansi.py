"""Colours for tables in Discord ```ansi code blocks (SPEC §9; embed format §1.1).

Discord renders a small set of SGR codes in its own fixed palette, which differs
between themes. Never use `30` (black on the dark code-block background); `37` is
dimmer than the default text, so it serves as the secondary colour. `1` keeps the
previous colour, so bold default text is always `0` then `1` (A-0). Mobile clients
drop the colours, so no information depends on colour alone (C-6).
"""

PRIMARY = "\x1b[0m"  # rank, table label, a player without a decided result
STRONG = "\x1b[0m\x1b[1m"  # player in standings, the winner: bold, default colour
SECONDARY = "\x1b[0;37m"  # header, rule, SoS, the loser, `·`, an unknown ID
SCORE = "\x1b[1;33m"  # points
CORP = "\x1b[0;34m"  # Corp ID, the `C` tag
RUNNER = "\x1b[0;35m"  # Runner ID, the `R` tag

RESET = "\x1b[0m"  # ends every line (A-0)
RULE = "─"


def rule(width: int) -> str:
    return f"{SECONDARY}{RULE * width}{RESET}"
