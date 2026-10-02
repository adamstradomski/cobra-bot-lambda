"""Golden files and whole-output checks for the rendered fixtures (embed format
C-5, C-9, C-13, C-14, A-0; acceptance 1-2, 8).

`tests/golden/{renderer}_{fixture}.json` hold the expected payloads for the
anonymised fixtures `single_sided_top8` (the design's sample data) and `dss`
(double-sided, a round in progress). Regenerate them only with
`UPDATE_GOLDEN=1 uv run pytest tests/formatting/test_golden.py`, then review the
diff.
"""

import json
import os
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from builders import FETCHED_AT, plain
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.discord.api import message_payload
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import (
    PairingsView,
    StandingsView,
    pairings_view,
    standings_view,
    swiss_round_numbers,
)
from cobra_bot.formatting.chunking import DISCORD_LIMITS, Message, chunk
from cobra_bot.formatting.document import Document
from cobra_bot.formatting.pairings import format_pairings
from cobra_bot.formatting.standings import format_standings
from cobra_bot.formatting.text import display_width

type LoadRaw = Callable[[str], object]

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"
GOLDEN_FIXTURES = {"single_sided_top8": 4909, "dss": 5018}
FIXTURES = [("single_sided_top8", 4909), ("large_top_cut", 4990), ("dss", 5018)]
MAX_LINE_WIDTH = 34  # C-5
# §1.1: the only SGR codes allowed; `30` renders black on Discord's dark theme.
ALLOWED_SGR = {"0", "1", "0;37", "1;33", "0;34", "0;35"}
SGR = re.compile(r"\x1b\[([0-9;]*)m")
RESET = "\x1b[0m"
CODE_BLOCK = re.compile(r"```ansi\n(.*?)\n```", re.DOTALL)


def _standings(t: Tournament) -> Document:
    view = standings_view(t)
    assert isinstance(view, StandingsView)
    return format_standings(t, view)


def _pairings(t: Tournament) -> Document:
    view = pairings_view(t, None)
    assert isinstance(view, PairingsView)
    return format_pairings(t, view)


RENDERERS: dict[str, Callable[[Tournament], Document]] = {
    "standings": _standings,
    "pairings": _pairings,
}


def _parse(raw_fixture: LoadRaw, fixture: str, tid: int) -> Tournament:
    return parse_tournament(
        raw_fixture(fixture), tournament_id=tid, fetched_at=FETCHED_AT
    )


def _payloads(messages: tuple[Message, ...]) -> list[dict[str, object]]:
    return [message_payload(m) for m in messages]


def _every_document(t: Tournament) -> list[Document]:
    """Standings and the pairings of every Swiss round."""
    pairings = []
    for number in swiss_round_numbers(t):
        view = pairings_view(t, number)
        assert isinstance(view, PairingsView)
        pairings.append(format_pairings(t, view))
    return [_standings(t), *pairings]


def _table_lines(t: Tournament) -> list[str]:
    """Every line inside an ```ansi block of every rendered message."""
    lines = []
    for doc in _every_document(t):
        for message in chunk(doc):
            for embed in message:
                for part in (embed.description, *embed.fields):
                    for block in CODE_BLOCK.findall(part):
                        lines.extend(block.split("\n"))
    assert lines
    return lines


@pytest.mark.parametrize("fixture", sorted(GOLDEN_FIXTURES))
@pytest.mark.parametrize("name", sorted(RENDERERS))
def test_fixture_matches_golden(raw_fixture: LoadRaw, name: str, fixture: str) -> None:
    t = _parse(raw_fixture, fixture, GOLDEN_FIXTURES[fixture])
    rendered = json.dumps(
        _payloads(chunk(RENDERERS[name](t))), ensure_ascii=False, indent=2
    )
    path = GOLDEN_DIR / f"{name}_{fixture}.json"

    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    assert rendered + "\n" == path.read_text(encoding="utf-8")


def test_every_golden_file_has_a_renderer_and_fixture() -> None:
    expected = {f"{n}_{f}.json" for n in RENDERERS for f in GOLDEN_FIXTURES}

    assert {p.name for p in GOLDEN_DIR.glob("*.json")} == expected


@pytest.mark.parametrize(("fixture", "tid"), FIXTURES)
def test_table_lines_fit_34_columns(
    raw_fixture: LoadRaw, fixture: str, tid: int
) -> None:
    """C-5, acceptance 2: measured by display width without ANSI codes."""
    lines = _table_lines(_parse(raw_fixture, fixture, tid))

    too_wide = [p for p in map(plain, lines) if display_width(p) > MAX_LINE_WIDTH]
    assert too_wide == []


@pytest.mark.parametrize(("fixture", "tid"), FIXTURES)
def test_every_table_line_ends_with_a_reset(
    raw_fixture: LoadRaw, fixture: str, tid: int
) -> None:
    """A-0, acceptance 8; the blank lines between groups carry no codes at all."""
    lines = _table_lines(_parse(raw_fixture, fixture, tid))

    assert [line for line in lines if line and not line.endswith(RESET)] == []


@pytest.mark.parametrize(("fixture", "tid"), FIXTURES)
def test_colours_use_only_the_palette(
    raw_fixture: LoadRaw, fixture: str, tid: int
) -> None:
    """§1.1, A-0, acceptance 8: never `30`."""
    text = "\n".join(_table_lines(_parse(raw_fixture, fixture, tid)))

    used = set(SGR.findall(text))

    assert used  # the table is coloured at all
    assert used <= ALLOWED_SGR, used - ALLOWED_SGR


@pytest.mark.parametrize(("fixture", "tid"), FIXTURES)
def test_no_decorative_glyphs_or_hyphens_in_scores(
    raw_fixture: LoadRaw, fixture: str, tid: int
) -> None:
    """C-14, acceptance 8."""
    text = plain("\n".join(_table_lines(_parse(raw_fixture, fixture, tid))))

    assert "↳" not in text
    assert re.search(r"\d-\d", text) is None


@pytest.mark.parametrize(("fixture", "tid"), FIXTURES)
def test_every_rendered_fixture_is_within_discord_limits(
    raw_fixture: LoadRaw, fixture: str, tid: int
) -> None:
    """C-9."""
    limits = DISCORD_LIMITS
    t = _parse(raw_fixture, fixture, tid)

    for doc in _every_document(t):
        messages = chunk(doc)
        assert len(messages) <= limits.messages
        for message in messages:
            (embed,) = message
            assert embed.chars <= limits.chars_per_message
            assert len(embed.description) <= limits.description
            assert len(embed.fields) <= limits.fields
            assert all(len(value) <= limits.field_value for value in embed.fields)
            assert embed.title is None or len(embed.title) <= limits.title
            assert embed.footer is None or len(embed.footer) <= limits.footer
