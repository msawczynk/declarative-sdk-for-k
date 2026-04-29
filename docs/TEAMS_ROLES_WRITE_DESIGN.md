# Teams/Roles Write Design

Status: DECIDED 2026-04-29 - read-only first; writes remain unsupported.

## Context

`keeper-enterprise.v1` currently packages schema-only enterprise scaffolding.
The `teams` and `roles` blocks are intentionally empty stubs (`maxItems: 0`),
and `dsk validate --online` is not wired for `keeper-enterprise.v1`. The
current CLI accepts offline schema validation for empty teams/roles blocks and
returns a capability error for enterprise online validation before any tenant
discovery runs.

This phase was executed as an offline worker slice with explicit instructions
not to run live Keeper, Commander, provider, or network commands. No live
tenant proof was produced by this slice.

## Decision

Do not implement team or role writes in v1.x. Keep teams/roles
`preview-gated` until a read-only enterprise discovery slice proves stable
Commander readback and an ownership model exists for enterprise objects.

The next supported step is read-only validation only:

1. Load a `keeper-enterprise.v1` manifest.
2. Discover live teams and roles with a sanctioned read-only Commander surface.
3. Normalize live rows into typed SDK payloads.
4. Compare manifest rows to live rows without mutating the tenant.
5. Emit a JSON summary with create/update/delete/conflict counts as validation
   evidence, but do not plan or apply mutations.

## Read Surface

Candidate read surfaces from the pinned Commander matrix:

- `enterprise-info -t -v --format json` for teams.
- `enterprise-info -r -v --format json` for roles.
- In-process `keepercommander.api.query_enterprise(params)` if it returns more
  stable IDs and relation payloads than the CLI renderer.

The SDK must prove the exact output shape on a lab tenant before making a
support claim. The live proof must include a sanitized compare of teams and
roles against a minimal manifest and must show that no write command ran.

## Future Manifest Shape

The first non-empty schema lift should model identity only. Memberships,
enforcements, managed nodes, and role privileges stay separate rows because
they have different blast radius and approval needs.

```yaml
schema: keeper-enterprise.v1
teams:
  - uid_ref: team.platform
    name: Platform
    node_uid_ref: keeper-enterprise:nodes:node.root
    restrict_edit: false
    restrict_share: false
    restrict_view: false
roles:
  - uid_ref: role.platform
    name: Platform Operators
    node_uid_ref: keeper-enterprise:nodes:node.root
```

The schema must keep `uid_ref` stable and separate from the live Keeper UID.
Live UIDs may appear only in discovery output, state/evidence, or an explicit
adoption mechanism.

## Write Boundary

Commander exposes apparent write primitives:

- `enterprise-team --add`, `--delete`, `--name`, `--node`,
  `--restrict-edit`, `--restrict-share`, `--restrict-view`, `-au`, `-ru`.
- `enterprise-role --add`, `--delete`, `--name`, `--node`, `--new-user`,
  `-au`, `-ru`, `-at`, `-rt`, `-aa`, `-ra`, `-ap`, `-rp`, `--enforcement`.

Those primitives are not enough for SDK support because teams and roles do not
currently have a proven Keeper-side ownership marker. The SDK contract says it
must not touch objects it does not own. Name matching alone is not ownership.

Therefore a future writer must first choose one of these ownership models:

| Option | Decision | Reason |
|--------|----------|--------|
| Keeper-side marker | Preferred if Commander exposes a metadata field | Matches PAM/vault ownership behavior. |
| Explicit adoption state | Possible, but needs a committed state format and recovery rules | Avoids name-only ownership but adds operator state. |
| Name-only management | Rejected | Cannot distinguish SDK-owned and manually-owned teams/roles. |
| Full-enterprise replacement | Rejected for v1.x | Too destructive and cannot meet default delete guardrails. |

Until one ownership model is proven, `plan`, `apply`, and `import` for
team/role mutations must raise capability errors or conflict rows with a
`next_action` pointing to this design.

## Approval Gates

Any future write support must satisfy all of:

- Source audit against the pinned Commander implementation.
- Offline schema/model tests for every field.
- Provider contract tests for generated Commander argv and JSON readback.
- Delete and membership-removal guards requiring `--allow-delete`.
- Live create -> readback -> clean re-plan -> guarded delete -> cleanup proof
  on a disposable team and role.
- Sanitized evidence proving no secret or raw UID leaks.
- Documentation and capability matrix updates in the same change.

## Current Operator Guidance

Use teams and roles as external enterprise prerequisites. Keep manifests
read-only for this surface until `keeper-enterprise.v1` online validation lands.
Do not represent intended team/role writes in a committed manifest yet.
