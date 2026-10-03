"""Automatic deployment from main: bootstrap/github-deploy.yaml (the roles GitHub
Actions deploys with) and .github/workflows/deploy.yml must stay locked down and agree
with each other, with ci.yml and with template.yaml."""

import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

# Any: CloudFormation templates and workflows are heterogeneous JSON-like documents.
type Document = dict[str, Any]


def _load(relative: str) -> Document:
    data = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def bootstrap() -> Document:
    return _load("bootstrap/github-deploy.yaml")


@pytest.fixture(scope="module")
def workflow() -> Document:
    return _load(".github/workflows/deploy.yml")


def _default(bootstrap: Document, parameter: str) -> str:
    value: str = bootstrap["Parameters"][parameter]["Default"]
    return value


def _role(bootstrap: Document, name: str) -> Document:
    props: Document = bootstrap["Resources"][name]["Properties"]
    return props


def _statements(bootstrap: Document, role: str) -> list[Document]:
    statements: list[Document] = []
    for policy in _role(bootstrap, role)["Policies"]:
        statements.extend(policy["PolicyDocument"]["Statement"])
    return statements


def _triggers(workflow: Document) -> Document:
    # PyYAML follows YAML 1.1, where the bare key `on` is the boolean True.
    triggers: Document = workflow[True]
    return triggers


def _resources(statement: Document) -> list[str]:
    resource = statement["Resource"]
    items = resource if isinstance(resource, list) else [resource]
    return [item if isinstance(item, str) else str(item) for item in items]


# --- who can deploy ----------------------------------------------------------------


def test_deploy_role_trusts_only_the_production_environment(
    bootstrap: Document,
) -> None:
    """Branch pushes, PRs and other environments must not get AWS credentials."""
    trust = _role(bootstrap, "GitHubDeployRole")["AssumeRolePolicyDocument"]
    (statement,) = trust["Statement"]
    condition = statement["Condition"]["StringEquals"]

    assert condition["token.actions.githubusercontent.com:sub"] == {
        "Fn::Sub": "repo:${GitHubRepository}:environment:${GitHubEnvironment}"
    }


def test_deploy_role_requires_the_sts_audience(bootstrap: Document) -> None:
    trust = _role(bootstrap, "GitHubDeployRole")["AssumeRolePolicyDocument"]
    condition = trust["Statement"][0]["Condition"]["StringEquals"]

    assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"


def test_bootstrap_defaults_match_the_repository(bootstrap: Document) -> None:
    """GitHub's default OIDC subject names the owner and repository with their IDs."""
    assert (
        _default(bootstrap, "GitHubRepository")
        == "adamstradomski@83371226/cobra-bot-lambda@1400117730"
    )


def test_deploy_job_runs_in_the_trusted_environment(
    bootstrap: Document, workflow: Document
) -> None:
    assert workflow["jobs"]["deploy"]["environment"] == _default(
        bootstrap, "GitHubEnvironment"
    )


# --- what the roles can touch ------------------------------------------------------


@pytest.mark.parametrize("role", ["GitHubDeployRole", "CloudFormationExecutionRole"])
def test_bootstrap_roles_are_outside_the_app_stack_prefix(
    bootstrap: Document, role: str
) -> None:
    """The execution role manages roles named `${AppStackName}-*`; if the bootstrap
    roles matched that pattern, a change set could rewrite its own permissions."""
    name = _role(bootstrap, role)["RoleName"]["Fn::Sub"]

    assert not name.startswith("${AppStackName}-")


# Statements allowed on "*": these actions have no resource-level permissions.
UNSCOPED = {
    ("GitHubDeployRole", "ReadTemplates"),
    ("CloudFormationExecutionRole", "DescribeLogGroups"),
}


@pytest.mark.parametrize("role", ["GitHubDeployRole", "CloudFormationExecutionRole"])
def test_role_statements_are_scoped(bootstrap: Document, role: str) -> None:
    for statement in _statements(bootstrap, role):
        if (role, statement["Sid"]) in UNSCOPED:
            continue
        assert "*" not in _resources(statement), statement["Sid"]


# Statements on AWS-owned resources, which cannot carry the app stack's name.
AWS_OWNED = {("CloudFormationExecutionRole", "SamTransform")}


def test_execution_role_resources_are_named_after_the_app_stack(
    bootstrap: Document,
) -> None:
    for statement in _statements(bootstrap, "CloudFormationExecutionRole"):
        if ("CloudFormationExecutionRole", statement["Sid"]) in UNSCOPED | AWS_OWNED:
            continue
        for resource in _resources(statement):
            assert "${AppStackName}" in resource, statement["Sid"]


