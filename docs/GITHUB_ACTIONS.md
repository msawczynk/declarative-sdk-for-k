# GitHub Actions

This repo ships two composite actions for GitOps-style DSK checks:

- `.github/actions/dsk-plan`: validates a manifest, runs `dsk plan --json`, exposes machine-readable outputs, and can post a PR comment with the plan table.
- `.github/actions/dsk-drift`: runs scheduled `dsk plan --json` against a live provider and opens or updates a GitHub issue when drift is detected.

Both actions install the `dsk` CLI from the checked-out repo when they run inside this repository. In downstream repositories, they install the package from `msawczynk/declarative-sdk-for-k@main`.

## PR Plan Check

Use the plan action in pull requests to show the create / update / delete rows before merge:

```yaml
name: dsk plan

on:
  pull_request:

permissions:
  contents: read
  issues: write
  pull-requests: write

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: dsk-plan
        uses: ./.github/actions/dsk-plan
        with:
          manifest_path: env.yaml
          provider: mock
          allow_delete: "false"
          post_comment: "true"
```

Outputs:

| Output | Meaning |
|---|---|
| `plan_clean` | `true` when plan exit is clean and no create / update / delete / conflict rows exist. |
| `conflict_count` | Number of conflict rows in `summary.conflict`. |
| `change_count` | `create + update + delete + conflict`. |

`dsk plan` exit code `2` means changes are present, so the action does not fail on that code. It fails on conflicts (`4`) and unexpected CLI/provider failures.

## Scheduled Drift

Use the drift action on a schedule with a live provider. It opens or updates one issue per manifest using a hidden marker in the issue body, so repeated drift checks do not create duplicate issues.

```yaml
name: dsk drift

on:
  schedule:
    - cron: "0 */6 * * *"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/dsk-drift
        with:
          manifest_path: env.yaml
          issue_label: dsk-drift
          assignees: platform-admin
        env:
          DSK_PROVIDER: commander
          KEEPER_SDK_LOGIN_HELPER: ksm
          KSM_CONFIG: ${{ secrets.KSM_CONFIG }}
          KEEPER_DECLARATIVE_FOLDER: ${{ secrets.KEEPER_DECLARATIVE_FOLDER }}
```

The example workflow in `.github/workflows/dsk-example.yml` includes the same schedule but gates the drift job behind repository variable `DSK_DRIFT_ENABLED=true`. This prevents a copied example from opening issues before a live manifest and credentials are configured.

## Secrets

For the hosted service provider, set:

| Secret | Meaning |
|---|---|
| `KEEPER_SERVICE_URL` | DSK service endpoint. |
| `KEEPER_SERVICE_API_KEY` | API key for the service endpoint. |

For Commander with KSM-backed login, set:

| Secret / variable | Meaning |
|---|---|
| `KSM_CONFIG` | KSM client config JSON or path. If JSON is supplied, the action writes it to a temp file and sets `KEEPER_SDK_KSM_CONFIG`. |
| `KEEPER_DECLARATIVE_FOLDER` | Optional shared-folder UID scope for vault/Commander runs. |
| `KEEPER_SDK_LOGIN_HELPER=ksm` | Repository variable that tells DSK to load Keeper credentials from KSM. |

For Commander with direct env login, set:

| Secret | Meaning |
|---|---|
| `KEEPER_EMAIL` | Keeper admin email. |
| `KEEPER_PASSWORD` | Keeper admin password. |
| `KEEPER_TOTP_SECRET` | Base32 TOTP secret, not a 6-digit code. |

Provider values:

| Provider | Use |
|---|---|
| `mock` | Offline PR checks and examples. |
| `commander` | Live tenant planning through Keeper Commander. |
| `service` | Hosted DSK service deployments that expose a service provider. |

## GitOps Flow

```text
commit manifest
      |
      v
open PR
      |
      v
dsk-plan action
      |
      +--> validate schema / refs
      |
      +--> dsk plan --json
      |
      +--> PR comment with plan table
      |
      v
review + merge
      |
      v
dsk apply in controlled deploy job
      |
      v
scheduled dsk-drift action
      |
      +--> clean plan: no issue
      |
      +--> exit 2 drift: open/update issue
```

Keep `apply` in a separate deploy workflow with explicit approval. The PR action is a planning gate only; it never mutates the tenant.
