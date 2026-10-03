"""`.env` for the local scripts (`register_commands.py`, `preview.py`); the
Lambda functions never read it.

Format: `KEY=VALUE` per line; blank lines and lines starting with `#` are
skipped; `export ` before the key is allowed; a value in matching single or
double quotes is unquoted. Nothing else is interpreted: `#` inside a value is
part of it, and there is no variable expansion.
"""

import re
import sys
from collections.abc import Mapping
from pathlib import Path

# ASCII only: `\w` would also accept other scripts' letters and digits.
_LINE = re.compile(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)")


def read_env_file(path: Path) -> dict[str, str]:
    """The file's values; empty if it does not exist or cannot be read.

    A malformed line is skipped with a warning naming only its line number,
    since it may hold a secret.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as err:
        print(f"{path.name}: not read ({type(err).__name__})", file=sys.stderr)
        return {}
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            print(
                f"{path.name}: line {number} is not KEY=VALUE; skipped", file=sys.stderr
            )
            continue
        key, value = match[1], match[2].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def environment(path: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """`environ` over the file's values: a variable set in the shell wins."""
    return {**read_env_file(path), **environ}
