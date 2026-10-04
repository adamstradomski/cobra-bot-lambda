"""scripts/generate_identities.py: short ID names from NetrunnerDB. No network:
HTTP goes to a mock transport, files to a temporary directory."""

import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from cobra_bot.formatting import identities

NRDB = "https://api.netrunnerdb.com/api/v3/public/cards"


def card(title: object, side: object = "corp", kind: object = None) -> object:
    card_type = kind if kind is not None else f"{side}_identity"
    return {"attributes": {"title": title, "side_id": side, "card_type_id": card_type}}


def page(*cards: object, next_url: str | None = None) -> dict[str, object]:
    links = {"next": next_url} if next_url else {}
    return {"data": list(cards), "links": links}


def _http(*responses: httpx.Response) -> tuple[httpx.Client, list[httpx.Request]]:
    queue = list(responses)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def _ok(body: object) -> httpx.Response:
    return httpx.Response(200, json=body)


# --- key ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Nuvem SA: Law of the Land", "Nuvem SA"),
        (
            "René “Loup” Arcemont: Party Animal",
            'René "Loup" Arcemont',
        ),  # Cobra: straight
        ("Ayla „Bios” Rahim: X", 'Ayla "Bios" Rahim'),
        ("Kit\u2019s Place: X", "Kit's Place"),
        ("No Colon Here", "No Colon Here"),
        ("A: B: C", "A"),  # the first colon only
        ("  Spaced  : X", "Spaced"),
        ("Me\u0301lie\u0300s U: X", "Méliès U"),  # NFC, as Cobra writes it
    ],
)
def test_key(identities_script: ModuleType, title: str, expected: str) -> None:
    assert identities_script.key(title) == expected


# --- derive ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('René "Loup" Arcemont', "Loup"),  # the nickname
        ("Zahya Sadeghi", "Zahya"),  # else the first word
        ("The Professor", "Professor"),  # after a leading "The "
        ("Quill, P.I.", "Quill"),  # comma dropped
        ("Lat", "Lat"),
        ("Silhouette", "Silhouet…"),  # 10 columns: cut
        ('Ann "Abcdefghij" Doe', "Abcdefgh…"),
    ],
)
def test_derive_runner(identities_script: ModuleType, name: str, expected: str) -> None:
    assert identities_script.derive("runner", name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Abcdefghi", "Abcdefghi"),  # exactly 9: whole
        ("AU Co.", "AU Co."),  # fits: whole, even with a space
        ("Abcdef Ghi", "Abcdef"),  # 10: first word
        ("The Foundry", "Foundry"),  # without "The " it fits
        ("The Zwicky Group", "Zwicky"),
        ("Thunderbolt Armaments", "Thunderb…"),  # first word still too long
        ("The Shadow", "Shadow"),
    ],
)
def test_derive_corp(identities_script: ModuleType, name: str, expected: str) -> None:
    assert identities_script.derive("corp", name) == expected


def test_derive_never_exceeds_nine_columns(identities_script: ModuleType) -> None:
    for side in ("corp", "runner"):
        for name in ("A" * 30, "B" * 9 + " C", '"' + "D" * 12 + '"'):
            assert len(identities_script.derive(side, name)) <= 9


# --- reading cards --------------------------------------------------------------


def test_identities_reads_both_sides(identities_script: ModuleType) -> None:
    found, skipped = identities_script.identities(
        [page(card("Nuvem SA: X"), card("Lat: Y", "runner"))]
    )

    assert [(i.side, i.title) for i in found] == [
        ("corp", "Nuvem SA: X"),
        ("runner", "Lat: Y"),
    ]
    assert skipped == 0


