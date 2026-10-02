"""Golden files: the full Discord payloads for the sample tournament (embed format
C-15, acceptance 1–2).

`tests/golden/*.json` hold the expected payloads for the anonymised fixture
`single_sided_top8` (the design's sample data). Regenerate them only with
`UPDATE_GOLDEN=1 uv run pytest tests/formatting/test_golden.py`, then review the
diff.
"""

import json
import os
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from builders import FETCHED_AT
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.discord.api import message_payload
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import (
    PairingsView,
    StandingsView,
    pairings_view,
    standings_view,
)
from cobra_bot.formatting.chunking import DISCORD_LIMITS, Message, chunk
from cobra_bot.formatting.document import Document
from cobra_bot.formatting.pairings import format_pairings
from cobra_bot.formatting.standings import format_standings

type LoadRaw = Callable[[str], object]

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"


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


def _payloads(messages: tuple[Message, ...]) -> list[dict[str, object]]:
    return [message_payload(m) for m in messages]


@pytest.mark.parametrize("name", sorted(RENDERERS))
def test_sample_tournament_matches_golden(raw_fixture: LoadRaw, name: str) -> None:
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    rendered = json.dumps(
        _payloads(chunk(RENDERERS[name](t))), ensure_ascii=False, indent=2
    )
    path = GOLDEN_DIR / f"{name}_single_sided_top8.json"

    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    assert rendered + "\n" == path.read_text(encoding="utf-8")


def test_every_golden_file_has_a_renderer() -> None:
    names = {p.name.split("_", 1)[0] for p in GOLDEN_DIR.glob("*.json")}

    assert names == set(RENDERERS)


FIXTURES = [("single_sided_top8", 4909), ("large_top_cut", 4990), ("dss", 5018)]
# C-5: the only SGR codes allowed; `30` renders black on Discord's dark theme.
ALLOWED_SGR = {"0", "1", "0;37", "1;37", "1;33", "0;34", "0;35"}
SGR = re.compile("\x1b\\[([0-9;]*)m")


@pytest.mark.parametrize(("fixture", "tid"), FIXTURES)
@pytest.mark.parametrize("name", sorted(RENDERERS))
def test_rendered_colours_use_only_the_c5_palette(
    raw_fixture: LoadRaw, fixture: str, tid: int, name: str
) -> None:
    t = parse_tournament(raw_fixture(fixture), tournament_id=tid, fetched_at=FETCHED_AT)

    messages = chunk(RENDERERS[name](t))

    text = "\n".join(p for m in messages for e in m for p in (e.description, *e.fields))
    used = set(SGR.findall(text))
    assert used  # the table is coloured at all
    assert used <= ALLOWED_SGR, used - ALLOWED_SGR
    assert not any("30" in code.split(";") for code in used)


@pytest.mark.parametrize(("fixture", "tid"), FIXTURES)
@pytest.mark.parametrize("name", sorted(RENDERERS))
def test_every_rendered_fixture_is_within_discord_limits(
    raw_fixture: LoadRaw, fixture: str, tid: int, name: str
) -> None:
    """C-11."""
    t = parse_tournament(raw_fixture(fixture), tournament_id=tid, fetched_at=FETCHED_AT)
    limits = DISCORD_LIMITS

    messages = chunk(RENDERERS[name](t))

    assert len(messages) <= limits.messages
    for message in messages:
        (embed,) = message
        assert embed.chars <= limits.chars_per_message
        assert len(embed.description) <= limits.description
        assert len(embed.fields) <= limits.fields
        assert all(len(value) <= limits.field_value for value in embed.fields)
        assert embed.title is None or len(embed.title) <= limits.title
        assert embed.footer is None or len(embed.footer) <= limits.footer
