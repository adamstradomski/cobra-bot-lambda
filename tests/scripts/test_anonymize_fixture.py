import copy
import json
from types import ModuleType
from typing import Any

import pytest

# Any: raw Cobra JSON is heterogeneous; tests index into it freely.
type Raw = dict[str, Any]


def _seat(pid: int | None, **scores: object) -> dict[str, object]:
    return {"id": pid, **scores}


def _raw() -> Raw:
    """A tiny export: 3 players, a Swiss round with a bye in the player1 slot,
    an elimination round, and every personal field present."""
    players = [
        {
            "id": pid,
            "name": name,
            "rank": rank,
            "corpFaction": "haas-bioroid",
            "corpIdentity": "Haas-Bioroid: Precision Design",
            "runnerFaction": None,
            "runnerIdentity": None,
            "matchPoints": points,
            "strengthOfSchedule": "1.5",
            "extendedStrengthOfSchedule": "2.25",
            "pronouns": "they/them",
        }
        for pid, name, rank, points in [
            (70300, "Zofia Original", 1, 6),
            (70100, "Jan Original", 2, 3),
            (70200, "Ana Original", 3, 0),
        ]
    ]
    swiss = [
        {
            "table": 1,
            "player1": _seat(
                70300, role="corp", corpScore=3, runnerScore=0, combinedScore=3
            ),
            "player2": _seat(
                70100, role="runner", corpScore=0, runnerScore=0, combinedScore=0
            ),
            "intentionalDraw": False,
            "twoForOne": False,
            "eliminationGame": False,
        },
        {
            "table": 2,
            "player1": _seat(
                None, role=None, corpScore=None, runnerScore=None, combinedScore=None
            ),
            "player2": _seat(
                70200, role=None, corpScore=None, runnerScore=None, combinedScore=3
            ),
            "intentionalDraw": False,
            "twoForOne": False,
            "eliminationGame": False,
        },
    ]
    elimination = [
        {
            "table": 1,
            "player1": _seat(70300, role="corp", winner=True),
            "player2": _seat(70100, role="runner", winner=False),
            "intentionalDraw": False,
            "twoForOne": False,
            "eliminationGame": True,
        }
    ]
    return {
        "name": "Secret Regional 2026",
        "date": "2026-09-07",
        "cutToTop": 2,
        "preliminaryRounds": 1,
        "tournamentOrganiser": {"nrdbId": 4242, "nrdbUsername": "real-organiser"},
        "players": players,
        "eliminationPlayers": [
            {"id": 70300, "name": "Zofia Original", "rank": 1, "seed": 1},
            {"id": 70100, "name": "Jan Original", "rank": 2, "seed": 2},
        ],
        "rounds": [swiss, elimination],
        "uploadedFrom": "Cobra",
        "links": [
            {
                "rel": "schemaderivedfrom",
                "href": "https://tournaments.nullsignal.games/schemas/tournament-schema.json",
            },
            {
                "rel": "uploadedfrom",
                "href": "https://tournaments.nullsignal.games/tournaments/QNSF",
            },
        ],
    }


def _ids(fixture: Raw) -> list[int | None]:
    seats = [
        p[key]["id"]
        for rnd in fixture["rounds"]
        for p in rnd
        for key in ("player1", "player2")
    ]
    return (
        [p["id"] for p in fixture["players"]]
        + seats
        + [e["id"] for e in fixture["eliminationPlayers"]]
    )


def test_player_ids_are_remapped_consistently(anonymizer: ModuleType) -> None:
    raw = _raw()
    fixture = anonymizer.anonymize(raw)

    # 1000 + position (1-based) in sorted original IDs.
    mapping = {70100: 1001, 70200: 1002, 70300: 1003, None: None}
    assert _ids(fixture) == [mapping[i] for i in _ids(raw)]


def test_undecided_cut_place_stays_null(anonymizer: ModuleType) -> None:
    """A live cut: Cobra exports places not decided yet with null player."""
    raw = _raw()
    raw["eliminationPlayers"][0] = {"id": None, "name": None, "rank": 1, "seed": None}

    fixture = anonymizer.anonymize(raw)

    assert fixture["eliminationPlayers"][0] == raw["eliminationPlayers"][0]


def test_cut_place_with_a_name_but_no_id_is_refused(anonymizer: ModuleType) -> None:
    raw = _raw()
    raw["eliminationPlayers"][0]["id"] = None

    with pytest.raises(anonymizer.AnonymizeError, match="a name without an id"):
        anonymizer.anonymize(raw)


