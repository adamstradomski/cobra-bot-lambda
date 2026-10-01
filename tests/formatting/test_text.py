from datetime import UTC, datetime, timedelta, timezone

import pytest

from cobra_bot import messages
from cobra_bot.formatting.text import (
    discord_timestamp,
    escape_markdown,
    escape_ordered_list,
    short_identity,
    standings_url,
    tournament_url,
)


@pytest.mark.parametrize(
    ("name", "escaped"),
    [
        ("@Mention", "@Mention"),  # pings are blocked by allowed_mentions (AC-21)
        ("*bold_name~", r"\*bold\_name\~"),
        ("__under__", r"\_\_under\_\_"),
        ("~~strike~~", r"\~\~strike\~\~"),
        ("`code`", r"\`code\`"),
        ("||spoiler||", r"\|\|spoiler\|\|"),
        ("> quote", r"\> quote"),
        ("# Heading", r"\# Heading"),
        ("- item", r"\- item"),
        ("[click](https://evil.example)", r"\[click\]\(https\://evil.example\)"),
        ("<@123456>", r"\<@123456\>"),
        ("<t:0:R>", r"\<t\:0\:R\>"),
        (r"back\slash", r"back\\slash"),
        ("Maëlig", "Maëlig"),
        ("Żółw", "Żółw"),
        ("two\nlines\t here ", "two lines here"),
    ],
)
def test_escape_markdown(name: str, escaped: str) -> None:
    assert escape_markdown(name) == escaped


def test_escape_ordered_list_only_at_line_start() -> None:
    text = "1. Alice — 22 pts\n10. Bob scored 3. Then"

    assert escape_ordered_list(text) == "1\\. Alice — 22 pts\n10\\. Bob scored 3. Then"


@pytest.mark.parametrize(
    ("identity", "short"),
    [
        ("Nuvem SA: Law of the Land", "Nuvem SA"),
        ("Arissana Rocha Nahu: Street Artist", "Arissana Rocha Nahu"),
        ('Ken "Express" Tenma: Disappeared Clone', 'Ken "Express" Tenma'),
        ("The Catalyst", "The Catalyst"),
        ("A: B: C", "A"),
        (None, messages.UNKNOWN_IDENTITY),
        ("", messages.UNKNOWN_IDENTITY),
        ("  ", messages.UNKNOWN_IDENTITY),
        (": nameless", messages.UNKNOWN_IDENTITY),
    ],
)
def test_short_identity(identity: str | None, short: str) -> None:
    assert short_identity(identity) == short


def test_discord_timestamp() -> None:
    moment = datetime(2026, 10, 1, 12, 0, 30, tzinfo=UTC)

    assert discord_timestamp(moment) == "<t:1790856030:R>"
    assert discord_timestamp(moment, "f") == "<t:1790856030:f>"


def test_discord_timestamp_is_time_zone_independent() -> None:
    utc = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    warsaw = utc.astimezone(timezone(timedelta(hours=2)))

    assert discord_timestamp(utc) == discord_timestamp(warsaw)


def test_discord_timestamp_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        discord_timestamp(datetime(2026, 10, 1, 12, 0))


def test_cobra_urls() -> None:
    assert (
        tournament_url(4909) == "https://tournaments.nullsignal.games/tournaments/4909"
    )
    assert standings_url(4977) == (
        "https://tournaments.nullsignal.games/tournaments/4977/players/standings"
    )


def test_round_out_of_range_message() -> None:
    assert messages.round_out_of_range(15, 14) == (
        "Round 15 does not exist. This tournament has rounds 1–14."
    )
