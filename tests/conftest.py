import importlib.util
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

from cobra_bot.formatting.text import corp_label, runner_label

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def raw_fixture() -> Callable[[str], object]:
    """Load an anonymised Cobra export from tests/fixtures/ by name."""

    def load(name: str) -> object:
        return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))

    return load


def _load_script(name: str) -> ModuleType:
    """Import a standalone script from scripts/ (not a package) without sys.modules."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def anonymizer() -> ModuleType:
    return _load_script("anonymize_fixture")


@pytest.fixture(scope="session")
def register_script() -> ModuleType:
    return _load_script("register_commands")


@pytest.fixture(scope="session")
def aws_ops() -> ModuleType:
    return _load_script("aws_ops")


@pytest.fixture(scope="session")
def preview_script() -> ModuleType:
    return _load_script("preview")


@pytest.fixture(scope="session")
def identities_script() -> ModuleType:
    return _load_script("generate_identities")


@pytest.fixture(autouse=True)
def _clear_id_label_caches() -> Iterator[None]:
    """ID labels are cached per process (and log a missing ID once); every test
    starts and ends with empty caches."""
    corp_label.cache_clear()
    runner_label.cache_clear()
    yield
    corp_label.cache_clear()
    runner_label.cache_clear()