def test_bye_in_player1_slot_stays_null(anonymizer: ModuleType) -> None:
    fixture = anonymizer.anonymize(_raw())

    assert fixture["rounds"][0][1]["player1"]["id"] is None


def test_ranks_scores_and_structure_are_unchanged(anonymizer: ModuleType) -> None:
    raw = _raw()
    fixture = anonymizer.anonymize(raw)

    def strip(data: Raw) -> Raw:
        data = copy.deepcopy(data)
        for key in ("name", "date", "tournamentOrganiser", "links"):
            data.pop(key)
        for p in data["players"] + data["eliminationPlayers"]:
            p.pop("id")
            p.pop("name")
            p.pop("pronouns", None)
        for rnd in data["rounds"]:
            for pairing in rnd:
                pairing["player1"].pop("id")
                pairing["player2"].pop("id")
        return data

    assert strip(fixture) == strip(raw)


@pytest.mark.req("NFR-11")
def test_no_original_personal_data_remains(anonymizer: ModuleType) -> None:
    raw = _raw()
    text = json.dumps(anonymizer.anonymize(raw), ensure_ascii=False)

    originals = [p["name"] for p in raw["players"]] + [
        "Original",
        "they/them",
        "real-organiser",
        "4242",
        "Secret Regional",
        "2026-09-07",
        "QNSF",
        "70100",
        "70200",
        "70300",
    ]
    assert [o for o in originals if o in text] == []


def test_names_are_pseudonyms_matching_new_ids(anonymizer: ModuleType) -> None:
    fixture = anonymizer.anonymize(_raw())

    assert {p["id"]: p["name"] for p in fixture["players"]} == {
        1003: "Player0003",
        1001: "Player0001",
        1002: "Player0002",
    }
    assert [e["name"] for e in fixture["eliminationPlayers"]] == [
        "Player0003",
        "Player0001",
    ]


def test_fake_values_replace_tournament_metadata(anonymizer: ModuleType) -> None:
    fixture = anonymizer.anonymize(_raw(), title="Fixture X", date_="2000-02-03")

    assert fixture["name"] == "Fixture X"
    assert fixture["date"] == "2000-02-03"
    assert fixture["tournamentOrganiser"] == anonymizer.FAKE_ORGANISER
    assert fixture["links"][1]["href"] == anonymizer.FAKE_UPLOADED_FROM
    assert fixture["links"][0] == _raw()["links"][0]
    assert {p["pronouns"] for p in fixture["players"]} == {""}


def test_edge_case_names_go_to_lowest_ranked_players(anonymizer: ModuleType) -> None:
    fixture = anonymizer.anonymize(_raw(), inject_edge_case_names=True)

    by_rank = {p["rank"]: p["name"] for p in fixture["players"]}
    assert by_rank == {3: "@Mention", 2: "*bold_name~", 1: "Maëlig"}
    assert [e["name"] for e in fixture["eliminationPlayers"]] == [
        "Maëlig",
        "*bold_name~",
    ]


def test_input_is_not_modified(anonymizer: ModuleType) -> None:
    raw = _raw()
    anonymizer.anonymize(raw, inject_edge_case_names=True)

    assert raw == _raw()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: r.update(description="free text"), id="top-level"),
        pytest.param(lambda r: r["players"][0].update(email="x@y"), id="player"),
        pytest.param(
            lambda r: r["rounds"][0][0]["player1"].update(note="x"), id="seat"
        ),
        pytest.param(
            lambda r: r["eliminationPlayers"][0].update(handle="x"), id="elimination"
        ),
        pytest.param(
            lambda r: r["tournamentOrganiser"].update(email="x"), id="organiser"
        ),
        pytest.param(
            lambda r: r["links"].append({"rel": "abr", "href": "https://example.com"}),
            id="link-rel",
        ),
    ],
)
def test_unknown_keys_are_rejected(anonymizer: ModuleType, mutate: Any) -> None:
    raw = _raw()
    mutate(raw)

    with pytest.raises(anonymizer.AnonymizeError):
        anonymizer.anonymize(raw)


def test_seat_with_unknown_player_id_is_rejected(anonymizer: ModuleType) -> None:
    raw = _raw()
    raw["rounds"][0][0]["player1"]["id"] = 99999

    with pytest.raises(anonymizer.AnonymizeError, match="unknown player ID"):
        anonymizer.anonymize(raw)