@pytest.mark.parametrize(
    "bad",
    [
        "not a card",
        {"no": "attributes"},
        {"attributes": "not a dict"},
        card(None),
        card(""),
        card("   "),
        card(42),
        card("X: Y", side="neutral"),
        card("X: Y", side=None),
        card("X: Y", kind="agenda"),
        card("X: Y", side="corp", kind="runner_identity"),  # sides disagree
    ],
)
def test_one_malformed_card_is_skipped_alone(
    identities_script: ModuleType, bad: object
) -> None:
    found, skipped = identities_script.identities(
        [page(card("Good: X"), bad, card("Also Good: Y", "runner"))]
    )

    assert [i.title for i in found] == ["Good: X", "Also Good: Y"]
    assert skipped == 1


@pytest.mark.parametrize("bad_page", [[], "x", {"data": "x"}, {"links": {}}])
def test_page_without_a_data_list_is_an_error(
    identities_script: ModuleType, bad_page: object
) -> None:
    with pytest.raises(identities_script.FetchError):
        identities_script.identities([bad_page])


# --- fetching -------------------------------------------------------------------


def test_fetch_follows_next_links(identities_script: ModuleType) -> None:
    second = f"{NRDB}?page[number]=2"
    http, seen = _http(
        _ok(page(card("A: 1"), next_url=second)), _ok(page(card("B: 2")))
    )

    pages = identities_script.fetch_pages(http)

    assert len(pages) == 2
    assert str(seen[1].url) == httpx.URL(second)


def test_fetch_asks_for_identities_only(identities_script: ModuleType) -> None:
    http, seen = _http(_ok(page()))

    identities_script.fetch_pages(http)

    params = seen[0].url.params
    assert params["filter[card_type_id]"] == "corp_identity,runner_identity"


def test_next_link_to_another_host_is_refused(identities_script: ModuleType) -> None:
    http, seen = _http(_ok(page(next_url="https://evil.test/cards?page=2")))

    with pytest.raises(identities_script.FetchError, match="another host"):
        identities_script.fetch_pages(http)
    assert len(seen) == 1


def test_endless_next_links_stop_at_the_page_limit(
    identities_script: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(identities_script, "MAX_PAGES", 3)
    http, seen = _http(*(_ok(page(next_url=f"{NRDB}?p={n}")) for n in range(5)))

    with pytest.raises(identities_script.FetchError, match="more than 3 pages"):
        identities_script.fetch_pages(http)
    assert len(seen) == 3


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(500), "HTTP 500"),
        (httpx.Response(429), "HTTP 429"),
        (httpx.Response(301, headers={"Location": "https://x.test"}), "HTTP 301"),
        (httpx.Response(302), "HTTP 302"),  # a redirect without a target
        (httpx.Response(200, text="<html>"), "not JSON"),
    ],
)
def test_bad_responses_are_fetch_errors(
    identities_script: ModuleType, response: httpx.Response, message: str
) -> None:
    http, _ = _http(response)

    with pytest.raises(identities_script.FetchError, match=message):
        identities_script.fetch_pages(http)


def test_network_errors_are_fetch_errors(identities_script: ModuleType) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    http = httpx.Client(transport=httpx.MockTransport(timeout))

    with pytest.raises(identities_script.FetchError, match="ReadTimeout"):
        identities_script.fetch_pages(http)


# --- building the map -----------------------------------------------------------


def _ids(module: ModuleType, *pairs: tuple[str, str]) -> list[object]:
    return [module.Identity(side, title) for side, title in pairs]


def test_override_wins_over_the_derived_name(identities_script: ModuleType) -> None:
    found = _ids(identities_script, ("corp", "Haas-Bioroid: Engineering the Future"))

    result = identities_script.build(
        found, overrides={"corp": {"Haas-Bioroid": "HB"}, "runner": {}}
    )

    assert result.corp == {"Haas-Bioroid": "HB"}
    assert result.warnings == ()


