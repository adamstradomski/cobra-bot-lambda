import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

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