def test_execution_role_attaches_only_the_basic_execution_policy(
    bootstrap: Document,
) -> None:
    attaching = [
        s
        for s in _statements(bootstrap, "CloudFormationExecutionRole")
        if "iam:AttachRolePolicy" in s["Action"]
    ]

    basic = "arn:${AWS::Partition}:iam::aws:policy/service-role/"
    basic += "AWSLambdaBasicExecutionRole"

    assert [s["Condition"]["ArnEquals"]["iam:PolicyARN"] for s in attaching] == [
        {"Fn::Sub": basic}
    ]


@pytest.mark.parametrize(
    ("role", "service"),
    [
        ("GitHubDeployRole", "cloudformation.amazonaws.com"),
        ("CloudFormationExecutionRole", "lambda.amazonaws.com"),
    ],
)
def test_pass_role_is_limited_to_one_service(
    bootstrap: Document, role: str, service: str
) -> None:
    passing = [s for s in _statements(bootstrap, role) if s["Action"] == "iam:PassRole"]

    assert [s["Condition"]["StringEquals"]["iam:PassedToService"] for s in passing] == [
        service
    ]


@pytest.mark.parametrize("role", ["GitHubDeployRole", "CloudFormationExecutionRole"])
def test_role_can_expand_the_sam_transform(bootstrap: Document, role: str) -> None:
    """sam deploy creates the change set as the deploy role, and CloudFormation
    expands the transform as the execution role passed with --role-arn."""
    transform = _load("template.yaml")["Transform"]
    arn = "arn:${AWS::Partition}:cloudformation:${AWS::Region}:aws:transform/"
    arn += transform.removeprefix("AWS::")

    granted = [
        s
        for s in _statements(bootstrap, role)
        if s["Action"] == "cloudformation:CreateChangeSet"
        and _resources(s) == [str({"Fn::Sub": arn})]
    ]

    assert granted, f"{role} cannot run {transform}"


# Services the execution role needs for each resource type in template.yaml. A new
# resource type fails test_execution_role_covers_every_app_resource_type until it is
# added here and the role gets the matching permissions.
SERVICES_BY_RESOURCE_TYPE = {
    "AWS::S3::Bucket": {"s3"},
    "AWS::Logs::LogGroup": {"logs"},
    "AWS::Serverless::Function": {"lambda", "iam"},
    "AWS::Budgets::Budget": {"budgets"},
}


def test_execution_role_covers_every_app_resource_type(bootstrap: Document) -> None:
    app = _load("template.yaml")
    granted = {
        action.split(":")[0]
        for s in _statements(bootstrap, "CloudFormationExecutionRole")
        for action in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]])
    }

    for resource in app["Resources"].values():
        kind = resource["Type"]
        assert kind in SERVICES_BY_RESOURCE_TYPE, f"no permissions mapped for {kind}"
        assert SERVICES_BY_RESOURCE_TYPE[kind] <= granted, kind


# --- the workflow --------------------------------------------------------------------


def test_deploy_runs_after_ci_on_main(workflow: Document) -> None:
    ci = _load(".github/workflows/ci.yml")

    assert _triggers(workflow) == {
        "workflow_run": {
            "workflows": [ci["name"]],
            "types": ["completed"],
            "branches": ["main"],
        }
    }


def test_deploy_needs_a_successful_ci_push_run(workflow: Document) -> None:
    condition = workflow["jobs"]["deploy"]["if"]

    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "github.event.workflow_run.event == 'push'" in condition


def test_deploy_checks_out_the_commit_ci_tested(workflow: Document) -> None:
    checkout = workflow["jobs"]["deploy"]["steps"][0]

    assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"


def test_deploys_are_never_cancelled_halfway(workflow: Document) -> None:
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_only_the_deploy_job_gets_an_oidc_token(workflow: Document) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["deploy"]["permissions"]["id-token"] == "write"


def test_workflow_deploys_the_stack_the_roles_allow(
    bootstrap: Document, workflow: Document
) -> None:
    assert workflow["env"]["STACK_NAME"] == _default(bootstrap, "AppStackName")


def test_workflow_deploys_to_the_configured_region(workflow: Document) -> None:
    samconfig = tomllib.loads((ROOT / "samconfig.toml").read_text(encoding="utf-8"))
    region = samconfig["default"]["global"]["parameters"]["region"]
    aws_step = next(
        step
        for step in workflow["jobs"]["deploy"]["steps"]
        if step.get("uses", "").startswith("aws-actions/configure-aws-credentials@")
    )

    assert aws_step["with"]["aws-region"] == region


def test_every_action_is_pinned_to_a_commit(workflow: Document) -> None:
    for step in workflow["jobs"]["deploy"]["steps"]:
        if "uses" in step:
            ref = step["uses"].split("@")[1]
            assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), step[
                "uses"
            ]


def test_deploy_never_waits_for_a_change_set_prompt(workflow: Document) -> None:
    deploy = next(
        step
        for step in workflow["jobs"]["deploy"]["steps"]
        if step.get("name") == "Deploy stack"
    )

    assert "--no-confirm-changeset" in deploy["run"]
    assert "--no-fail-on-empty-changeset" in deploy["run"]
