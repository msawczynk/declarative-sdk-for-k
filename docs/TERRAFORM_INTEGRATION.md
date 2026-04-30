# DSK + Terraform Integration

DSK and Terraform are complementary declarative tools. Terraform should own infrastructure provisioning and any Keeper resources it already tracks in Terraform state. DSK should own Keeper tenant state that benefits from DSK's manifest graph, ownership markers, import/export flow, and field-level Keeper diff.

Workspace reference: the sibling [`../Terraform/`](../Terraform/) folder contains the local Terraform examples and modules used beside this repo. Provider reference: `keeper-security/terraform-provider-keeper` is the existing Keeper Terraform provider codebase; Terraform Registry source names may differ by provider package.

## Ownership Boundary

Use one source of truth per Keeper object:

| Area | Terraform role | DSK role | Boundary |
|---|---|---|---|
| Cloud infrastructure | Create VPCs, subnets, EC2 instances, RDS databases, security groups, DNS | Reference resulting hostnames, ports, labels, or exported values in manifests | Terraform owns cloud objects |
| Keeper vault records | Manage Terraform-tracked `secretsmanager_*` records when teams need Terraform state-driven secret bootstrap | Manage vault records through `keeper-vault.v1`, including import/adoption and DSK markers | Do not put the same record UID/title under both states |
| PAM machine/user/database/directory records | Can create PAM-shaped record types through Terraform provider resources | Manage PAM resources and PAM relationships through `pam-environment.v1` | Pick Terraform or DSK for each PAM record, not both |
| PAM gateway and PAM configuration | Usually not an infrastructure resource; Terraform may provision host/container prerequisites | DSK declares Keeper PAM tenant state around gateways, configs, machines, databases, directories, and remote browsers | DSK owns Keeper-side PAM lifecycle |
| Shared folders and shares | Terraform modules can look up folders and create records inside them | `keeper-vault-sharing.v1` owns folder/share intent when DSK is the source of truth | Terraform can consume folder UIDs; DSK can own sharing policy |
| Enterprise nodes and enforcement policies | `keeper_node` and `keeper_role_enforcements` fit Terraform compliance-as-code workflows | `keeper-enterprise.v1` is the DSK tenant-state surface for enterprise graph intent | Choose by operational workflow and state owner |
| KSM applications and tokens | Terraform can consume KSM credentials for provider auth | `keeper-ksm.v1` models KSM apps, tokens, record shares, and config outputs | Keep credential bootstrap separate from Terraform state secrets |
| SCIM, SSO, outbound email, integrations | Terraform may configure adjacent IdP/cloud resources | DSK integration families capture Keeper tenant intent as offline schema/diff surfaces | DSK validates Keeper intent; writers require proof |
| MSP and EPM | Terraform can provision external tenant or endpoint prerequisites | DSK models managed companies and EPM policy intent as Keeper tenant state | DSK currently treats writer gaps explicitly |

## Migration Pattern

When Keeper objects already exist and Terraform currently manages them:

1. Inventory Terraform state: `terraform state list` and `terraform state show <addr>`.
2. Decide which objects move to DSK. Leave unrelated infrastructure and Terraform-owned Keeper objects in Terraform.
3. Remove overlap first. Use `terraform state rm <addr>` only after the team has agreed that Terraform no longer owns that Keeper object.
4. Add the object to the matching DSK manifest family.
5. Run `dsk validate <manifest>`.
6. Run `dsk import <manifest> --dry-run`.
7. If the adoption plan is clean, run `dsk import <manifest> --auto-approve`.
8. Run `dsk plan <manifest> --json` and confirm the object is owned and stable.

The important invariant is that Terraform state and DSK ownership markers must never claim the same Keeper object at the same time.

## Day-2 Pattern

Run Terraform and DSK side by side with explicit handoff points:

```text
terraform plan  -> terraform apply  -> terraform output -json
                                           |
                                           v
                                  generated/checked DSK manifest values
                                           |
                                           v
                       dsk validate -> dsk plan --json -> dsk apply
```

Terraform outputs should carry non-secret infrastructure facts such as hostname, port, cloud resource ID, network tag, or environment name. DSK manifests should carry Keeper tenant intent such as vault records, PAM resources, sharing rules, KSM bindings, enterprise roles, and ownership metadata.

## Example

Terraform provisions a server:

```hcl
resource "aws_instance" "app" {
  ami           = var.ami
  instance_type = "t3.micro"
  subnet_id     = var.subnet_id

  tags = {
    Name = "app-prod-01"
  }
}

output "app_private_dns" {
  value = aws_instance.app.private_dns
}
```

