"""scripts/preview.py: render a reply from a local export and post it through a
channel webhook."""

import io
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from builders import FETCHED_AT
from cobra_bot import messages
from cobra_bot.discord.api import text_payload

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"
DSS = str(FIXTURES_DIR / "dss.json")
WEBHOOK_TOKEN = "hook-secret_TOKEN-1"
WEBHOOK_URL = f"https://discord.com/api/webhooks/123/{WEBHOOK_TOKEN}"
ENV = {"DISCORD_PREVIEW_WEBHOOK_URL": WEBHOOK_URL}


def _http(status: int = 204) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def _dry_run(
    preview: ModuleType,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    snapshots: Path | None = None,
) -> list[dict[str, object]]:
    http, seen = _http()
    kwargs = {} if snapshots is None else {"snapshots": snapshots}
    code = preview.main(
        [*argv, "--dry-run"], env={}, http=http, clock=lambda: FETCHED_AT, **kwargs
    )
    assert code == 0
    assert seen == []
    payloads: list[dict[str, object]] = json.loads(capsys.readouterr().out)
    return payloads


def _description(payloads: list[dict[str, object]]) -> str:
    embeds = payloads[0]["embeds"]
    assert isinstance(embeds, list)
    description: str = embeds[0]["description"]
    return description


# --- what it renders ----------------------------------------------------------


