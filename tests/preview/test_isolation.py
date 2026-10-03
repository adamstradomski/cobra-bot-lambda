"""The layouts under test must not reach the bot: its handlers never import
`cobra_bot.preview`, and Pillow stays out of the Lambda package."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_handlers_do_not_import_the_preview_package() -> None:
    # A fresh interpreter: this test session has imported cobra_bot.preview.
    code = (
        "import sys, cobra_bot.handlers.interactions, cobra_bot.handlers.worker; "
        "print(sorted(m for m in sys.modules "
        "if m.startswith('cobra_bot.preview') or m.split('.')[0] == 'PIL'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "[]"


def test_pillow_is_not_a_lambda_dependency() -> None:
    requirements = (REPO_ROOT / "src" / "requirements.txt").read_text(encoding="utf-8")

    assert "pillow" not in requirements.lower()
