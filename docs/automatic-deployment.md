# Automatic deployment from main

How a push to `main` deploys the bot through GitHub Actions, and the one-time setup it needs. Manual deployment is in the [README](../README.md#run-your-own-bot).

Every push to `main` (normally a merge from `develop`) deploys the `cobra-bot` stack once CI passes. [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) starts when the CI workflow finishes successfully for a push to `main`. It checks out the commit CI tested, runs `sam build`, then `sam deploy` without a change-set prompt. A push that changes nothing in the stack still succeeds (`--no-fail-on-empty-changeset`). Only one deploy runs at a time and none is cancelled halfway. A failed CloudFormation update rolls back to the previous version and fails the job.

GitHub Actions holds no AWS keys. It signs in through OIDC as the role `github-deploy-cobra-bot`, which can only upload the build to SAM's artifact bucket and run change sets on the `cobra-bot` stack. CloudFormation applies them as `cfn-exec-cobra-bot`, which can only manage resources whose names start with `cobra-bot-`: functions, their roles, the cache bucket, log groups and the budget. Both roles are defined in [`bootstrap/github-deploy.yaml`](../bootstrap/github-deploy.yaml). `tests/test_deploy_setup.py` checks that the roles stay scoped and agree with the workflow. Anyone who can push to `main` can change the inline policies of the `cobra-bot-*` function roles, so protect `main`.

One-time setup:

1. **Deploy the roles** with administrator credentials. `SamArtifactBucket` is the `SamCliSourceBucket` output of the `aws-sam-cli-managed-default` stack, created by the first manual `sam deploy`. Pass `CreateOidcProvider=false` if the account already has an identity provider for `token.actions.githubusercontent.com`. The role trusts only the `production` environment of the repository named by `GitHubRepository`, written as GitHub's OIDC subject prefix shows it under repository **Settings → Actions → OIDC** (`owner@owner-id/name@repo-id`). Override it if that prefix differs; a mismatch fails the deploy with `Not authorized to perform sts:AssumeRoleWithWebIdentity`.

   ```bash
   aws cloudformation deploy --region eu-central-1 --stack-name github-deploy-cobra-bot --template-file bootstrap/github-deploy.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides SamArtifactBucket=<SamCliSourceBucket>
   ```

   Then print the two role ARNs:

   ```bash
   aws cloudformation describe-stacks --region eu-central-1 --stack-name github-deploy-cobra-bot --query "Stacks[0].Outputs" --output table
   ```

   Do not name this stack `cobra-bot-…`: the execution role may modify anything with that prefix.

   **Updating the roles later.** On an existing stack, `aws cloudformation deploy` keeps the stored value of every parameter you don't pass, even when the template's default has changed; if nothing else changed it reports `No changes to deploy`. Pass any parameter whose new value you want explicitly, for example after changing the `GitHubRepository` default:

   ```bash
   aws cloudformation deploy --region eu-central-1 --stack-name github-deploy-cobra-bot --template-file bootstrap/github-deploy.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides GitHubRepository=adamstradomski@83371226/cobra-bot-lambda@1400117730
   ```

   Check the subject the role now trusts:

   ```bash
   aws iam get-role --role-name github-deploy-cobra-bot --query "Role.AssumeRolePolicyDocument.Statement[0].Condition"
   ```

2. **Create the GitHub environment.** Repository **Settings → Environments → New environment** `production`. Under **Deployment branches and tags**, choose **Selected branches and tags** and add `main`. Leave **Required reviewers** off for fully automatic deploys.

3. **Add the environment's values** (same page):

   | Kind | Name | Value |
   |------|------|-------|
   | Variable | `AWS_DEPLOY_ROLE_ARN` | `GitHubDeployRoleArn` output |
   | Variable | `AWS_CFN_EXECUTION_ROLE_ARN` | `CloudFormationExecutionRoleArn` output |
   | Variable | `DISCORD_PUBLIC_KEY` | The deployed `DiscordPublicKey` (in `samconfig.local.toml` under `parameter_overrides`) |
   | Secret | `BUDGET_EMAIL` | The deployed `BudgetEmail` |

   Use the values already deployed. A different public key breaks the Discord endpoint, and a different e-mail moves the budget alert.

4. **Protect `main`** (**Settings → Rules → Rulesets → New branch ruleset**, target `main`, enforcement **Active**, empty bypass list). Select **Restrict deletions**, **Block force pushes** and **Require status checks to pass** with the check `Lint, type-check, test`. Leave **Require a pull request before merging** and **Require linear history** off: `main` is updated by pushing `develop`, which contains merge commits.

5. **Release:** once CI is green on `develop`, fast-forward `main` to it:

   ```bash
   git push origin develop:main
   ```

   The required status check accepts only a commit that already passed CI, so wait for the `develop` run to finish. A merge commit made locally has no checks yet and is rejected, which is why `main` is only ever fast-forwarded. Follow the deploy under **Actions → Deploy**. The first run also records `cfn-exec-cobra-bot` as the stack's CloudFormation role.

Manual `sam deploy` from your machine still works. After step 5 the stack uses `cfn-exec-cobra-bot` for every update, so your own deploys also need permission to pass that role (`iam:PassRole`). An administrator has it.
