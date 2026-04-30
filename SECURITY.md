# Security policy

## Supported versions

| Version | Supported            |
|---------|----------------------|
| 1.x     | Yes (active)         |
| < 1.0   | No (pre-release)     |

## Reporting a vulnerability

**Do not open a public GitHub issue for security problems.** Email the
maintainer (see the `Authors` block in `pyproject.toml`) or use GitHub's
private vulnerability-reporting feature under `Security` → `Report a
vulnerability` on this repository.

Include:

1. The command / manifest / environment that reproduces the issue.
2. The observed behaviour vs. what you expected.
3. Whether the issue leaks credentials, bypasses ownership markers, or
   touches records outside the manifest scope — those three classes of
   bug are triaged as P0.

We aim for an initial acknowledgement within 3 business days and a fix
or mitigation within 30 days for high-severity issues.

## Scope reminders

`dsk` (declarative-sdk-for-k) shells out to the installed `keeper` CLI (or its in-process
Python equivalent) via subprocess. The SDK itself never stores
credentials at rest, but any agent running it has the full blast radius
of whatever Keeper session it inherits. Protect the login helper
(`KEEPER_SDK_LOGIN_HELPER` or `EnvLoginHelper` env vars) the same way
you would protect a root-admin API token.

Ownership markers (`keeper_declarative_manager` custom field) are
declarative-only — they do not gate the tenant. A Keeper admin with
vault access can still delete a managed record out from under the SDK;
the next `plan` will surface that drift as a CONFLICT row.