def test_ids_sharing_a_key_get_full_title_entries_and_keep_the_key(
    identities_script: ModuleType,
) -> None:
    found = _ids(
        identities_script,
        ("corp", "NBN: Controlling the Message"),
        ("corp", "NBN: Making News"),
    )

    result = identities_script.build(found, overrides={"corp": {}, "runner": {}})

    assert result.corp == {
        "NBN": "NBN",
        "NBN: Controlling the Message": "NBN CtM",
        "NBN: Making News": "NBN MN",
    }


def test_an_id_with_its_own_key_gets_no_full_title_entry(
    identities_script: ModuleType,
) -> None:
    found = _ids(identities_script, ("corp", "AU Co.: The Gold Standard in Clones"))

    result = identities_script.build(found, overrides={"corp": {}, "runner": {}})

    assert result.corp == {"AU Co.": "AU Co."}


def test_the_same_title_twice_is_not_shared(identities_script: ModuleType) -> None:
    """A reprint: NetrunnerDB lists one identity under two cards."""
    found = _ids(identities_script, ("corp", "Jinteki: A"), ("corp", "Jinteki: A"))

    result = identities_script.build(found, overrides={"corp": {}, "runner": {}})

    assert result.corp == {"Jinteki": "Jinteki"}


def test_full_title_override_wins(identities_script: ModuleType) -> None:
    found = _ids(
        identities_script, ("corp", "NBN: Reality Plus"), ("corp", "NBN: Making News")
    )

    result = identities_script.build(
        found, overrides={"corp": {"NBN: Reality Plus": "NBN R+"}, "runner": {}}
    )

    assert result.corp["NBN: Reality Plus"] == "NBN R+"


def test_shared_key_with_curly_quotes_uses_cobras_straight_quotes(
    identities_script: ModuleType,
) -> None:
    found = _ids(
        identities_script,
        ("runner", "X: “One”"),
        ("runner", "X: Two"),
    )

    result = identities_script.build(found, overrides={"corp": {}, "runner": {}})

    assert 'X: "One"' in result.runner


@pytest.mark.parametrize(
    ("prefix", "title", "short"),
    [
        ("NBN", "NBN: Controlling the Message", "NBN CtM"),
        ("NBN", "NBN: The World is Yours*", "NBN TWiY"),
        ("HB", "Haas-Bioroid: Architects of Tomorrow", "HB AoT"),
        ("Weyland", "Weyland Consortium: Because We Built It", "Weyland …"),
        ("NBN", "NBN: 2nd edition", "NBN 2E"),
        ("NBN", "NBN:", "NBN"),
    ],
    ids=["small-word", "first-word-capital", "of", "cut", "digit", "no-subtitle"],
)
def test_derive_shared(
    identities_script: ModuleType, prefix: str, title: str, short: str
) -> None:
    assert identities_script.derive_shared(prefix, title) == short


def test_entries_sorted_ignoring_case(identities_script: ModuleType) -> None:
    found = _ids(
        identities_script, ("runner", "b: X"), ("runner", "A: X"), ("runner", "C: X")
    )

    result = identities_script.build(found, overrides={"corp": {}, "runner": {}})

    assert list(result.runner) == ["A", "b", "C"]


def test_override_for_an_unknown_id_is_reported(identities_script: ModuleType) -> None:
    result = identities_script.build(
        _ids(identities_script, ("corp", "Real: X")),
        overrides={"corp": {"Gone Corp": "Gone"}, "runner": {}},
    )

    assert result.warnings == ("corp override for an unknown ID: Gone Corp",)


def test_cut_name_is_reported(identities_script: ModuleType) -> None:
    result = identities_script.build(
        _ids(identities_script, ("runner", "Silhouette: X")),
        overrides={"corp": {}, "runner": {}},
    )

    assert result.warnings == (
        "runner 'Silhouette' cut to 'Silhouet…'; add an override",
    )


