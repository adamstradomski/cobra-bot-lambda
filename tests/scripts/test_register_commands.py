import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest

ENV = {"DISCORD_APPLICATION_ID": "app-1", "DISCORD_BOT_TOKEN": "bot-secret"}


def _http(
    status: int = 200, body: object = None
) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status, json=body if body is not None else [{"name": "cobra"}]
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_dry_run_prints_payload_without_credentials(
    register_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    http, seen = _http()

    code = register_script.main(["--dry-run"], env={}, http=http)

    assert code == 0
    assert seen == []
    printed = json.loads(capsys.readouterr().out)
    assert printed[0]["name"] == "cobra"
    assert printed[0]["integration_types"] == [0, 1]


def test_registers_global_commands(register_script: ModuleType) -> None:
    http, seen = _http()

    assert register_script.main([], env=ENV, http=http) == 0

    (request,) = seen
    assert (request.method, str(request.url)) == (
        "PUT",
        "https://discord.com/api/v10/applications/app-1/commands",
    )
    assert request.headers["Authorization"] == "Bot bot-secret"
    assert json.loads(request.content) == register_script.payload()


@pytest.mark.parametrize("missing", ["DISCORD_APPLICATION_ID", "DISCORD_BOT_TOKEN"])
def test_missing_credentials_is_a_usage_error(
    register_script: ModuleType, missing: str
) -> None:
    http, seen = _http()
    env = {k: v for k, v in ENV.items() if k != missing}

    assert register_script.main([], env=env, http=http) == 2
    assert seen == []


@pytest.mark.req("NFR-08")
def test_http_error_fails_without_printing_the_token(
    register_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    http, _ = _http(401, {"message": "401: Unauthorized", "code": 0})

    assert register_script.main([], env=ENV, http=http) == 1
    err = capsys.readouterr().err
    assert "HTTP 401" in err
    assert "bot-secret" not in err


def test_network_error_fails(register_script: ModuleType) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.Client(transport=httpx.MockTransport(refused))

    assert register_script.main([], env=ENV, http=http) == 1


def test_whitespace_around_credentials_is_stripped(register_script: ModuleType) -> None:
    http, seen = _http()
    env = {
        "DISCORD_APPLICATION_ID": " app-1\r\n",
        "DISCORD_BOT_TOKEN": " bot-secret \n",
    }

    assert register_script.main([], env=env, http=http) == 0
    assert str(seen[0].url).endswith("/applications/app-1/commands")
    assert seen[0].headers["Authorization"] == "Bot bot-secret"


def test_blank_credentials_are_a_usage_error(register_script: ModuleType) -> None:
    http, seen = _http()
    env = {"DISCORD_APPLICATION_ID": "app-1", "DISCORD_BOT_TOKEN": "   "}

    assert register_script.main([], env=env, http=http) == 2
    assert seen == []


def test_credentials_come_from_the_env_file(
    register_script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without `env`, the script reads `.env`; the shell's variables win."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_APPLICATION_ID=from-file\nDISCORD_BOT_TOKEN=file-token\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(register_script, "ENV_FILE", env_file)
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "shell-token")
    http, seen = _http()

    assert register_script.main([], http=http) == 0

    (request,) = seen
    assert "/applications/from-file/" in str(request.url)
    assert request.headers["Authorization"] == "Bot shell-token"
