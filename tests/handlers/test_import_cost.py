"""Cold-start cost: InteractionsFunction must answer Discord within 3 s, so it
must not load Pillow, which only the Worker needs to draw reply images."""

import subprocess
import sys


def _loaded_after(statement: str) -> list[str]:
    # A fresh interpreter: this test session has already imported Pillow.
    code = (
        f"import sys; {statement}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'PIL'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    return [m.strip("' ") for m in result.stdout.strip()[1:-1].split(",") if m]


def test_interactions_handler_does_not_load_pillow() -> None:
    assert _loaded_after("import cobra_bot.handlers.interactions") == []


def test_worker_loads_pillow() -> None:
    """The check above can fail: the Worker does load it."""
    assert "PIL" in _loaded_after("import cobra_bot.handlers.worker")
