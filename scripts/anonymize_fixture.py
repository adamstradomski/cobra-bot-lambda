#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Anonymise a raw Cobra tournament export into a test fixture (SPEC §12, task T04).

- Player names become deterministic pseudonyms (`Player0001`…), in `players` and
  `eliminationPlayers`.
- Player IDs are remapped everywhere: new ID = 1000 + position (1-based) in the
  sorted original IDs; `null` (bye) stays `null`. Pseudonym number = new ID - 1000.
- `pronouns` is emptied; the tournament organiser, name, date and the
  `uploadedfrom` shortcode are replaced by fixed fake values.
- Ranks, points, SoS/eSoS, scores, tables, flags, factions and identities are kept.

Only known keys are accepted: an unknown key aborts the run, so a field Cobra
adds later cannot slip into a committed fixture unreviewed.

Standard library only. See README.md for usage and exit codes.
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ID_OFFSET = 1000
DEFAULT_TITLE = "Fixture Tournament"
DEFAULT_DATE = "2000-01-01"
FAKE_ORGANISER = {"nrdbId": 1, "nrdbUsername": "fixture-organiser"}
FAKE_UPLOADED_FROM = "https://tournaments.nullsignal.games/tournaments/FXTR"
# Edge-case names (SPEC §12): assigned to the lowest-ranked players, in this order
# starting from the last rank, so acceptance criteria about top players are unaffected.
EDGE_CASE_NAMES = ("@Mention", "*bold_name~", "Maëlig", "Żółw")

TOP_KEYS = frozenset(
    {
        "name",
        "date",
        "cutToTop",
        "preliminaryRounds",
        "tournamentOrganiser",
        "players",
        "eliminationPlayers",
        "rounds",
        "uploadedFrom",
        "links",
    }
)
ORGANISER_KEYS = frozenset({"nrdbId", "nrdbUsername"})
PLAYER_KEYS = frozenset(
    {
        "id",
        "name",
        "rank",
        "corpFaction",
        "corpIdentity",
        "runnerFaction",
        "runnerIdentity",
        "matchPoints",
        "strengthOfSchedule",
        "extendedStrengthOfSchedule",
        "pronouns",
    }
)
ELIMINATION_PLAYER_KEYS = frozenset({"id", "name", "rank", "seed"})
PAIRING_KEYS = frozenset(
    {"table", "player1", "player2", "intentionalDraw", "twoForOne", "eliminationGame"}
)
SEAT_KEYS = frozenset(
    {"id", "role", "corpScore", "runnerScore", "combinedScore", "winner"}
)
LINK_KEYS = frozenset({"rel", "href"})
LINK_RELS = frozenset({"schemaderivedfrom", "uploadedfrom"})

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

# JSON objects from Cobra are heterogeneous; values are checked where they are used.
type JsonObject = dict[str, object]


class AnonymizeError(Exception):
    """The export has an unexpected shape or an unknown key."""


def _check_keys(obj: object, allowed: frozenset[str], where: str) -> JsonObject:
    if not isinstance(obj, dict):
        raise AnonymizeError(f"{where}: expected an object, got {type(obj).__name__}")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise AnonymizeError(f"{where}: unknown key(s) {unknown}; review and allowlist")
    return obj


def _list(obj: JsonObject, key: str, where: str) -> list[object]:
    value = obj.get(key, [])
    if not isinstance(value, list):
        raise AnonymizeError(f"{where}.{key}: expected a list")
    return value


def build_id_map(players: list[JsonObject]) -> dict[int, int]:
    ids: list[int] = []
    for player in players:
        pid = player.get("id")
        if not isinstance(pid, int):
            raise AnonymizeError(f"players[].id: expected an integer, got {pid!r}")
        ids.append(pid)
    if len(set(ids)) != len(ids):
        raise AnonymizeError("players[].id: duplicate IDs")
    return {old: ID_OFFSET + pos for pos, old in enumerate(sorted(ids), start=1)}


def pseudonym(new_id: int) -> str:
    return f"Player{new_id - ID_OFFSET:04d}"


def _remap(old: object, id_map: dict[int, int], where: str) -> int | None:
    if old is None:
        return None
    if not isinstance(old, int) or old not in id_map:
        raise AnonymizeError(f"{where}: unknown player ID {old!r}")
    return id_map[old]


