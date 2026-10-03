import re
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

LOCAL_CONFIG = """\
version = 0.1

[default.deploy.parameters]
stack_name = "my-bot"
region = "eu-central-1"

[other.deploy.parameters]
stack_name = "other-bot"

[other.global.parameters]
region = "eu-west-1"
"""


class FakeRunner:
    def __init__(self, code: int = 0, raises: BaseException | None = None) -> None:
        self.code = code
        self.raises = raises
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, cmd: Sequence[str], cwd: Path) -> int:
        self.calls.append((list(cmd), cwd))
        if self.raises is not None:
            raise self.raises
        return self.code


def _which(*available: str) -> object:
    return lambda name: f"/bin/{name}" if name in available else None


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "samconfig.local.toml").write_text(LOCAL_CONFIG, encoding="utf-8")
    return tmp_path


def _run(
    aws_ops: ModuleType,
    argv: list[str],
    root: Path,
    runner: FakeRunner | None = None,
    which: object = None,
) -> tuple[int, FakeRunner]:
    runner = runner or FakeRunner()
    code = aws_ops.main(argv, run=runner, which=which or _which("sam"), root=root)
    return code, runner


# --- build -----------------------------------------------------------------


def test_build_runs_sam_build_in_repo_root(aws_ops: ModuleType, root: Path) -> None:
    code, runner = _run(aws_ops, ["build"], root)

    assert code == 0
    assert runner.calls == [(["/bin/sam", "build"], root)]


def test_build_needs_no_local_config(aws_ops: ModuleType, tmp_path: Path) -> None:
    code, runner = _run(aws_ops, ["build"], tmp_path)

    assert code == 0
    assert runner.calls[0][0] == ["/bin/sam", "build"]


def test_unknown_arguments_are_passed_to_sam(aws_ops: ModuleType, root: Path) -> None:
    _, runner = _run(aws_ops, ["build", "--use-container"], root)

    assert runner.calls[0][0] == ["/bin/sam", "build", "--use-container"]


def test_sam_exit_code_is_returned(aws_ops: ModuleType, root: Path) -> None:
    code, _ = _run(aws_ops, ["build"], root, runner=FakeRunner(code=1))

    assert code == 1


# --- choosing sam ------------------------------------------------------------


def test_falls_back_to_pinned_sam_through_uvx(aws_ops: ModuleType, root: Path) -> None:
    _, runner = _run(aws_ops, ["build"], root, which=_which("uvx"))

    assert runner.calls[0][0] == [
        "/bin/uvx",
        "--from",
        f"aws-sam-cli=={aws_ops.SAM_CLI_VERSION}",
        "sam",
        "build",
    ]


