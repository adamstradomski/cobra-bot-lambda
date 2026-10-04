#!/usr/bin/env python3
"""Generate `src/cobra_bot/formatting/identities.py`, the short ID names, from
every identity on NetrunnerDB (embed format A-1 to A-3, A-5).

    uv run scripts/generate_identities.py
    uv run scripts/generate_identities.py --check
    uv run scripts/generate_identities.py --input cards.json --stdout

Each identity's key is its title before the first `:`, written as Cobra writes
it: straight quotes where NetrunnerDB has curly ones (`René "Loup" Arcemont`).
Its short name comes from `OVERRIDES` if listed there, otherwise from `derive`.
Runs in the project environment. See docs/scripts.md for options and exit codes.
"""

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "src" / "cobra_bot" / "formatting" / "identities.py"
NRDB_URL = (
    "https://api.netrunnerdb.com/api/v3/public/cards"
    "?filter[card_type_id]=corp_identity,runner_identity&page[size]=1000"
)
USER_AGENT = (
    "cobra-bot-lambda/0.1 (+https://github.com/adamstradomski/cobra-bot-lambda)"
)
TIMEOUT_S = 15.0
MAX_PAGES = 20
MAX_WIDTH = 9  # columns for a short name (A-1)
ELLIPSIS = "…"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

type Side = Literal["corp", "runner"]

# Short names chosen by hand: the initial mapping (A-3), and IDs whose derived
# name is longer than 9 columns, ambiguous, or not what players call them.
OVERRIDES: dict[Side, dict[str, str]] = {
    "corp": {
        # A-3
        "Nuvem SA": "Nuvem",
        "Méliès U": "Méliès",
        "Haas-Bioroid": "HB",
        "Earth Station": "Earth St.",
        # Not the first word
        "PT Untaian": "Untaian",
        "New Angeles Sol": "NA Sol",
        "Near-Earth Hub": "NEH",
        "Jinteki Biotech": "Biotech",  # "Jinteki" is Jinteki's own IDs
        "Custom Biotics": "CustomBio",
        # Longer than 9 columns
        "AgInfusion": "AgInf.",
        "Cyber Bureau": "Cyb. Bur.",
        "Cybernetics Division": "Cyb. Div.",
        "Haarpsichord Studios": "Haarp.",
        "Harishchandra Ent.": "Harish.",
        "Industrial Genomics": "Ind. Gen.",
        "Information Dynamics": "Info Dyn.",
        "MirrorMorph": "MirrMorph",
        "Pravdivost Consulting": "Pravdiv.",
        "Sportsmetal": "Sportsmtl",
        "Thunderbolt Armaments": "Thunderb.",
    },
    "runner": {
        # Not the first word
        "Captain Padma Isbister": "Padma",
        "Virtual Intelligence, P.I.": "Vic",
        # What players call them, not the derived name
        'Kate "Mac" McCaffrey': "Kate",
        'Ken "Express" Tenma': "Ken Tenma",
        "Laramy Fisk": "Fisk",
        # Longer than 9 columns
        "Silhouette": "Silhouet.",
    },
}

# Curly quotes NetrunnerDB uses; Cobra writes straight ones.
_QUOTES = str.maketrans(
    {"\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2018": "'", "\u2019": "'"}
)
_NICKNAME = re.compile(r'"([^"]+)"')


class FetchError(Exception):
    """NetrunnerDB could not be read; exit code 1."""


@dataclass(frozen=True)
class Identity:
    side: Side
    title: str


@dataclass(frozen=True)
class Result:
    corp: dict[str, str]
    runner: dict[str, str]
    skipped: int  # malformed cards
    warnings: tuple[str, ...]


# --- reading NetrunnerDB ------------------------------------------------------