@pytest.mark.parametrize("command", ["standings", "pairings"])
def test_dry_run_matches_the_production_golden_payloads(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    """Same embeds as the Worker: the golden files are the production renderer's
    output for the same fixture, tournament ID and fetch time."""
    payloads = _dry_run(preview_script, capsys, [DSS, command, "--id", "5018"])

    golden = json.loads(
        (GOLDEN_DIR / f"{command}_dss.json").read_text(encoding="utf-8")
    )
    assert payloads == golden


def test_pairings_round_option_is_passed_on(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    payloads = _dry_run(preview_script, capsys, [DSS, "pairings", "--round", "1"])

    assert "Round 1" in _description(payloads)


def test_player_query_is_passed_on_and_never_ephemeral(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """Channel webhooks cannot post ephemeral messages, so the flag is dropped."""
    payloads = _dry_run(preview_script, capsys, [DSS, "player", "Player0029"])

    assert "Player0029" in _description(payloads)
    assert all("flags" not in p for p in payloads)


def test_text_reply_uses_the_text_payload(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    payloads = _dry_run(preview_script, capsys, [DSS, "pairings", "--round", "99"])

    assert payloads == [text_payload(messages.round_out_of_range(99, 3))]


def test_fresh_by_default(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    payloads = _dry_run(preview_script, capsys, [DSS, "standings"])

    assert "Data from <t:" in _description(payloads)


def test_stale_renders_cobra_unavailable(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    payloads = _dry_run(preview_script, capsys, [DSS, "standings", "--stale"])

    assert "Cobra unavailable — data from <t:" in _description(payloads)


def test_private_renders_tournament_now_private(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    payloads = _dry_run(preview_script, capsys, [DSS, "standings", "--private"])

    assert "Tournament is now private — data from <t:" in _description(payloads)


def test_stale_and_private_are_exclusive(preview_script: ModuleType) -> None:
    with pytest.raises(SystemExit) as exit_info:
        preview_script.main([DSS, "standings", "--stale", "--private", "--dry-run"])

    assert exit_info.value.code == 2


def test_dry_run_writes_utf8_whatever_the_console_encoding(
    preview_script: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dss fixture has `Żółw` and `Maëlig`; a cp1250 console (Polish
    Windows) cannot encode `ë`."""
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1250"))

    code = preview_script.main(
        [DSS, "standings", "--dry-run"], env={}, clock=lambda: FETCHED_AT
    )

    assert code == 0
    out = raw.getvalue().decode("utf-8")
    assert "Żółw" in out
    assert "Maëlig" in out


# --- where the export comes from ----------------------------------------------


def _snapshot_dir(tmp_path: Path, tournament_id: str) -> Path:
    directory = tmp_path / tournament_id
    directory.mkdir()
    return directory


def test_id_picks_the_newest_snapshot_and_skips_meta_files(
    preview_script: ModuleType, tmp_path: Path
) -> None:
    directory = _snapshot_dir(tmp_path, "5018")
    for name in ("20261001T100000Z.json", "20261001T120000Z.json"):
        (directory / name).write_text("{}", encoding="utf-8")
    (directory / "20261001T130000Z.meta.json").write_text("{}", encoding="utf-8")

    path, tournament_id = preview_script.resolve_source("5018", tmp_path, None)

    assert path == directory / "20261001T120000Z.json"
    assert tournament_id == 5018


def test_id_without_a_snapshot_is_a_usage_error(
    preview_script: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = preview_script.main(
        ["5018", "standings", "--dry-run"], env={}, snapshots=tmp_path
    )

    assert code == 2
    assert "capture_snapshots.py 5018 --once" in capsys.readouterr().err


def test_snapshot_id_renders_under_that_id(
    preview_script: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = _snapshot_dir(tmp_path, "5018")
    (directory / "20261001T100000Z.json").write_bytes(Path(DSS).read_bytes())

    payloads = _dry_run(preview_script, capsys, ["5018", "standings"], tmp_path)

    embeds = payloads[0]["embeds"]
    assert isinstance(embeds, list)
    assert "/tournaments/5018/" in embeds[0]["url"]


def test_file_outside_an_id_directory_uses_the_default_id(
    preview_script: ModuleType,
) -> None:
    _, tournament_id = preview_script.resolve_source(DSS, Path("unused"), None)

    assert tournament_id == preview_script.DEFAULT_TOURNAMENT_ID


def test_file_in_an_id_directory_uses_that_id(
    preview_script: ModuleType, tmp_path: Path
) -> None:
    export = _snapshot_dir(tmp_path, "4909") / "20261001T100000Z.json"
    export.write_text("{}", encoding="utf-8")

    _, tournament_id = preview_script.resolve_source(str(export), tmp_path, None)

    assert tournament_id == 4909


def test_id_option_overrides_the_derived_id(preview_script: ModuleType) -> None:
    _, tournament_id = preview_script.resolve_source(DSS, Path("unused"), 77)

    assert tournament_id == 77


@pytest.mark.parametrize("value", ["0", "-3"])
def test_non_positive_id_option_is_a_usage_error(
    preview_script: ModuleType, value: str
) -> None:
    assert preview_script.main([DSS, "standings", "--id", value, "--dry-run"]) == 2


def test_source_that_is_neither_id_nor_file_is_a_usage_error(
    preview_script: ModuleType, tmp_path: Path
) -> None:
    code = preview_script.main(
        [str(tmp_path / "missing.json"), "standings", "--dry-run"], env={}
    )

    assert code == 2


def test_id_with_non_ascii_digits_is_not_an_id(
    preview_script: ModuleType, tmp_path: Path
) -> None:
    """`٥٠١٨` (Arabic-Indic digits) must not be read as tournament 5018."""
    with pytest.raises(preview_script.UsageError, match="neither"):
        preview_script.resolve_source("٥٠١٨", tmp_path, None)


def test_unparseable_export_renders_the_unreadable_data_message(
    preview_script: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    export = tmp_path / "broken.json"
    export.write_text("not json", encoding="utf-8")

    payloads = _dry_run(preview_script, capsys, [str(export), "standings"])

    assert payloads == [text_payload(messages.COBRA_DATA_UNREADABLE)]


# --- sending ------------------------------------------------------------------


def test_posts_every_payload_to_the_webhook(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = _dry_run(preview_script, capsys, [DSS, "standings"])
    http, seen = _http()

    code = preview_script.main(
        [DSS, "standings"], env=ENV, http=http, clock=lambda: FETCHED_AT
    )

    assert code == 0
    assert [(r.method, str(r.url)) for r in seen] == [
        ("POST", f"https://discord.com/api/v10/webhooks/123/{WEBHOOK_TOKEN}")
    ] * len(expected)
    assert [json.loads(r.content) for r in seen] == expected
    assert WEBHOOK_TOKEN not in capsys.readouterr().err


def test_player_warns_that_the_preview_is_public(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    http, _ = _http()

    assert preview_script.main([DSS, "player", "Player"], env=ENV, http=http) == 0

    assert "replies privately" in capsys.readouterr().err


def test_failed_post_exits_1_without_the_token(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    http, _ = _http(status=404)

    assert preview_script.main([DSS, "standings"], env=ENV, http=http) == 1

    err = capsys.readouterr().err
    assert "HTTP 404" in err
    assert WEBHOOK_TOKEN not in err


def test_missing_webhook_url_is_a_usage_error(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    http, seen = _http()

    assert preview_script.main([DSS, "standings"], env={}, http=http) == 2

    assert seen == []
    assert "DISCORD_PREVIEW_WEBHOOK_URL" in capsys.readouterr().err


@pytest.mark.parametrize(
    "url",
    [
        f"https://example.com/api/webhooks/123/{WEBHOOK_TOKEN}",
        f"http://discord.com/api/webhooks/123/{WEBHOOK_TOKEN}",
        f"https://discord.com/api/webhooks/abc/{WEBHOOK_TOKEN}",
        f"https://discord.com/api/webhooks/123/{WEBHOOK_TOKEN}/extra",
        f"https://discord.com/api/webhooks/123/{WEBHOOK_TOKEN}?wait=true",
    ],
)
def test_url_that_is_not_a_webhook_is_a_usage_error_and_never_printed(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str], url: str
) -> None:
    http, seen = _http()

    code = preview_script.main(
        [DSS, "standings"], env={"DISCORD_PREVIEW_WEBHOOK_URL": url}, http=http
    )

    assert code == 2
    assert seen == []
    assert WEBHOOK_TOKEN not in capsys.readouterr().err


@pytest.mark.parametrize(
    "url",
    [
        f"https://discordapp.com/api/webhooks/123/{WEBHOOK_TOKEN}",
        f"https://canary.discord.com/api/v10/webhooks/123/{WEBHOOK_TOKEN}",
        f"  {WEBHOOK_URL}\n",  # whitespace from copy-paste is stripped
    ],
)
def test_accepted_webhook_url_forms(preview_script: ModuleType, url: str) -> None:
    webhook_id, token = preview_script.webhook_target(
        {"DISCORD_PREVIEW_WEBHOOK_URL": url}
    )

    assert (webhook_id, token) == ("123", WEBHOOK_TOKEN)


# --- formats under test (B1, B2, C) -------------------------------------------

SSS = str(FIXTURES_DIR / "single_sided_top8.json")


def _walk(payload: object) -> list[dict[str, object]]:
    """Every dict nested in a payload."""
    found: list[dict[str, object]] = []
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            found.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


@pytest.fixture
def default_font(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pillow's built-in font instead of a system font."""
    from PIL import ImageFont

    from cobra_bot.preview import image

    font = ImageFont.load_default(image.FONT_SIZE)
    monkeypatch.setattr(image, "load_fonts", lambda *_: image.Fonts(font, font))


@pytest.mark.parametrize("layout", ["b1", "b2"])
def test_v2_formats_swap_interactive_components_for_links(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str], layout: str
) -> None:
    """A channel webhook rejects custom IDs and selects (HTTP 400)."""
    (payload,) = _dry_run(
        preview_script, capsys, [DSS, "pairings", "--format", layout, "--id", "5018"]
    )

    assert payload["flags"] == 1 << 15
    nested = _walk(payload)
    assert not [d for d in nested if "custom_id" in d or "options" in d]
    buttons = [d for d in nested if d.get("type") == 2]
    assert buttons
    assert all(b["style"] == 5 for b in buttons)
    assert {b["url"] for b in buttons} == {
        "https://tournaments.nullsignal.games/tournaments/5018"
    }


def test_mockup_turns_the_round_select_into_link_rows(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    (payload,) = _dry_run(preview_script, capsys, [DSS, "pairings", "--format", "b1"])

    rounds = [
        (d["label"], d["disabled"])
        for d in _walk(payload)
        if str(d.get("label", "")).startswith("Round ")
    ]
    assert sorted(rounds) == [("Round 1", False), ("Round 2", False), ("Round 3", True)]


def test_mockup_splits_options_into_rows_of_five(preview_script: ModuleType) -> None:
    select = {
        "type": 3,
        "custom_id": "cobra:round",
        "options": [{"label": f"Round {n}", "value": str(n)} for n in range(1, 8)],
    }
    row = {"type": 1, "components": [select]}
    payload = {"components": [{"type": 17, "components": [row]}]}

    mocked = preview_script.link_mockup(payload, "https://x.test")

    rows = mocked["components"][0]["components"]
    assert [len(r["components"]) for r in rows] == [5, 2]


def test_no_mockup_keeps_the_real_components(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    (payload,) = _dry_run(
        preview_script, capsys, [DSS, "pairings", "--format", "b1", "--no-mockup"]
    )

    nested = _walk(payload)
    assert any(d.get("custom_id") == "cobra:next" for d in nested)
    assert any(d.get("custom_id") == "cobra:round" for d in nested)


def test_v2_posts_ask_the_webhook_to_keep_components(
    preview_script: ModuleType,
) -> None:
    http, seen = _http()

    code = preview_script.main([DSS, "standings", "--format", "b2"], env=ENV, http=http)

    assert code == 0
    (request,) = seen
    assert request.url.params["with_components"] == "true"


def test_a_posts_do_not_set_with_components(preview_script: ModuleType) -> None:
    http, seen = _http()

    assert preview_script.main([DSS, "standings"], env=ENV, http=http) == 0

    assert all("with_components" not in r.url.params for r in seen)


@pytest.mark.parametrize("layout", ["b1", "b2", "c"])
def test_error_reply_is_the_bots_text_in_every_format(
    preview_script: ModuleType,
    capsys: pytest.CaptureFixture[str],
    layout: str,
    default_font: None,
) -> None:
    payloads = _dry_run(
        preview_script, capsys, [DSS, "pairings", "--round", "99", "--format", layout]
    )

    assert payloads == [text_payload(messages.round_out_of_range(99, 3))]


@pytest.mark.parametrize("layout", ["b2", "c"])
def test_player_has_only_formats_a_and_b1(
    preview_script: ModuleType,
    capsys: pytest.CaptureFixture[str],
    layout: str,
    default_font: None,
) -> None:
    code = preview_script.main(
        [DSS, "player", "Player", "--format", layout, "--dry-run"], env={}
    )

    assert code == 2
    assert "pairings and standings" in capsys.readouterr().err


def test_b1_player_cards(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    (payload,) = _dry_run(
        preview_script, capsys, [DSS, "player", "Player0029", "--format", "b1"]
    )

    assert "Player0029" in json.dumps(payload)


def test_page_option_picks_one_page(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    every = _dry_run(
        preview_script, capsys, [DSS, "pairings", "--format", "b1", "--all-pages"]
    )
    second = _dry_run(
        preview_script, capsys, [DSS, "pairings", "--format", "b1", "--page", "2"]
    )

    assert len(every) == 2
    assert second == [every[1]]


def test_page_past_the_last_is_a_usage_error(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    code = preview_script.main(
        [DSS, "pairings", "--format", "b1", "--page", "3", "--dry-run"], env={}
    )

    assert code == 2
    assert "has 2 page(s)" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_page_must_be_a_positive_number(preview_script: ModuleType, value: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        preview_script.main([DSS, "standings", "--format", "b1", "--page", value])

    assert exit_info.value.code == 2


def test_page_and_all_pages_are_exclusive(preview_script: ModuleType) -> None:
    with pytest.raises(SystemExit) as exit_info:
        preview_script.main([DSS, "standings", "--page", "1", "--all-pages"])

    assert exit_info.value.code == 2


def test_c_posts_the_png_as_multipart(
    preview_script: ModuleType, default_font: None
) -> None:
    http, seen = _http()

    code = preview_script.main(
        [SSS, "pairings", "--round", "1", "--format", "c"], env=ENV, http=http
    )

    assert code == 0
    (request,) = seen
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'filename="pairings-1.png"' in request.content
    assert b"attachment://pairings-1.png" in request.content


def test_save_images_writes_the_pngs(
    preview_script: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    default_font: None,
) -> None:
    out = tmp_path / "png"

    _dry_run(
        preview_script,
        capsys,
        [DSS, "standings", "--format", "c", "--save-images", str(out)],
    )

    assert (out / "standings-1.png").read_bytes().startswith(b"\x89PNG")


def test_missing_font_is_a_usage_error(
    preview_script: ModuleType,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cobra_bot.preview import image

    def no_font(*_: object) -> image.Fonts:
        raise image.FontNotFound("no system font found; pass one with --font")

    monkeypatch.setattr(image, "load_fonts", no_font)

    code = preview_script.main([DSS, "standings", "--format", "c", "--dry-run"], env={})

    assert code == 2
    assert "--font" in capsys.readouterr().err


def test_note_is_posted_first_as_plain_text(preview_script: ModuleType) -> None:
    http, seen = _http()

    code = preview_script.main(
        [DSS, "standings", "--note", "## B2 @everyone"], env=ENV, http=http
    )

    assert code == 0
    first, *rest = (json.loads(r.content) for r in seen)
    assert first == {"content": "## B2 @everyone", "allowed_mentions": {"parse": []}}
    assert rest
    assert all("embeds" in p for p in rest)


def test_rejected_post_prints_discords_reason_without_the_token(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"components": ["0"]})

    http = httpx.Client(transport=httpx.MockTransport(handler))

    code = preview_script.main(
        [DSS, "standings", "--format", "b1", "--no-mockup"], env=ENV, http=http
    )

    assert code == 1
    err = capsys.readouterr().err
    assert '{"components":["0"]}' in err.replace(" ", "")
    assert WEBHOOK_TOKEN not in err
