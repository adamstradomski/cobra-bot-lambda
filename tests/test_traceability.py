"""Every requirement (FR, NFR) and acceptance criterion (AC) has a test, and every
test marker names one that exists.

Tests name what they cover with `@pytest.mark.req("FR-09", "AC-27")`, or a
module-level `pytestmark = pytest.mark.req(...)`. The markers are read from the
source (AST), not by running pytest. Requirements whose status is exempt
(`Not implemented`, `Manual`, `TBD`) need no test; an AC is exempt when its
text starts with "Manual".
"""

import ast
import re
from collections.abc import Iterable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "docs" / "requirements.md"
ACCEPTANCE = ROOT / "docs" / "spec" / "acceptance-criteria.md"
TESTS = ROOT / "tests"

ID = re.compile(r"(?:FR|NFR|AC)-[0-9]{2}")
STATUSES = frozenset({"Implemented", "Partly", "Not implemented", "Manual", "TBD"})
EXEMPT = frozenset({"Not implemented", "Manual", "TBD"})


class TraceabilityError(ValueError):
    pass


def requirement_rows(markdown: str) -> dict[str, str]:
    """FR/NFR ID -> status, from table rows `| ID | Priority | Requirement |
    Status |`."""
    rows: dict[str, str] = {}
    for line in markdown.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"N?FR-[0-9]{2}", cells[0]):
            if cells[0] in rows:
                raise TraceabilityError(f"{cells[0]} is listed twice")
            rows[cells[0]] = cells[3]
    return rows


def acceptance_rows(markdown: str) -> dict[str, bool]:
    """AC ID -> whether it needs an automated test, from rows `| AC-xx | text |`."""
    rows: dict[str, bool] = {}
    for line in markdown.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and re.fullmatch(r"AC-[0-9]{2}", cells[0]):
            if cells[0] in rows:
                raise TraceabilityError(f"{cells[0]} is listed twice")
            rows[cells[0]] = not cells[1].startswith("Manual")
    return rows