def fetch_pages(http: httpx.Client, url: str = NRDB_URL) -> list[object]:
    """Every page of the card list, following `links.next` on the same host."""
    host = urllib.parse.urlsplit(url).netloc
    pages: list[object] = []
    next_url: str | None = url
    while next_url is not None:
        if len(pages) == MAX_PAGES:
            raise FetchError(f"more than {MAX_PAGES} pages")
        if urllib.parse.urlsplit(next_url).netloc != host:
            raise FetchError("next page is on another host")
        try:
            response = http.get(next_url)
        except httpx.HTTPError as err:
            raise FetchError(f"request failed: {type(err).__name__}") from None
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code}")
        try:
            page = json.loads(response.content)
        except ValueError:
            raise FetchError("response is not JSON") from None
        pages.append(page)
        next_url = _next_link(page)
    return pages


def _next_link(page: object) -> str | None:
    links = page.get("links") if isinstance(page, dict) else None
    link = links.get("next") if isinstance(links, dict) else None
    return link if isinstance(link, str) and link else None


def identities(pages: Iterable[object]) -> tuple[list[Identity], int]:
    """Identity cards in the pages, and how many cards were skipped as malformed.
    A page without a `data` list is an error."""
    found: list[Identity] = []
    skipped = 0
    for page in pages:
        data = page.get("data") if isinstance(page, dict) else None
        if not isinstance(data, list):
            raise FetchError("page without a data list")
        for card in data:
            identity = _identity(card)
            if identity is None:
                skipped += 1
            else:
                found.append(identity)
    return found, skipped


def _identity(card: object) -> Identity | None:
    attributes = card.get("attributes") if isinstance(card, dict) else None
    if not isinstance(attributes, dict):
        return None
    title, side = attributes.get("title"), attributes.get("side_id")
    if not isinstance(title, str) or not title.strip():
        return None
    if side not in ("corp", "runner"):
        return None
    if attributes.get("card_type_id") != f"{side}_identity":
        return None
    return Identity(cast(Side, side), title)


# --- short names --------------------------------------------------------------


def key(title: str) -> str:
    """The title before the first `:`, as Cobra writes it (A-5)."""
    text = unicodedata.normalize("NFC", title).translate(_QUOTES)
    return text.split(":", 1)[0].strip()


def derive(side: Side, name: str) -> str:
    """The short name when there is no override (the A-2 rule, refined).

    Runner: the nickname in quotes, else the first word (after a leading
    "The "). Corp: the whole name if it fits, else without a leading "The ",
    else the first word. Cut to 9 columns with `…` if still longer.
    """
    bare = name.removeprefix("The ")
    if side == "runner":
        nickname = _NICKNAME.search(name)
        short = nickname.group(1).strip() if nickname else bare.split(" ")[0]
        short = short.rstrip(",")
    elif len(name) <= MAX_WIDTH:
        short = name
    else:
        short = bare if len(bare) <= MAX_WIDTH else bare.split(" ")[0]
    return short if len(short) <= MAX_WIDTH else short[: MAX_WIDTH - 1] + ELLIPSIS


def build(
    found: Iterable[Identity],
    skipped: int = 0,
    overrides: Mapping[Side, Mapping[str, str]] = OVERRIDES,
) -> Result:
    names: dict[Side, dict[str, str]] = {"corp": {}, "runner": {}}
    for identity in found:
        name = key(identity.title)
        override = overrides[identity.side].get(name)
        names[identity.side][name] = override or derive(identity.side, name)
    warnings: list[str] = []
    for side in ("corp", "runner"):
        for name in sorted(set(overrides[side]) - set(names[side])):
            warnings.append(f"{side} override for an unknown ID: {name}")
        for name, short in names[side].items():
            if short.endswith(ELLIPSIS):
                warnings.append(f"{side} {name!r} cut to {short!r}; add an override")
        by_short: dict[str, list[str]] = {}
        for name, short in names[side].items():
            by_short.setdefault(short, []).append(name)
        for short, keys in sorted(by_short.items()):
            if len(keys) > 1:
                warnings.append(
                    f"{side} IDs share {short!r}: {', '.join(sorted(keys))}"
                )
    return Result(
        corp=_sorted(names["corp"]),
        runner=_sorted(names["runner"]),
        skipped=skipped,
        warnings=tuple(warnings),
    )