DSK provisions the Keeper PAM state that watches it:

```yaml
version: "1"
name: prod-pam
gateways:
  - uid_ref: gw.prod
    name: prod-gateway
    mode: reference_existing
resources:
  - uid_ref: machine.app-prod-01
    type: pamMachine
    title: app-prod-01
    host: ${TF_OUTPUT_app_private_dns}
    gateway_uid_ref: gw.prod
```

The server remains Terraform-owned. The Keeper PAM machine record and its gateway relationship remain DSK-owned.

## Terraform Mapping Manifest

`keeper-terraform.v1` is a schema and typed-model stub for documenting integration boundaries. It validates mapping intent but intentionally does not support `plan` or `apply`.

```yaml
schema: keeper-terraform.v1
resource_mappings:
  - dsk_family: keeper-vault.v1
    tf_resource_type: secretsmanager_login
    direction: bidirectional
  - dsk_family: pam-environment.v1
    tf_resource_type: secretsmanager_pam_machine
    direction: tf_source
  - dsk_family: keeper-enterprise.v1
    tf_resource_type: keeper_role_enforcements
    direction: dsk_source
```

Directions mean:

| Direction | Meaning |
|---|---|
| `tf_source` | Terraform owns the resource; DSK may read or document the relationship but must not write it |
| `dsk_source` | DSK owns the Keeper tenant object; Terraform may consume exported facts but must not manage the object |
| `bidirectional` | Migration or comparison mapping only; operators must still choose one active writer before applying changes |

## Resource Comparison

| Keeper resource type | Terraform fit | DSK fit | Recommended owner |
|---|---|---|---|
| Login and general vault records | Strong for bootstrap records and generated passwords through `secretsmanager_*` resources | Strong for Keeper-native import, diff, and ownership markers through `keeper-vault.v1` | Use one owner per record |
| PAM machine, user, database, directory records | Useful when the record is part of an infra module | Strong when tied to PAM gateways, configs, adoption, and Keeper tenant drift | DSK for PAM lifecycle; Terraform for infra-coupled bootstrap |
| PAM gateways and PAM configurations | Provision host prerequisites only | Primary Keeper-side owner in `pam-environment.v1` | DSK |
| Remote browsers | Not a Terraform infrastructure primitive | Keeper PAM resource intent in `pam-environment.v1` | DSK |
| Shared folders and record shares | Useful for module inputs and KSM folder access patterns | Keeper sharing graph and adoption via `keeper-vault-sharing.v1` | DSK when sharing policy is the goal |
| KSM apps, tokens, record shares, config outputs | Terraform consumes KSM credentials to authenticate providers | DSK models the KSM tenant state in `keeper-ksm.v1` | DSK for Keeper state; Terraform for consumers |
| Enterprise nodes | Supported by Terraform administration provider as `keeper_node` | Modeled by `keeper-enterprise.v1` | Choose one state owner |
| Role enforcement policies | Supported by Terraform administration provider as `keeper_role_enforcements` | Enterprise policy intent can live in DSK family as it matures | Terraform today when already in compliance-as-code workflow |
| Teams, users, roles, aliases | Terraform data sources help discover existing state | DSK enterprise family is the Keeper tenant-state target | DSK when declarative lifecycle is required |
| SCIM, SSO, outbound email | Terraform may own IdP or SMTP infrastructure | DSK integration families validate Keeper-side intent | DSK schema/diff until writers are proven |
| MSP managed companies | Terraform can own external prerequisites | `msp-environment.v1` owns managed-company intent where supported | DSK for Keeper MSP state |
| EPM policy intent | Terraform can provision endpoint/cloud prerequisites | `keeper-epm.v1` models Keeper EPM policy intent | DSK schema/diff until writer proof |
| Reports, compliance, posture | Terraform is not a reporting engine | `dsk report ...` is the read-only path | Neither as mutable state |

## Operational Rules

- Do not manage the same Keeper UID, title, shared folder membership, or role policy in both Terraform state and a DSK manifest.
- Terraform outputs passed to DSK should be non-secret infrastructure facts. Keep secret values in Keeper, not in Terraform output.
- DSK imports/adopts unmanaged Keeper objects; it should not adopt objects still present in Terraform state.
- Terraform `plan` detects infrastructure and Terraform-state drift. DSK `plan` detects Keeper tenant drift against DSK manifests.
- A `keeper-terraform.v1` manifest is documentation/config metadata only; `dsk plan` and `dsk apply` return a capability error for it by design.