def test_without_sam_or_uvx_exits_2(
    aws_ops: ModuleType, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, runner = _run(aws_ops, ["build"], root, which=_which())

    assert code == 2
    assert runner.calls == []
    assert "uvx" in capsys.readouterr().err


@pytest.mark.parametrize("workflow", ["ci.yml", "deploy.yml"])
def test_sam_version_matches_workflow(aws_ops: ModuleType, workflow: str) -> None:
    text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    pins = set(re.findall(r"aws-sam-cli==([0-9.]+)", text))

    assert pins == {aws_ops.SAM_CLI_VERSION}, (
        f"{workflow} pins {pins}, scripts/aws_ops.py pins {aws_ops.SAM_CLI_VERSION}"
    )


# --- deploy ------------------------------------------------------------------


def test_deploy_uses_local_config(aws_ops: ModuleType, root: Path) -> None:
    code, runner = _run(aws_ops, ["deploy"], root)

    assert code == 0
    assert runner.calls == [
        (
            [
                "/bin/sam",
                "deploy",
                "--config-file",
                "samconfig.local.toml",
                "--config-env",
                "default",
            ],
            root,
        )
    ]


def test_deploy_config_env(aws_ops: ModuleType, root: Path) -> None:
    _, runner = _run(aws_ops, ["deploy", "--config-env", "other"], root)

    assert runner.calls[0][0][-2:] == ["--config-env", "other"]


def test_deploy_without_local_config_exits_2(
    aws_ops: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, runner = _run(aws_ops, ["deploy"], tmp_path)

    assert code == 2
    assert runner.calls == []
    assert "sam deploy --guided" in capsys.readouterr().err


def test_deploy_unknown_config_env_exits_2(aws_ops: ModuleType, root: Path) -> None:
    code, runner = _run(aws_ops, ["deploy", "--config-env", "missing"], root)

    assert code == 2
    assert runner.calls == []


def test_invalid_toml_exits_2(aws_ops: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "samconfig.local.toml").write_text("[default\n", encoding="utf-8")

    code, runner = _run(aws_ops, ["deploy"], tmp_path)

    assert code == 2
    assert runner.calls == []


def test_parameters_that_are_not_a_table_exit_2(
    aws_ops: ModuleType, tmp_path: Path
) -> None:
    (tmp_path / "samconfig.local.toml").write_text(
        "[default.deploy]\nparameters = 'x'\n", encoding="utf-8"
    )

    code, _ = _run(aws_ops, ["deploy"], tmp_path)

    assert code == 2


# --- logs --------------------------------------------------------------------


def test_logs_tail_streams_all_functions(aws_ops: ModuleType, root: Path) -> None:
    code, runner = _run(aws_ops, ["logs", "tail"], root)

    assert code == 0
    assert runner.calls[0][0] == [
        "/bin/sam",
        "logs",
        "--stack-name",
        "my-bot",
        "--region",
        "eu-central-1",
        "--tail",
    ]


def test_logs_window_reads_back_from_start_time(
    aws_ops: ModuleType, root: Path
) -> None:
    _, runner = _run(aws_ops, ["logs", "10m"], root)

    assert runner.calls[0][0][-2:] == ["--start-time", "10 minutes ago"]


def test_logs_defaults_to_last_10_minutes(aws_ops: ModuleType, root: Path) -> None:
    _, runner = _run(aws_ops, ["logs"], root)

    assert runner.calls[0][0][-2:] == ["--start-time", "10 minutes ago"]


@pytest.mark.parametrize(
    ("function", "name"),
    [("worker", "WorkerFunction"), ("interactions", "InteractionsFunction")],
)
def test_logs_for_one_function(
    aws_ops: ModuleType, root: Path, function: str, name: str
) -> None:
    _, runner = _run(aws_ops, ["logs", "tail", "--function", function], root)

    cmd = runner.calls[0][0]
    assert cmd[cmd.index("--name") + 1] == name


def test_logs_function_names_exist_in_template(aws_ops: ModuleType) -> None:
    template = (REPO_ROOT / "template.yaml").read_text(encoding="utf-8")

    for name in aws_ops.FUNCTIONS.values():
        assert re.search(
            rf"^  {name}:\n    Type: AWS::Serverless::Function", template, re.M
        ), name


def test_logs_stack_name_option_wins(aws_ops: ModuleType, root: Path) -> None:
    _, runner = _run(aws_ops, ["logs", "tail", "--stack-name", "x-bot"], root)

    cmd = runner.calls[0][0]
    assert cmd[cmd.index("--stack-name") + 1] == "x-bot"


def test_logs_region_falls_back_to_global(aws_ops: ModuleType, root: Path) -> None:
    _, runner = _run(aws_ops, ["logs", "tail", "--config-env", "other"], root)

    cmd = runner.calls[0][0]
    assert cmd[cmd.index("--stack-name") + 1] == "other-bot"
    assert cmd[cmd.index("--region") + 1] == "eu-west-1"


def test_logs_without_any_region_lets_sam_choose(
    aws_ops: ModuleType, tmp_path: Path
) -> None:
    (tmp_path / "samconfig.local.toml").write_text(
        '[default.deploy.parameters]\nstack_name = "b"\n', encoding="utf-8"
    )

    _, runner = _run(aws_ops, ["logs", "tail"], tmp_path)

    assert "--region" not in runner.calls[0][0]


def test_logs_without_stack_name_exits_2(aws_ops: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "samconfig.local.toml").write_text(
        '[default.global.parameters]\nregion = "eu-central-1"\n', encoding="utf-8"
    )

    code, runner = _run(aws_ops, ["logs", "tail"], tmp_path)

    assert code == 2
    assert runner.calls == []


@pytest.mark.parametrize("value", ['""', '"   "', "5"])
def test_logs_blank_or_non_text_stack_name_exits_2(
    aws_ops: ModuleType, tmp_path: Path, value: str
) -> None:
    (tmp_path / "samconfig.local.toml").write_text(
        f"[default.deploy.parameters]\nstack_name = {value}\n", encoding="utf-8"
    )

    code, _ = _run(aws_ops, ["logs", "tail"], tmp_path)

    assert code == 2


def test_ctrl_c_ends_tail_cleanly(aws_ops: ModuleType, root: Path) -> None:
    runner = FakeRunner(raises=KeyboardInterrupt())

    code, _ = _run(aws_ops, ["logs", "tail"], root, runner=runner)

    assert code == 0


def test_ctrl_c_during_deploy_exits_130(aws_ops: ModuleType, root: Path) -> None:
    runner = FakeRunner(raises=KeyboardInterrupt())

    code, _ = _run(aws_ops, ["deploy"], root, runner=runner)

    assert code == 130


# --- log windows -------------------------------------------------------------


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ("1s", "1 second ago"),
        ("30s", "30 seconds ago"),
        ("1m", "1 minute ago"),
        ("10m", "10 minutes ago"),
        ("2h", "2 hours ago"),
        ("1d", "1 day ago"),
    ],
)
def test_start_time(aws_ops: ModuleType, window: str, expected: str) -> None:
    assert aws_ops.start_time(window) == expected


@pytest.mark.parametrize(
    "window",
    [
        "",  # empty
        "0m",  # zero
        "-5m",  # negative
        "05m",  # leading zero
        "10",  # no unit
        "m",  # no number
        "10min",  # unknown unit
        "10M",  # unit is lower case
        "1.5h",  # not an integer
        "10m\n",  # trailing newline
        chr(0x661) + chr(0x660) + "m",  # Arabic-Indic digits for 10
    ],
)
def test_invalid_window_is_rejected(aws_ops: ModuleType, window: str) -> None:
    with pytest.raises(aws_ops.UsageError):
        aws_ops.start_time(window)


def test_invalid_window_exits_2(aws_ops: ModuleType, root: Path) -> None:
    code, runner = _run(aws_ops, ["logs", "0m"], root)

    assert code == 2
    assert runner.calls == []