def _sorted(names: Mapping[str, str]) -> dict[str, str]:
    return dict(sorted(names.items(), key=lambda item: item[0].casefold()))


# --- the generated module -----------------------------------------------------

HEADER = '''"""Short ID names for table columns (embed format A-1, A-3): data only.

Generated by `scripts/generate_identities.py` from every identity on NetrunnerDB;
do not edit by hand. To change a short name, edit `OVERRIDES` in the script and
run it again.

Keys are the text before the first `:` of an identity, as Cobra writes it
(straight quotes); values are at most 9 columns. IDs missing here (released
after the last run) fall back to a derived name (`text.corp_label`,
`text.runner_label`) and are logged.
"""
'''


def render(result: Result) -> str:
    parts = [HEADER]
    for constant, names in (
        ("CORP_SHORT_NAMES", result.corp),
        ("RUNNER_SHORT_NAMES", result.runner),
    ):
        lines = [f"    {_literal(k)}: {_literal(v)}," for k, v in names.items()]
        parts.append(
            f"\n{constant}: dict[str, str] = {{\n" + "\n".join(lines) + "\n}\n"
        )
    return "".join(parts)


def _literal(text: str) -> str:
    """A string literal as ruff formats it: double quotes, unless the text has
    double quotes and no single ones."""
    if '"' in text and "'" not in text:
        return f"'{text}'"
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# --- command line -------------------------------------------------------------


def main(
    argv: list[str] | None = None,
    http: httpx.Client | None = None,
    output: Path = OUTPUT,
) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the short ID names from NetrunnerDB."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="read a saved NetrunnerDB card list (JSON) instead of fetching",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the file is out of date; write nothing",
    )
    mode.add_argument(
        "--stdout", action="store_true", help="print the module instead of writing"
    )
    parser.add_argument(
        "--output", type=Path, help=f"file to write (default: {OUTPUT})"
    )
    args = parser.parse_args(argv)
    target = args.output or output

    try:
        if args.input is not None:
            pages: list[object] = [json.loads(args.input.read_bytes())]
        else:
            client = http or httpx.Client(
                timeout=TIMEOUT_S,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            try:
                pages = fetch_pages(client)
            finally:
                if http is None:
                    client.close()
        found, skipped = identities(pages)
    except OSError as err:
        print(f"generate_identities: {args.input}: {err.strerror}", file=sys.stderr)
        return EXIT_USAGE
    except ValueError:
        print(f"generate_identities: {args.input} is not JSON", file=sys.stderr)
        return EXIT_FAILED
    except FetchError as err:
        print(f"generate_identities: NetrunnerDB: {err}", file=sys.stderr)
        return EXIT_FAILED
    if not found:
        print("generate_identities: no identities found", file=sys.stderr)
        return EXIT_FAILED

    result = build(found, skipped)
    for warning in result.warnings:
        print(f"generate_identities: warning: {warning}", file=sys.stderr)
    module = render(result)
    summary = f"{len(result.corp)} corp and {len(result.runner)} runner IDs" + (
        f", {skipped} malformed card(s) skipped" if skipped else ""
    )
    if args.stdout:
        print(f"generate_identities: {summary}", file=sys.stderr)
        sys.stdout.flush()
        sys.stdout.buffer.write(module.encode())
        sys.stdout.buffer.flush()
        return EXIT_OK
    current = target.read_bytes().decode() if target.is_file() else None
    if args.check:
        if current is not None and current.replace("\r\n", "\n") == module:
            print(f"generate_identities: up to date ({summary})", file=sys.stderr)
            return EXIT_OK
        print(f"generate_identities: {target} is out of date", file=sys.stderr)
        return EXIT_FAILED
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(module.encode())
    print(f"generate_identities: wrote {target}: {summary}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