def test_shared_short_name_is_reported(identities_script: ModuleType) -> None:
    result = identities_script.build(
        _ids(identities_script, ("corp", "Cyber Bureau: X"), ("corp", "Cyber Corp: Y")),
        overrides={"corp": {}, "runner": {}},
    )

    assert result.warnings == ("corp IDs share 'Cyber': Cyber Bureau, Cyber Corp",)


def test_same_short_name_on_both_sides_is_fine(identities_script: ModuleType) -> None:
    result = identities_script.build(
        _ids(identities_script, ("corp", "Nisei Division: X"), ("runner", "Nisei: Y")),
        overrides={"corp": {"Nisei Division": "Nisei"}, "runner": {}},
    )

    assert result.warnings == ()


# --- rendering ------------------------------------------------------------------


def _load(source: str) -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "identities.py", "exec"), namespace)
    return namespace


def test_rendered_module_round_trips(identities_script: ModuleType) -> None:
    result = identities_script.Result(
        corp={"Nuvem SA": "Nuvem", "Back\\slash": "B\\s"},
        runner={'René "Loup" Arcemont': "Loup", "Both \"'": "Q", "Żółw": "Żółw"},
        skipped=0,
        warnings=(),
    )

    namespace = _load(identities_script.render(result))

    assert namespace["CORP_SHORT_NAMES"] == result.corp
    assert namespace["RUNNER_SHORT_NAMES"] == result.runner


@pytest.mark.parametrize(
    ("text", "literal"),
    [
        ("Nuvem", '"Nuvem"'),
        ('René "Loup" Arcemont', "'René \"Loup\" Arcemont'"),  # as ruff formats it
        ("Kit's", '"Kit\'s"'),
        ("Both \"'", '"Both \\"\'"'),
    ],
)
def test_literal_quotes_like_ruff(
    identities_script: ModuleType, text: str, literal: str
) -> None:
    assert identities_script._literal(text) == literal


def test_rendered_module_ends_with_one_newline_and_uses_lf(
    identities_script: ModuleType,
) -> None:
    result = identities_script.Result({"A": "A"}, {"B": "B"}, 0, ())

    source = identities_script.render(result)

    assert source.endswith("}\n")
    assert not source.endswith("\n\n")
    assert "\r" not in source


# --- the committed map ----------------------------------------------------------


@pytest.mark.parametrize("side", ["corp", "runner"])
def test_committed_map_has_every_override(
    identities_script: ModuleType, side: str
) -> None:
    """The overrides live in the script, the map in identities.py: every
    override must be in the map with its value."""
    committed = (
        identities.CORP_SHORT_NAMES if side == "corp" else identities.RUNNER_SHORT_NAMES
    )

    missing = {
        name: short
        for name, short in identities_script.OVERRIDES[side].items()
        if committed.get(name) != short
    }
    assert missing == {}, f"identities.py lacks these {side} overrides; regenerate"


def test_overrides_fit_the_column(identities_script: ModuleType) -> None:
    for side in ("corp", "runner"):
        for short in identities_script.OVERRIDES[side].values():
            assert len(short) <= 9, short


def test_committed_map_says_it_is_generated() -> None:
    assert "Generated by `scripts/generate_identities.py`" in (identities.__doc__ or "")


# --- command line ---------------------------------------------------------------


def _input(tmp_path: Path, *cards: object) -> Path:
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(page(*cards)), encoding="utf-8")
    return path


