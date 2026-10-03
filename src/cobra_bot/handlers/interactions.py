"""InteractionsFunction: Lambda Function URL entry point (SPEC §1, §3; NFR-04, NFR-07).

Verify the signature, answer PING, acknowledge commands with a deferred response
(public for every command) and hand the work to the Worker asynchronously.

Environment (set by the SAM template; nothing is hard-coded, so several bots or
accounts can run the same code):
- `DISCORD_PUBLIC_KEY`: the application's public key, hex (Developer Portal). It is
  not a secret: it only verifies signatures;
- `WORKER_FUNCTION_NAME`: the WorkerFunction to invoke.
"""

import base64
import json
import logging
from collections.abc import Mapping
from typing import Any, Protocol

from cobra_bot import messages
from cobra_bot.commands import Job, parse_command
from cobra_bot.discord.verify import SignatureVerifier
from cobra_bot.handlers.logging_setup import configure_logging

log = logging.getLogger(__name__)

PING = 1
APPLICATION_COMMAND = 2
PONG = 1
CHANNEL_MESSAGE = 4
DEFERRED_CHANNEL_MESSAGE = 5
EPHEMERAL = 1 << 6

PUBLIC_KEY_ENV = "DISCORD_PUBLIC_KEY"
WORKER_ENV = "WORKER_FUNCTION_NAME"

type Event = Mapping[str, Any]  # Any: Lambda events are untyped JSON
type Response = dict[str, object]


class LambdaClient(Protocol):
    """The subset of the boto3 Lambda client used here. Any: untyped responses."""

    def invoke(
        self, *, FunctionName: str, InvocationType: str, Payload: bytes
    ) -> Mapping[str, Any]: ...


class InteractionsApp:
    def __init__(
        self, verifier: SignatureVerifier, lambda_client: LambdaClient, worker: str
    ) -> None:
        self._verifier = verifier
        self._lambda = lambda_client
        self._worker = worker

    def handle(self, event: Event) -> Response:
        body = _body(event)
        headers = event.get("headers") or {}
        if not isinstance(headers, Mapping) or not self._verifier.verify(headers, body):
            return _response(401, {"error": "invalid request signature"})
        try:
            interaction = json.loads(body)
        except ValueError:
            return _response(400, {"error": "invalid JSON"})
        if not isinstance(interaction, Mapping):
            return _response(400, {"error": "invalid interaction"})
        if interaction.get("type") == PING:
            return _response(200, {"type": PONG})
        if interaction.get("type") != APPLICATION_COMMAND:
            return _response(400, {"error": "unsupported interaction type"})
        return self._command(interaction)

    def _command(self, interaction: Mapping[str, object]) -> Response:
        command = parse_command(interaction)
        application_id = interaction.get("application_id")
        token = interaction.get("token")
        if (
            command is None
            or not isinstance(application_id, str)
            or not isinstance(token, str)
        ):
            return _ephemeral_message(messages.UNKNOWN_COMMAND)
        job = Job(application_id, token, command)
        try:
            self._lambda.invoke(
                FunctionName=self._worker,
                InvocationType="Event",
                Payload=json.dumps(job.to_payload()).encode(),
            )
        except Exception:
            log.exception("worker invoke failed for %s", command.name)
            return _ephemeral_message(messages.INTERNAL_ERROR)
        log.info("deferred %s", command.name)
        return _response(200, {"type": DEFERRED_CHANNEL_MESSAGE})


def _body(event: Event) -> bytes:
    raw = event.get("body") or ""
    if not isinstance(raw, str):
        return b""
    if event.get("isBase64Encoded"):
        try:
            return base64.b64decode(raw)
        except ValueError:
            return b""
    return raw.encode()


def _response(status: int, body: object) -> Response:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _ephemeral_message(text: str) -> Response:
    return _response(
        200,
        {
            "type": CHANNEL_MESSAGE,
            "data": {
                "content": text,
                "flags": EPHEMERAL,
                "allowed_mentions": {"parse": []},
            },
        },
    )


# --- Lambda entry point -------------------------------------------------------------

_app: InteractionsApp | None = None


class ConfigurationError(RuntimeError):
    """A required environment variable is missing, empty or invalid."""


def app_from_environment(
    env: Mapping[str, str], lambda_client: LambdaClient
) -> InteractionsApp:
    """Build the app from environment variables; fails fast on bad configuration."""
    values = {name: env.get(name, "").strip() for name in (PUBLIC_KEY_ENV, WORKER_ENV)}
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise ConfigurationError(f"missing environment variables: {missing}")
    try:
        verifier = SignatureVerifier(values[PUBLIC_KEY_ENV])
    except ValueError:
        raise ConfigurationError(f"{PUBLIC_KEY_ENV} is not a valid key") from None
    return InteractionsApp(verifier, lambda_client, values[WORKER_ENV])


def handler(event: Event, context: object) -> Response:
    """Lambda entry point; configuration is read once per cold start."""
    global _app
    if _app is None:
        configure_logging()
        import os

        import boto3  # type: ignore[import-untyped]  # provided by the Lambda runtime

        _app = app_from_environment(os.environ, boto3.client("lambda"))
    return _app.handle(event)
