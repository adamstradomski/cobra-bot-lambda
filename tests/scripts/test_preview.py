"""scripts/preview.py: render a reply from a local export and post it through a
channel webhook."""

import io
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from builders import FETCHED_AT
from cobra_bot import messages
from cobra_bot.discord.api import text_payload

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
DSS = str(FIXTURES_DIR / "dss.json")
WEBHOOK_TOKEN = "hook-secret_TOKEN-1"
WEBHOOK_URL = f"https://discord.com/api/webhooks/123/{WEBHOOK_TOKEN}"
ENV = {"DISCORD_PREVIEW_WEBHOOK_URL": WEBHOOK_URL}
_PAYLOAD_JSON = re.compile(rb'name="payload_json"\r\n\r\n(.*?)\r\n--', re.DOTALL)


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


def _payload(request: httpx.Request) -> dict[str, object]:
    """The JSON body, also from a multipart request (a reply with an image)."""
    if request.headers["Content-Type"].startswith("multipart/form-data"):
        match = _PAYLOAD_JSON.search(request.content)
        assert match, "multipart request without payload_json"
        payload: dict[str, object] = json.loads(match.group(1))
        return payload
    payload = json.loads(request.content)
    return payload


def _description(payloads: list[dict[str, object]]) -> str:
    embeds = payloads[0]["embeds"]
    assert isinstance(embeds, list)
    description: str = embeds[0]["description"]
    return description


# --- what it renders ----------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [["standings"], ["pairings"], ["pairings", "--round", "1"], ["player", "0029"]],
)
def test_dry_run_matches_what_the_worker_sends(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    """Same messages as the bot: the Worker, run on the same export, sends the
    same payloads (images and their attachments included)."""
    from cobra_bot import fonts as bundled_fonts
    from cobra_bot.cobra.cache import InMemoryCacheStore, TournamentCache
    from cobra_bot.commands import Command, Job
    from cobra_bot.discord.api import WebhookClient
    from cobra_bot.handlers.worker import WorkerApp

    previewed = _dry_run(preview_script, capsys, [DSS, *argv, "--id", "5018"])

    class Export:
        def fetch_tournament(self, tournament_id: int) -> bytes:
            return Path(DSS).read_bytes()

        def resolve_shortcode(self, code: str) -> int:
            raise AssertionError("not used")

    http, seen = _http()
    cache = TournamentCache(InMemoryCacheStore(), Export(), clock=lambda: FETCHED_AT)
    worker = WorkerApp(
        cache, lambda app_id: WebhookClient(http, app_id), bundled_fonts.load()
    )
    name = argv[0]
    command = Command(
        name,  # type: ignore[arg-type]
        "5018",
        round=int(argv[2]) if len(argv) > 2 else None,
        query=argv[1] if name == "player" else None,
    )
    worker.handle(Job("app", "tok", command).to_payload())

    assert previewed == [_payload(r) for r in seen]


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
    """A cp1250 console (Polish Windows) cannot encode `ë`; the query is
    echoed in the header."""
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1250"))

    code = preview_script.main(
        [DSS, "player", "Maëlig", "--dry-run"], env={}, clock=lambda: FETCHED_AT
    )

    assert code == 0
    assert "Maëlig" in raw.getvalue().decode("utf-8")


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
    assert [_payload(r) for r in seen] == expected
    assert WEBHOOK_TOKEN not in capsys.readouterr().err


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


# --- images ---------------------------------------------------------------------


def test_images_are_posted_as_attachments(preview_script: ModuleType) -> None:
    http, seen = _http()

    code = preview_script.main([DSS, "pairings"], env=ENV, http=http)

    assert code == 0
    (request,) = seen
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'filename="pairings-1.png"' in request.content
    assert b"attachment://pairings-1.png" in request.content


def test_long_replies_send_every_page(
    preview_script: ModuleType,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cobra_bot.formatting import image

    monkeypatch.setattr(image, "MAX_ROWS", 10)  # 31 players: 4 pages

    payloads = _dry_run(preview_script, capsys, [DSS, "standings"])

    assert [p["attachments"] for p in payloads] == [
        [{"id": 0, "filename": f"standings-{n}.png"}] for n in range(1, 5)
    ]


def test_save_images_writes_the_pngs(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "png"

    _dry_run(preview_script, capsys, [DSS, "standings", "--save-images", str(out)])

    assert (out / "standings-1.png").read_bytes().startswith(b"\x89PNG")


def test_save_images_without_images_writes_nothing(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "png"

    _dry_run(
        preview_script, capsys, [DSS, "player", "nobody", "--save-images", str(out)]
    )

    assert list(out.iterdir()) == []


@pytest.mark.parametrize(
    "option", [["--format", "c"], ["--page", "2"], ["--all-pages"], ["--no-mockup"]]
)
def test_options_of_the_layout_trials_are_gone(
    preview_script: ModuleType, option: list[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        preview_script.main([DSS, "standings", *option, "--dry-run"])

    assert exit_info.value.code == 2


def test_note_is_posted_first_as_plain_text(preview_script: ModuleType) -> None:
    http, seen = _http()

    code = preview_script.main(
        [DSS, "standings", "--note", "## Standings @everyone"], env=ENV, http=http
    )

    assert code == 0
    first, *rest = (_payload(r) for r in seen)
    assert first == {
        "content": "## Standings @everyone",
        "allowed_mentions": {"parse": []},
    }
    assert rest
    assert all("embeds" in p for p in rest)


def test_rejected_post_prints_discords_reason_without_the_token(
    preview_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"attachments": ["0"]})

    http = httpx.Client(transport=httpx.MockTransport(handler))

    code = preview_script.main([DSS, "standings"], env=ENV, http=http)

    assert code == 1
    err = capsys.readouterr().err
    assert '{"attachments":["0"]}' in err.replace(" ", "")
    assert WEBHOOK_TOKEN not in err
