import base64
import json
from collections.abc import Mapping
from typing import Any

import pytest
from nacl.signing import SigningKey

from cobra_bot.commands import Command, Job
from cobra_bot.discord.verify import SignatureVerifier
from cobra_bot.handlers.interactions import (
    ConfigurationError,
    InteractionsApp,
    app_from_environment,
)

KEY = SigningKey.generate()
WORKER = "cobra-bot-worker"
TIMESTAMP = "1790856000"


class FakeLambda:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []  # Any: recorded boto3 kwargs
        self.error = error

    def invoke(
        self, *, FunctionName: str, InvocationType: str, Payload: bytes
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "FunctionName": FunctionName,
                "InvocationType": InvocationType,
                "Payload": Payload,
            }
        )
        if self.error:
            raise self.error
        return {"StatusCode": 202}


def _app(lambda_client: FakeLambda | None = None) -> tuple[InteractionsApp, FakeLambda]:
    fake = lambda_client or FakeLambda()
    verifier = SignatureVerifier(KEY.verify_key.encode().hex())
    return InteractionsApp(verifier, fake, WORKER), fake


def _event(
    body: object, *, sign: bool = True, base64_body: bool = False
) -> dict[str, Any]:
    raw = json.dumps(body).encode()
    headers = {"x-signature-timestamp": TIMESTAMP}
    if sign:
        headers["x-signature-ed25519"] = KEY.sign(
            TIMESTAMP.encode() + raw
        ).signature.hex()
    return {
        "headers": headers,
        "body": base64.b64encode(raw).decode() if base64_body else raw.decode(),
        "isBase64Encoded": base64_body,
    }


def _command(sub: str, **options: object) -> dict[str, object]:
    return {
        "type": 2,
        "application_id": "app-1",
        "token": "tok-1",
        "data": {
            "name": "cobra",
            "type": 1,
            "options": [
                {
                    "name": sub,
                    "type": 1,
                    "options": [{"name": k, "value": v} for k, v in options.items()],
                }
            ],
        },
    }


def _json(response: dict[str, object]) -> object:
    return json.loads(str(response["body"]))


# --- AC-19 ---------------------------------------------------------------------------


def test_ac19_invalid_signature_is_401() -> None:
    app, fake = _app()
    event = _event({"type": 1})
    event["body"] = event["body"].replace("1", "2")  # tampered after signing

    response = app.handle(event)

    assert response["statusCode"] == 401
    assert fake.calls == []


def test_ac19_missing_signature_is_401() -> None:
    app, _ = _app()

    assert app.handle(_event({"type": 1}, sign=False))["statusCode"] == 401


def test_ac19_ping_is_pong() -> None:
    app, _ = _app()

    response = app.handle(_event({"type": 1}))

    assert response["statusCode"] == 200
    assert _json(response) == {"type": 1}


def test_ac19_player_is_deferred_publicly_and_worker_invoked_async() -> None:
    app, fake = _app()

    response = app.handle(_event(_command("player", tournament="4909", query="ali")))

    assert response["statusCode"] == 200
    assert _json(response) == {"type": 5}  # public, like every reply
    (call,) = fake.calls
    assert (call["FunctionName"], call["InvocationType"]) == (WORKER, "Event")
    job = Job.from_payload(json.loads(call["Payload"]))
    assert job == Job("app-1", "tok-1", Command("player", "4909", query="ali"))


# --- other commands and cases -----


@pytest.mark.parametrize(
    ("sub", "options", "command"),
    [
        (
            "pairings",
            {"tournament": "4909", "round": 3},
            Command("pairings", "4909", round=3),
        ),
        ("pairings", {"tournament": "QNSF"}, Command("pairings", "QNSF")),
        ("standings", {"tournament": "4909"}, Command("standings", "4909")),
    ],
)
def test_public_commands_are_deferred_without_flags(
    sub: str, options: dict[str, object], command: Command
) -> None:
    app, fake = _app()

    response = app.handle(_event(_command(sub, **options)))

    assert _json(response) == {"type": 5}
    assert Job.from_payload(json.loads(fake.calls[0]["Payload"])).command == command


def test_base64_body_is_decoded() -> None:
    app, _ = _app()

    assert _json(app.handle(_event({"type": 1}, base64_body=True))) == {"type": 1}