def anonymize(
    raw: object,
    *,
    title: str = DEFAULT_TITLE,
    date_: str = DEFAULT_DATE,
    inject_edge_case_names: bool = False,
) -> JsonObject:
    """Return an anonymised copy of a Cobra export; the input is not modified."""
    top = _check_keys(raw, TOP_KEYS, "export")
    players = [
        _check_keys(p, PLAYER_KEYS, "players[]") for p in _list(top, "players", "")
    ]
    id_map = build_id_map(players)

    names = {new: pseudonym(new) for new in id_map.values()}
    if inject_edge_case_names:
        by_rank_desc = sorted(players, key=lambda p: _int(p, "rank"), reverse=True)
        for player, name in zip(by_rank_desc, EDGE_CASE_NAMES, strict=False):
            names[id_map[_int(player, "id")]] = name

    out: JsonObject = {}
    for key, value in top.items():
        match key:
            case "name":
                out[key] = title
            case "date":
                out[key] = date_
            case "tournamentOrganiser":
                _check_keys(value, ORGANISER_KEYS, "tournamentOrganiser")
                out[key] = dict(FAKE_ORGANISER)
            case "players":
                out[key] = [_player(p, id_map, names) for p in players]
            case "eliminationPlayers":
                out[key] = [
                    _elimination_player(e, id_map, names)
                    for e in _list(top, key, "export")
                ]
            case "rounds":
                out[key] = [
                    _round(r, id_map, f"rounds[{i}]")
                    for i, r in enumerate(_list(top, key, "export"))
                ]
            case "links":
                out[key] = [_link(link) for link in _list(top, key, "export")]
            case _:
                out[key] = value
    return out


def _int(obj: JsonObject, key: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int):
        raise AnonymizeError(f"{key}: expected an integer, got {value!r}")
    return value


def _player(
    player: JsonObject, id_map: dict[int, int], names: dict[int, str]
) -> JsonObject:
    new_id = id_map[_int(player, "id")]
    out = dict(player)
    out["id"] = new_id
    out["name"] = names[new_id]
    if "pronouns" in out:
        out["pronouns"] = ""
    return out


def _elimination_player(
    entry: object, id_map: dict[int, int], names: dict[int, str]
) -> JsonObject:
    obj = _check_keys(entry, ELIMINATION_PLAYER_KEYS, "eliminationPlayers[]")
    new_id = _remap(obj.get("id"), id_map, "eliminationPlayers[].id")
    if new_id is None:
        raise AnonymizeError("eliminationPlayers[].id: unexpected null")
    out = dict(obj)
    out["id"] = new_id
    out["name"] = names[new_id]
    return out


def _round(rnd: object, id_map: dict[int, int], where: str) -> list[JsonObject]:
    if not isinstance(rnd, list):
        raise AnonymizeError(f"{where}: expected a list of pairings")
    out: list[JsonObject] = []
    for pairing in rnd:
        obj = dict(_check_keys(pairing, PAIRING_KEYS, f"{where}[]"))
        for seat_key in ("player1", "player2"):
            seat = dict(
                _check_keys(obj.get(seat_key), SEAT_KEYS, f"{where}[].{seat_key}")
            )
            seat["id"] = _remap(seat.get("id"), id_map, f"{where}[].{seat_key}.id")
            obj[seat_key] = seat
        out.append(obj)
    return out


def _link(link: object) -> JsonObject:
    obj = dict(_check_keys(link, LINK_KEYS, "links[]"))
    rel = obj.get("rel")
    if rel not in LINK_RELS:
        raise AnonymizeError(f"links[]: unknown rel {rel!r}; review and allowlist")
    if rel == "uploadedfrom":
        obj["href"] = FAKE_UPLOADED_FROM
    return obj


# --- CLI ---------------------------------------------------------------------


def iso_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}") from None
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Anonymise a raw Cobra export into a test fixture (SPEC §12).",
    )
    parser.add_argument("input", type=Path, help="raw Cobra export (JSON)")
    parser.add_argument("output", type=Path, help="anonymised fixture to write")
    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help=f"tournament name in the fixture (default: {DEFAULT_TITLE!r})",
    )
    parser.add_argument(
        "--date",
        type=iso_date,
        default=DEFAULT_DATE,
        help=f"tournament date in the fixture (default: {DEFAULT_DATE})",
    )
    parser.add_argument(
        "--inject-edge-case-names",
        action="store_true",
        help=f"give the lowest-ranked players the names {list(EDGE_CASE_NAMES)}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        fixture = anonymize(
            raw,
            title=args.title,
            date_=args.date,
            inject_edge_case_names=args.inject_edge_case_names,
        )
    except (OSError, ValueError, AnonymizeError) as err:
        print(f"anonymize_fixture: {err}", file=sys.stderr)
        return EXIT_FAILED
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_name(args.output.name + ".tmp")
    tmp.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, args.output)
    players = fixture.get("players")
    count = len(players) if isinstance(players, list) else 0
    print(f"anonymize_fixture: {count} players -> {args.output}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