def test_input_file_writes_the_module(
    identities_script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _input(tmp_path, card("Nuvem SA: X"), card("Lat: Y", "runner"))
    out = tmp_path / "out" / "identities.py"

    code = identities_script.main(["--input", str(source), "--output", str(out)])

    assert code == 0
    namespace = _load(out.read_text(encoding="utf-8"))
    assert namespace["CORP_SHORT_NAMES"] == {"Nuvem SA": "Nuvem"}
    assert namespace["RUNNER_SHORT_NAMES"] == {"Lat": "Lat"}
    assert "1 corp and 1 runner IDs" in capsys.readouterr().err


def test_fetches_when_no_input(identities_script: ModuleType, tmp_path: Path) -> None:
    http, seen = _http(_ok(page(card("Nuvem SA: X"))))
    out = tmp_path / "identities.py"

    assert identities_script.main(["--output", str(out)], http=http) == 0
    assert len(seen) == 1
    assert '"Nuvem SA": "Nuvem"' in out.read_text(encoding="utf-8")


def test_check_up_to_date_and_out_of_date(
    identities_script: ModuleType, tmp_path: Path
) -> None:
    source = _input(tmp_path, card("Nuvem SA: X"))
    out = tmp_path / "identities.py"
    identities_script.main(["--input", str(source), "--output", str(out)])
    written = out.read_bytes()

    assert (
        identities_script.main(
            ["--input", str(source), "--output", str(out), "--check"]
        )
        == 0
    )
    out.write_bytes(written.replace(b"\n", b"\r\n"))  # a CRLF checkout is up to date
    assert (
        identities_script.main(
            ["--input", str(source), "--output", str(out), "--check"]
        )
        == 0
    )
    out.write_text("old", encoding="utf-8")
    assert (
        identities_script.main(
            ["--input", str(source), "--output", str(out), "--check"]
        )
        == 1
    )
    assert out.read_text(encoding="utf-8") == "old"  # --check writes nothing


def test_check_without_the_file_is_out_of_date(
    identities_script: ModuleType, tmp_path: Path
) -> None:
    source = _input(tmp_path, card("Nuvem SA: X"))
    out = tmp_path / "missing.py"

    assert (
        identities_script.main(
            ["--input", str(source), "--output", str(out), "--check"]
        )
        == 1
    )
    assert not out.exists()


def test_stdout_prints_and_writes_nothing(
    identities_script: ModuleType,
    tmp_path: Path,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    source = _input(tmp_path, card("Poétrï Luxury Brands: X"))
    out = tmp_path / "identities.py"

    code = identities_script.main(
        ["--input", str(source), "--output", str(out), "--stdout"]
    )

    assert code == 0
    assert not out.exists()
    assert '"Poétrï Luxury Brands": "Poétrï"' in capsysbinary.readouterr().out.decode()


def test_check_and_stdout_are_exclusive(identities_script: ModuleType) -> None:
    with pytest.raises(SystemExit) as exit_info:
        identities_script.main(["--check", "--stdout"])

    assert exit_info.value.code == 2


def test_fetch_failure_exits_1_and_writes_nothing(
    identities_script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    http, _ = _http(httpx.Response(503))
    out = tmp_path / "identities.py"

    assert identities_script.main(["--output", str(out)], http=http) == 1
    assert not out.exists()
    assert "NetrunnerDB: HTTP 503" in capsys.readouterr().err


def test_missing_input_is_a_usage_error(
    identities_script: ModuleType, tmp_path: Path
) -> None:
    assert identities_script.main(["--input", str(tmp_path / "nope.json")]) == 2


def test_input_that_is_not_json_exits_1(
    identities_script: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")

    assert identities_script.main(["--input", str(bad), "--stdout"]) == 1


def test_no_identities_exits_1_and_keeps_the_old_file(
    identities_script: ModuleType, tmp_path: Path
) -> None:
    """An empty answer must not wipe the map."""
    source = _input(tmp_path, card("X: Y", kind="agenda"))
    out = tmp_path / "identities.py"
    out.write_text("old", encoding="utf-8")

    assert identities_script.main(["--input", str(source), "--output", str(out)]) == 1
    assert out.read_text(encoding="utf-8") == "old"


def test_malformed_cards_are_counted(
    identities_script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _input(tmp_path, card("Nuvem SA: X"), "junk", card(""))

    assert identities_script.main(["--input", str(source), "--stdout"]) == 0
    assert "2 malformed card(s) skipped" in capsys.readouterr().err
