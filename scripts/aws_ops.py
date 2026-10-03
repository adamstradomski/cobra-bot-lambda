#!/usr/bin/env python3
"""Run the everyday AWS SAM commands for this bot from your machine.

    uv run scripts/aws_ops.py build
    uv run scripts/aws_ops.py deploy
    uv run scripts/aws_ops.py logs tail
    uv run scripts/aws_ops.py logs 10m

Stack name and region come from `samconfig.local.toml`, written by the first
`sam deploy --guided`. Uses `sam` from PATH, or SAM CLI through `uvx` when it is
not installed. Standard library only. See README.md for options and exit codes.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

# Keep in step with .github/workflows/ci.yml and deploy.yml (tests check this).
SAM_CLI_VERSION = "1.166.2"
REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = "samconfig.local.toml"

FUNCTIONS = {
    "worker": "WorkerFunction",
    "interactions": "InteractionsFunction",
}

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

# ASCII digits only: `\d` would also accept other scripts' digits.
_DURATION = re.compile(r"([1-9][0-9]*)([smhd])")
_UNITS = {"s": "second", "m": "minute", "h": "hour", "d": "day"}

Runner = Callable[[Sequence[str], Path], int]
Which = Callable[[str], str | None]


class UsageError(Exception):
    """Bad arguments or missing local setup; exit code 2."""


def run_subprocess(cmd: Sequence[str], cwd: Path) -> int:
    return subprocess.run(list(cmd), cwd=cwd, check=False).returncode


def sam_command(which: Which) -> list[str]:
    sam = which("sam")
    if sam:
        return [sam]
    uvx = which("uvx")
    if uvx:
        return [uvx, "--from", f"aws-sam-cli=={SAM_CLI_VERSION}", "sam"]
    raise UsageError("Neither `sam` nor `uvx` is on PATH; install uv or SAM CLI.")


def start_time(window: str) -> str:
    """Turn `10m` into SAM's `--start-time` text, `10 minutes ago`."""
    match = _DURATION.fullmatch(window)
    if match is None:
        raise UsageError(
            f"Invalid log window {window!r}: use `tail` or a duration such as "
            "30s, 10m, 2h or 1d."
        )
    count, unit = int(match[1]), _UNITS[match[2]]
    return f"{count} {unit}{'' if count == 1 else 's'} ago"


def deploy_settings(root: Path, config_env: str) -> dict[str, object]:
    """The `[<env>.deploy.parameters]` table of samconfig.local.toml, with the
    region from `[<env>.global.parameters]` as a fallback."""
    path = root / LOCAL_CONFIG
    if not path.is_file():
        raise UsageError(
            f"{LOCAL_CONFIG} not found. Run `sam deploy --guided` once and save "
            f"the settings to {LOCAL_CONFIG} (see README.md, Deployment)."
        )
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise UsageError(f"{LOCAL_CONFIG} is not valid TOML: {exc}") from exc
    env = config.get(config_env)
    if not isinstance(env, dict):
        raise UsageError(f"{LOCAL_CONFIG} has no [{config_env}.*] settings.")
    deploy = _parameters(env, config_env, "deploy")
    settings = dict(deploy)
    if "region" not in settings:
        global_ = _parameters(env, config_env, "global")
        if "region" in global_:
            settings["region"] = global_["region"]
    return settings


def _parameters(
    env: dict[str, object], config_env: str, command: str
) -> dict[str, object]:
    section = env.get(command, {})
    params = section.get("parameters", {}) if isinstance(section, dict) else None
    if not isinstance(params, dict):
        raise UsageError(
            f"{LOCAL_CONFIG}: [{config_env}.{command}.parameters] must be a table."
        )
    return params


def _text_setting(settings: dict[str, object], key: str) -> str | None:
    value = settings.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise UsageError(f"{LOCAL_CONFIG}: {key} must be a non-empty string.")
    return value.strip()


def build_cmd(sam: list[str], extra: Sequence[str]) -> list[str]:
    return [*sam, "build", *extra]


def deploy_cmd(
    sam: list[str], root: Path, config_env: str, extra: Sequence[str]
) -> list[str]:
    deploy_settings(root, config_env)  # fail early with a clear message
    return [
        *sam,
        "deploy",
        "--config-file",
        LOCAL_CONFIG,
        "--config-env",
        config_env,
        *extra,
    ]


def logs_cmd(
    sam: list[str],
    root: Path,
    config_env: str,
    window: str,
    function: str,
    stack_name: str | None,
    extra: Sequence[str],
) -> list[str]:
    timing = ["--tail"] if window == "tail" else ["--start-time", start_time(window)]
    settings = deploy_settings(root, config_env)
    stack = stack_name or _text_setting(settings, "stack_name")
    if not stack:
        raise UsageError(
            f"No stack_name in [{config_env}.deploy.parameters] of {LOCAL_CONFIG}; "
            "pass --stack-name."
        )
    cmd = [*sam, "logs", "--stack-name", stack]
    region = _text_setting(settings, "region")
    if region:
        cmd += ["--region", region]
    if function != "all":
        cmd += ["--name", FUNCTIONS[function]]
    return [*cmd, *timing, *extra]


def parse_args(argv: Sequence[str] | None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run AWS SAM build, deploy and logs for this bot.",
        epilog="Arguments the script does not know are passed on to sam unchanged.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="sam build")

    deploy = sub.add_parser("deploy", help=f"sam deploy with {LOCAL_CONFIG}")
    deploy.add_argument("--config-env", default="default", help="default: default")

    logs = sub.add_parser("logs", help="show or stream the functions' logs")
    logs.add_argument(
        "window",
        nargs="?",
        default="10m",
        help="`tail` to stream, or how far back to read: 30s, 10m, 2h, 1d "
        "(default: 10m)",
    )
    logs.add_argument(
        "--function",
        choices=[*FUNCTIONS, "all"],
        default="all",
        help="which function's logs (default: all)",
    )
    logs.add_argument("--config-env", default="default", help="default: default")
    logs.add_argument("--stack-name", help=f"default: stack_name in {LOCAL_CONFIG}")

    args, extra = parser.parse_known_args(argv)
    return args, extra


def main(
    argv: Sequence[str] | None = None,
    run: Runner = run_subprocess,
    which: Which = shutil.which,
    root: Path = REPO_ROOT,
) -> int:
    args, extra = parse_args(argv)
    try:
        sam = sam_command(which)
        if args.command == "build":
            cmd = build_cmd(sam, extra)
        elif args.command == "deploy":
            cmd = deploy_cmd(sam, root, args.config_env, extra)
        else:
            cmd = logs_cmd(
                sam,
                root,
                args.config_env,
                args.window,
                args.function,
                args.stack_name,
                extra,
            )
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    print("$ " + " ".join(cmd), file=sys.stderr)
    try:
        return run(cmd, root)
    except KeyboardInterrupt:
        # Ctrl+C is the normal way to stop `logs tail`.
        if args.command == "logs" and args.window == "tail":
            return EXIT_OK
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