def marked_ids(source: str, where: str) -> Iterable[tuple[str, str]]:
    """(ID, test) for every `req` marker in a test module's source."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                for rid in _req_args(decorator, f"{where}::{node.name}"):
                    yield rid, f"{where}::{node.name}"
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            marks = (
                node.value.elts if isinstance(node.value, ast.List) else [node.value]
            )
            for mark in marks:
                for rid in _req_args(mark, where):
                    yield rid, where


def _req_args(node: ast.expr, where: str) -> list[str]:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "req"
    ):
        return []
    ids = []
    for arg in node.args:
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            raise TraceabilityError(f"{where}: req() takes ID strings only")
        if not ID.fullmatch(arg.value):
            raise TraceabilityError(f"{where}: {arg.value!r} is not an FR/NFR/AC ID")
        ids.append(arg.value)
    if not ids:
        raise TraceabilityError(f"{where}: req() without an ID")
    return ids


def _markers() -> dict[str, list[str]]:
    """ID -> the tests marked with it, over the whole suite."""
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        where = path.relative_to(TESTS).as_posix()
        for rid, test in marked_ids(path.read_text(encoding="utf-8"), where):
            found.setdefault(rid, []).append(test)
    return found


@pytest.fixture(scope="module")
def requirements() -> dict[str, str]:
    return requirement_rows(REQUIREMENTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def criteria() -> dict[str, bool]:
    return acceptance_rows(ACCEPTANCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def markers() -> dict[str, list[str]]:
    return _markers()


# --- the documents against the suite ---------------------------------------------


def test_documents_list_requirements_and_criteria(
    requirements: dict[str, str], criteria: dict[str, bool]
) -> None:
    assert any(r.startswith("FR-") for r in requirements)
    assert any(r.startswith("NFR-") for r in requirements)
    assert criteria


def test_every_status_is_known(requirements: dict[str, str]) -> None:
    unknown = {r: s for r, s in requirements.items() if s not in STATUSES}
    assert not unknown, f"unknown status in docs/requirements.md: {unknown}"


def test_every_requirement_has_a_test(
    requirements: dict[str, str], markers: dict[str, list[str]]
) -> None:
    untested = [
        r for r, s in requirements.items() if s not in EXEMPT and r not in markers
    ]
    assert not untested, f"no test marked @pytest.mark.req for: {untested}"


def test_every_criterion_has_a_test(
    criteria: dict[str, bool], markers: dict[str, list[str]]
) -> None:
    untested = [
        ac for ac, automated in criteria.items() if automated and ac not in markers
    ]
    assert not untested, f"no test marked @pytest.mark.req for: {untested}"


def test_exempt_requirements_have_no_tests(
    requirements: dict[str, str], markers: dict[str, list[str]]
) -> None:
    """A test for a requirement marked Not implemented, Manual or TBD means its
    status is out of date."""
    stale = {
        r: markers[r] for r, s in requirements.items() if s in EXEMPT and r in markers
    }
    assert not stale, f"tested, but exempt in docs/requirements.md: {stale}"


def test_every_marker_names_a_documented_id(
    requirements: dict[str, str],
    criteria: dict[str, bool],
    markers: dict[str, list[str]],
) -> None:
    known = set(requirements) | set(criteria)
    unknown = {r: tests for r, tests in markers.items() if r not in known}
    assert not unknown, f"markers name IDs missing from the documents: {unknown}"


# --- the parsers ------------------------------------------------------------------


def test_requirement_rows_read_id_and_status() -> None:
    text = (
        "| ID | Priority | Requirement | Status |\n"
        "|----|----------|-------------|--------|\n"
        "| FR-01 | Must | Pairings. | Implemented |\n"
        "| NFR-05 | Should | Speed. | TBD |\n"
        "| AC-01 | Not a requirement row |\n"
    )
    assert requirement_rows(text) == {"FR-01": "Implemented", "NFR-05": "TBD"}


def test_requirement_rows_skip_malformed_ids() -> None:
    """A short ID and one in Arabic-Indic digits are not requirement rows."""
    arabic_indic_01 = "\u0660\u0661"
    text = (
        "| FR-1 | Must | x | Implemented |\n"
        f"| FR-{arabic_indic_01} | Must | x | Implemented |\n"
    )
    assert requirement_rows(text) == {}


def test_a_duplicated_requirement_is_an_error() -> None:
    row = "| FR-01 | Must | x | Implemented |\n"
    with pytest.raises(TraceabilityError, match="FR-01 is listed twice"):
        requirement_rows(row * 2)


def test_acceptance_rows_mark_manual_criteria() -> None:
    text = "| AC-01 | Given a fixture… |\n| AC-20 | Manual: on a test server… |\n"
    assert acceptance_rows(text) == {"AC-01": True, "AC-20": False}


def test_markers_on_functions_and_modules() -> None:
    source = (
        "import pytest\n"
        'pytestmark = [pytest.mark.req("NFR-07"), pytest.mark.slow]\n'
        '@pytest.mark.req("FR-01", "AC-02")\n'
        '@pytest.mark.parametrize("x", [1])\n'
        "def test_a(x): ...\n"
        "def test_b(): ...\n"
    )
    assert list(marked_ids(source, "t.py")) == [
        ("NFR-07", "t.py"),
        ("FR-01", "t.py::test_a"),
        ("AC-02", "t.py::test_a"),
    ]


@pytest.mark.parametrize(
    "marker",
    ['"FR-1"', '"FR-01\\n"', '"FR-\u0660\u0661"', '"fr-01"', '"XR-01"', "1", "ID", ""],
    ids=["short", "newline", "arabic-digits", "lower", "prefix", "int", "name", "none"],
)
def test_a_malformed_marker_is_an_error(marker: str) -> None:
    source = f"import pytest\n@pytest.mark.req({marker})\ndef test_a(): ...\n"
    with pytest.raises(TraceabilityError):
        list(marked_ids(source, "t.py"))
