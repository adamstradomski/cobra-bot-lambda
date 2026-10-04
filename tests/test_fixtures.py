"""Guards for committed fixtures: every file in tests/fixtures/ must look anonymised
(SPEC §12, NFR-11). The originals are not in the repository, so this checks the
shape anonymize_fixture.py produces rather than comparing against raw data."""

import json
import re
from pathlib import Path
from types import ModuleType

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))
PSEUDONYM = re.compile(r"Player\d{4}")


def test_fixtures_exist() -> None:
    assert {f.stem for f in FIXTURES} >= {
        "single_sided_top8",
        "large_top_cut",
        "dss",
        "not_started",
    }


@pytest.mark.req("NFR-11")
@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_is_anonymised(path: Path, anonymizer: ModuleType) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    allowed_names = set(anonymizer.EDGE_CASE_NAMES)
    entries = data["players"] + data["eliminationPlayers"]

    bad_names = [
        e["name"]
        for e in entries
        if not PSEUDONYM.fullmatch(e["name"]) and e["name"] not in allowed_names
    ]
    assert bad_names == []
    assert all(1000 < e["id"] < 10000 for e in entries)
    assert {p["pronouns"] for p in data["players"]} <= {""}
    assert data["tournamentOrganiser"] == anonymizer.FAKE_ORGANISER
    uploaded = [lnk["href"] for lnk in data["links"] if lnk["rel"] == "uploadedfrom"]
    assert uploaded == [anonymizer.FAKE_UPLOADED_FROM]