def test_worker_payload_carries_no_user_data() -> None:
    app, fake = _app()
    interaction = _command("standings", tournament="4909")
    interaction["member"] = {"user": {"id": "42", "username": "someone"}}

    app.handle(_event(interaction))

    payload = json.loads(fake.calls[0]["Payload"])
    assert set(payload) == {"application_id", "token", "command"}
    assert "someone" not in fake.calls[0]["Payload"].decode()


@pytest.mark.parametrize(
    "interaction",
    [
        {**_command("standings", tournament="1"), "data": {"name": "other"}},
        _command("unknown", tournament="1"),
        _command("player", tournament="1"),  # query missing
        _command("pairings", tournament="1", round="three"),
    ],
    ids=["other-command", "unknown-subcommand", "player-without-query", "bad-round"],
)
def test_unknown_or_malformed_command_gets_ephemeral_message(
    interaction: dict[str, object],
) -> None:
    app, fake = _app()

    body = _json(app.handle(_event(interaction)))

    assert body == {
        "type": 4,
        "data": {
            "content": "Unknown command.",
            "flags": 64,
            "allowed_mentions": {"parse": []},
        },
    }
    assert fake.calls == []


def test_failed_worker_invoke_gets_ephemeral_error() -> None:
    app, _ = _app(FakeLambda(error=RuntimeError("throttled")))

    body = _json(app.handle(_event(_command("standings", tournament="4909"))))

    assert body["data"]["content"] == "Something went wrong. Please try again later."  # type: ignore[index]


@pytest.mark.parametrize("body", ["not json", "[1, 2]"])
def test_bad_json_is_400(body: str) -> None:
    app, _ = _app()
    raw = body.encode()
    signature = KEY.sign(TIMESTAMP.encode() + raw).signature.hex()
    event = {
        "headers": {
            "x-signature-timestamp": TIMESTAMP,
            "x-signature-ed25519": signature,
        },
        "body": body,
    }

    assert app.handle(event)["statusCode"] == 400


def test_unsupported_interaction_type_is_400() -> None:
    app, _ = _app()

    assert app.handle(_event({"type": 3}))["statusCode"] == 400


# --- Job payload -----


def test_job_round_trip() -> None:
    job = Job("app", "tok", Command("pairings", "4909", round=2))

    assert Job.from_payload(json.loads(json.dumps(job.to_payload()))) == job


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "application_id": "a",
            "token": "t",
            "command": {"name": "x", "tournament": "1"},
        },
        {
            "application_id": "a",
            "token": "",
            "command": {"name": "standings", "tournament": "1"},
        },
    ],
)
def test_malformed_job_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Job.from_payload(payload)


# --- configuration from the environment -------------------------------------------

PUBLIC_KEY = KEY.verify_key.encode().hex()


def test_app_from_environment() -> None:
    env = {"DISCORD_PUBLIC_KEY": PUBLIC_KEY, "WORKER_FUNCTION_NAME": WORKER}
    fake = FakeLambda()

    app = app_from_environment(env, fake)
    app.handle(_event(_command("standings", tournament="4909")))

    assert fake.calls[0]["FunctionName"] == WORKER


@pytest.mark.parametrize(
    ("env", "missing"),
    [
        ({}, "DISCORD_PUBLIC_KEY', 'WORKER_FUNCTION_NAME"),
        ({"DISCORD_PUBLIC_KEY": PUBLIC_KEY}, "WORKER_FUNCTION_NAME"),
        ({"WORKER_FUNCTION_NAME": WORKER}, "DISCORD_PUBLIC_KEY"),
        (
            {"DISCORD_PUBLIC_KEY": "  ", "WORKER_FUNCTION_NAME": WORKER},
            "DISCORD_PUBLIC_KEY",
        ),
    ],
    ids=["both-missing", "worker-missing", "key-missing", "key-blank"],
)
def test_missing_or_blank_variables_fail_fast(
    env: dict[str, str], missing: str
) -> None:
    with pytest.raises(ConfigurationError, match=missing):
        app_from_environment(env, FakeLambda())


def test_invalid_public_key_fails_fast() -> None:
    env = {"DISCORD_PUBLIC_KEY": "not-hex", "WORKER_FUNCTION_NAME": WORKER}

    with pytest.raises(ConfigurationError, match="not a valid key"):
        app_from_environment(env, FakeLambda())
