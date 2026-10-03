"""`.env` reading for the local scripts."""

from pathlib import Path

import pytest

from cobra_bot.envfile import environment, read_env_file


def _file(tmp_path: Path, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / ".env"
    path.write_bytes(text.encode(encoding))
    return path


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("KEY=value", {"KEY": "value"}),
        ("KEY = value ", {"KEY": "value"}),  # spaces around `=` and value
        ("export KEY=value", {"KEY": "value"}),
        ('KEY="quoted value"', {"KEY": "quoted value"}),
        ("KEY='single'", {"KEY": "single"}),
        ("KEY=\"mismatched'", {"KEY": "\"mismatched'"}),  # kept as is
        ("KEY=", {"KEY": ""}),  # empty value
        ("KEY=a=b", {"KEY": "a=b"}),  # first `=` splits
        ("KEY=https://x.test/a#b", {"KEY": "https://x.test/a#b"}),  # `#` kept
        ("_K1=v", {"_K1": "v"}),
        ("# comment", {}),
        ("   ", {}),
    ],
)
def test_line_formats(tmp_path: Path, line: str, expected: dict[str, str]) -> None:
    assert read_env_file(_file(tmp_path, line + "\n")) == expected


@pytest.mark.parametrize(
    "bad", ["no equals sign", "1KEY=v", "KEY-NAME=v", "KĘY=v", "=value"]
)
def test_malformed_line_is_skipped_alone_without_its_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    path = _file(tmp_path, f"A=1\n{bad}\nB=2\n")

    assert read_env_file(path) == {"A": "1", "B": "2"}
    err = capsys.readouterr().err
    assert "line 2" in err
    assert bad not in err  # the line may hold a secret


def test_crlf_and_bom(tmp_path: Path) -> None:
    path = _file(tmp_path, "﻿A=1\r\nB=2\r\n")

    assert read_env_file(path) == {"A": "1", "B": "2"}


def test_later_line_wins(tmp_path: Path) -> None:
    assert read_env_file(_file(tmp_path, "A=1\nA=2\n")) == {"A": "2"}


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_env_file(tmp_path / "missing") == {}


def test_undecodable_file_is_reported_and_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / ".env"
    path.write_bytes(b"A=\xff\xfe\n")

    assert read_env_file(path) == {}
    assert "UnicodeDecodeError" in capsys.readouterr().err


def test_shell_variable_wins_over_the_file(tmp_path: Path) -> None:
    path = _file(tmp_path, "A=file\nB=file\n")

    assert environment(path, {"A": "shell"}) == {"A": "shell", "B": "file"}
