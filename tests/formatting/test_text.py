import logging
from datetime import UTC, datetime, timedelta, timezone

import pytest

from cobra_bot import messages
from cobra_bot.formatting.identities import CORP_SHORT_NAMES, RUNNER_SHORT_NAMES
from cobra_bot.formatting.text import (
    code_text,
    corp_label,
    discord_timestamp,
    display_width,
    escape_markdown,
    fit,
    pad,
    runner_label,
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


ESC = chr(0x1B)
CJK = chr(0x6F22)  # a wide character
EMOJI = chr(0x1F600)
COMBINING_DIAERESIS = chr(0x0308)


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("@Mention", "@Mention"),  # pings are blocked by allowed_mentions (AC-21)
        ("*bold_name~", "*bold_name~"),  # markdown does not render in code blocks
        (r"back\slash", r"back\slash"),
        ("a`b", "a'b"),  # C-7
        ("```@everyone", "'''@everyone"),
        (f"red{ESC}[1;31mname", "red[1;31mname"),
        (f"bell{chr(7)}zero{chr(0x200B)}width", "bellzerowidth"),
        ("two\nlines\t here ", "two lines here"),
        ("cr\r\nlf", "cr lf"),
        (f"Mae{COMBINING_DIAERESIS}lig", "Maëlig"),  # NFC: one column per letter
        ("Żółw", "Żółw"),
        ("“curly” – dash", "“curly” – dash"),
    ],
    ids=[
        "mention",
        "markdown",
        "backslash",
        "backtick",
        "fence",
        "escape",
        "control-and-format",
        "whitespace",
        "crlf",
        "nfc",
        "polish",
        "punctuation",
    ],
)
def test_code_text(name: str, safe: str) -> None:
    assert code_text(name) == safe


@pytest.mark.parametrize(
    ("text", "width"),
    [
        ("abc", 3),
        ("Żółw", 4),  # diacritics take one column (C-5)
        (f"Mae{COMBINING_DIAERESIS}lig", 6),  # combining marks take none
        (f"a{CJK}b", 4),  # wide characters take two
        (f"a{EMOJI}b", 4),
        ("", 0),
    ],
)
def test_display_width(text: str, width: int) -> None:
    assert display_width(text) == width


@pytest.mark.parametrize(
    ("text", "width", "fitted"),
    [
        ("abcd", 5, "abcd"),  # one below
        ("abcde", 5, "abcde"),  # at the limit
        ("abcdef", 5, "abcd…"),  # one above
        ("", 5, ""),
        (f"ab{CJK}{CJK}", 5, f"ab{CJK}…"),  # cut by columns, not characters
        (f"abc{CJK}d", 5, "abc…"),  # a wide char that would overflow is dropped
    ],
)
def test_fit(text: str, width: int, fitted: str) -> None:
    assert fit(text, width) == fitted


def test_twenty_character_name_is_cut_to_fifteen_plus_ellipsis() -> None:
    """Embed format acceptance 4."""
    assert fit("A" * 20, 16) == "A" * 15 + "…"


@pytest.mark.parametrize(
    ("text", "padded"),
    [("ab", "ab   "), (f"{EMOJI}a", f"{EMOJI}a  "), ("abcdef", "abcdef")],
)
def test_pad_uses_display_width(text: str, padded: str) -> None:
    assert pad(text, 5) == padded


@pytest.mark.parametrize(
    ("identity", "label"),
    [
        ("Nuvem SA: Law of the Land", "Nuvem"),
        ("Haas-Bioroid: Precision Design", "HB"),
        ("Earth Station: SEA Headquarters", "Earth St."),
        ("The Zwicky Group: Invisible Hands", "Zwicky"),
        ("Jinteki: Personal Evolution", "Jinteki"),  # fallback: the full name
        ("Thunderbolt Armaments: Peace", "Thunderb…"),  # cut to 9 columns
        (None, messages.UNKNOWN_IDENTITY),  # A-4
        ("", messages.UNKNOWN_IDENTITY),
        (": nameless", messages.UNKNOWN_IDENTITY),
        (f"{ESC}: X", messages.UNKNOWN_IDENTITY),  # nothing left once made safe
    ],
)
def test_corp_label(identity: str | None, label: str) -> None:
    """FR-08, A-1–A-4."""
    assert corp_label(identity) == label


@pytest.mark.parametrize(
    ("identity", "label"),
    [
        ("Arissana Rocha Nahu: Street Artist", "Arissana"),
        ('René "Loup" Arcemont: Party Animal', "Loup"),
        ("Captain Padma Isbister: Intrepid Explorer", "Padma"),
        ('Hiram "0mission" Svensson: X', "0mission"),  # A-3
        ('Kim "Ghost" Lee: X', "Ghost"),  # fallback: the nickname
        ("Ken “Express” Tenma: Disappeared Clone", "Express"),  # curly quotes
        ('Ken "" Tenma: Disappeared Clone', "Ken"),  # empty nickname: first word
        ("Virtual Intelligence, P.I.: X", "Virtual"),  # first word, comma dropped
        ("Rielle Peddler: Transhuman", "Rielle"),
        ("Wolfgangerovich Smith: X", "Wolfgang…"),  # cut to 9 columns
        (None, messages.UNKNOWN_IDENTITY),
    ],
)
def test_runner_label(identity: str | None, label: str) -> None:
    """FR-08, A-1–A-4."""
    assert runner_label(identity) == label


def test_short_names_fit_the_column() -> None:
    """A-1: every mapped name is at most 9 columns and already code-safe."""
    for name in (*CORP_SHORT_NAMES.values(), *RUNNER_SHORT_NAMES.values()):
        assert display_width(name) <= 9, name
        assert code_text(name) == name, name


def test_missing_id_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    """A-2 / acceptance 6: a fallback logs a warning, once per ID."""
    with caplog.at_level(logging.WARNING):
        corp_label("Jinteki: Personal Evolution")
        corp_label("Jinteki: Personal Evolution")
        runner_label("Rielle Peddler: Transhuman")

    assert [r.getMessage() for r in caplog.records] == [
        "corp ID missing from the short-name map: Jinteki",
        "runner ID missing from the short-name map: Rielle Peddler",
    ]


def test_mapped_id_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        corp_label("Nuvem SA: Law of the Land")
        runner_label(None)

    assert caplog.records == []


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
