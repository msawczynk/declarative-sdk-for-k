# MSP Managed-Company Writes Lift Plan

Status: offline design only. Do not run live Commander writes from this memo.

## Commander Calls

| Plan row | Commander class | Execute kwargs |
|---|---|---|
| `create` | `MSPAddCommand` / `msp-add` | `name`, optional `plan`, `seats`, `file_plan`, `addon`, `node` |
| `update` | `MSPUpdateCommand` / `msp-update` | `mc`, optional `name`, `plan`, `seats`, `file_plan`, `add_addon`, `remove_addon`, `node` |
| `delete` | `MSPRemoveCommand` / `msp-remove` | `mc`, `force=True` |

`mc` must prefer the live `mc_enterprise_id` / plan `keeper_uid`; fall back to
case-insensitive name only when no id is available. Delete may set `force=True`
only after DSK has enforced `--allow-delete`.

## Manifest Mapping

| Manifest path | Create kwarg | Update kwarg | Notes |
|---|---|---|---|
| `managed_companies[].name` | `name` | `name` for rename; `mc` only as fallback target | Names are unique case-insensitively. |
| `managed_companies[].plan` | `plan` | `plan` | Normalize live product id/display to the manifest string. |
| `managed_companies[].seats` | `seats` | `seats` | Absolute cap; canonical unlimited sentinel maps to Commander `-1`. |
| `managed_companies[].file_plan` | `file_plan` | `file_plan` | Omit when null/empty. |
| `managed_companies[].addons[]` | repeated `addon` | `add_addon` / `remove_addon` delta | Structured `{name,seats}` becomes `name` or `name:seats`. |
| future `managed_companies[].node` | `node` | `node` | Not in the current schema; do not claim support yet. |

## Clean Re-Plan

After each non-dry-run create, update, or delete, the provider must refresh
Commander enterprise state, rebuild the MSP diff, and produce a plan with:
`summary.create == 0`, `summary.update == 0`, `summary.delete == 0`,
`summary.conflict == 0`, and only expected `noop` rows for manifest-declared
managed companies. A delete proof is clean only when the removed disposable MC
is absent and no unrelated live MC appears as a delete candidate without
`--allow-delete`.

## Support-Lift Test Matrix

Required before DA moves MSP writes from `preview-gated` to `supported`:
offline kwargs tests for create/update/delete and dry-run rendering; mock
create/update/delete idempotence; duplicate-name, missing-target, and foreign
manager conflicts; sanitized Commander create -> discover -> clean re-plan;
sanitized update covering rename/plan/seats/file_plan/addons -> clean re-plan;
import/adoption marker contract; disposable delete dry-run + `--allow-delete`
apply + clean re-plan; leak check for stdout/stderr/artifacts; docs and matrix
claim updated to match the proven subset.

## Delete Risk

Estimated risk: high until live proof is narrow and boring. `msp-remove` can
detach or remove an MSP managed company from parent control, with licensing and
access consequences. The first support lift must use only a disposable MC,
fresh discover immediately before mutation, explicit target id/name, dry-run
review, `--allow-delete`, `force=True` behind that guard, and documented cleanup
evidence. Bulk or customer MC delete remains unsupported.
