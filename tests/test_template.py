"""template.yaml (SPEC §11): the settings that protect users and the bill, and
consistency with the code it deploys."""

import importlib
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from cobra_bot.handlers import interactions, worker

ROOT = Path(__file__).resolve().parents[1]

# Any: CloudFormation templates are heterogeneous JSON-like documents.
type Template = dict[str, Any]


@pytest.fixture(scope="module")
def template() -> Template:
    data = yaml.safe_load((ROOT / "template.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _resource(template: Template, name: str) -> dict[str, Any]:
    resource: dict[str, Any] = template["Resources"][name]
    return resource


def _props(template: Template, name: str) -> dict[str, Any]:
    props: dict[str, Any] = _resource(template, name)["Properties"]
    return props


# --- AC-23 ---------------------------------------------------------------------------


def test_ac23_worker_is_never_retried(template: Template) -> None:
    """NFR-06: a retried Worker would post duplicate messages."""
    config = _props(template, "WorkerFunction")["EventInvokeConfig"]

    assert config["MaximumRetryAttempts"] == 0


def test_ac23_cache_bucket_expires_objects(template: Template) -> None:
    rules = _props(template, "CacheBucket")["LifecycleConfiguration"]["Rules"]

    assert {"Status": "Enabled", "ExpirationInDays": 1}.items() <= rules[0].items()


# --- other SPEC §11 settings ----------------------------------------------------------


def test_worker_events_expire_with_the_interaction_token(template: Template) -> None:
    """Interaction tokens live 15 minutes; older queued events are useless."""
    config = _props(template, "WorkerFunction")["EventInvokeConfig"]

    assert config["MaximumEventAgeInSeconds"] == 600


def test_worker_timeout_and_memory(template: Template) -> None:
    props = _props(template, "WorkerFunction")
    memory = props.get("MemorySize", template["Globals"]["Function"]["MemorySize"])

    assert (props["Timeout"], memory) == (30, 256)


def test_cache_bucket_is_private(template: Template) -> None:
    block = _props(template, "CacheBucket")["PublicAccessBlockConfiguration"]

    assert block == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }


def test_interactions_function_url_is_public(template: Template) -> None:
    """Protected by the signature check (NFR-07), not by IAM."""
    url = _props(template, "InteractionsFunction")["FunctionUrlConfig"]

    assert url == {"AuthType": "NONE"}


@pytest.mark.parametrize("group", ["WorkerLogGroup", "InteractionsLogGroup"])
def test_logs_are_kept_14_days(template: Template, group: str) -> None:
    assert _props(template, group)["RetentionInDays"] == 14


@pytest.mark.parametrize(
    ("function", "group"),
    [
        ("WorkerFunction", "WorkerLogGroup"),
        ("InteractionsFunction", "InteractionsLogGroup"),
    ],
)
def test_functions_log_to_their_groups(
    template: Template, function: str, group: str
) -> None:
    assert _props(template, function)["LoggingConfig"] == {"LogGroup": {"Ref": group}}


def test_budget_is_5_usd_per_month(template: Template) -> None:
    budget = _props(template, "MonthlyBudget")["Budget"]

    assert (budget["BudgetLimit"], budget["TimeUnit"]) == (
        {"Amount": 5, "Unit": "USD"},
        "MONTHLY",
    )


def test_budget_alerts_go_to_the_email_parameter(template: Template) -> None:
    notifications = _props(template, "MonthlyBudget")["NotificationsWithSubscribers"]

    assert notifications
    for notification in notifications:
        assert notification["Subscribers"] == [
            {"SubscriptionType": "EMAIL", "Address": {"Ref": "BudgetEmail"}}
        ]


# --- least privilege (SPEC §10) -------------------------------------------------------


def test_interactions_may_only_invoke_the_worker(template: Template) -> None:
    policies = _props(template, "InteractionsFunction")["Policies"]

    assert policies == [
        {"LambdaInvokePolicy": {"FunctionName": {"Ref": "WorkerFunction"}}}
    ]


def test_worker_may_only_use_its_bucket(template: Template) -> None:
    (policy,) = _props(template, "WorkerFunction")["Policies"]
    statements = {s["Sid"]: s for s in policy["Statement"]}

    assert set(statements) == {"CacheObjects", "MissingKeyIs404"}
    assert statements["CacheObjects"]["Action"] == [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
    ]
    assert statements["CacheObjects"]["Resource"] == {"Fn::Sub": "${CacheBucket.Arn}/*"}
    assert statements["MissingKeyIs404"]["Action"] == "s3:ListBucket"
    assert all(s["Effect"] == "Allow" for s in statements.values())


def test_no_function_reads_ssm(template: Template) -> None:
    """NFR-08: nothing deployed needs a secret."""
    text = (ROOT / "template.yaml").read_text(encoding="utf-8").lower()

    assert "ssm" not in text


# --- consistency with the code --------------------------------------------------------


def test_runtime_matches_the_project_python(template: Template) -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()

    assert template["Globals"]["Function"]["Runtime"] == f"python{version}"
    assert pyproject["project"]["requires-python"] == f"=={version}.*"


@pytest.mark.parametrize("function", ["WorkerFunction", "InteractionsFunction"])
def test_handlers_exist(template: Template, function: str) -> None:
    module_name, _, attribute = _props(template, function)["Handler"].rpartition(".")

    assert callable(getattr(importlib.import_module(module_name), attribute))


@pytest.mark.parametrize(
    ("function", "names"),
    [
        (
            "InteractionsFunction",
            {interactions.PUBLIC_KEY_ENV, interactions.WORKER_ENV},
        ),
        ("WorkerFunction", {worker.CACHE_BUCKET_ENV}),
    ],
)
def test_environment_variables_match_the_code(
    template: Template, function: str, names: set[str]
) -> None:
    configured = set(_props(template, function)["Environment"]["Variables"])

    assert configured - names == set(), "set in template.yaml but unused by the code"
    assert names - configured == set(), "read by the code but missing in template.yaml"


def test_lambda_requirements_match_the_lock_file() -> None:
    """src/requirements.txt is what SAM installs; it must list exactly the runtime
    packages of uv.lock (regenerate with the command in README.md)."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    by_name = {p["name"]: p for p in lock["package"]}
    runtime: set[str] = set()
    pending = [d["name"] for d in by_name["cobra-bot"].get("dependencies", [])]
    while pending:
        name = pending.pop()
        if name not in runtime:
            runtime.add(name)
            pending += [d["name"] for d in by_name[name].get("dependencies", [])]
    pinned = {
        line.split("==")[0].strip(): line.split("==")[1].split(";")[0].strip()
        for line in (ROOT / "src" / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith(("#", " "))
    }

    assert set(pinned) - runtime == set(), (
        "in requirements.txt but not a runtime dependency"
    )
    assert runtime - set(pinned) == set(), (
        "runtime dependency missing from requirements.txt"
    )
    assert {n: by_name[n]["version"] for n in runtime} == pinned


def test_interactions_function_has_cpu_for_a_cold_start(template: Template) -> None:
    """NFR-04: at 256 MB a cold start missed Discord's 3 s acknowledgement limit."""
    assert _props(template, "InteractionsFunction")["MemorySize"] == 512
