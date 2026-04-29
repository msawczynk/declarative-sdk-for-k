# DSK Ecosystem Roadmap

Strategic integration plan for declarative-sdk-for-k (DSK) within the Keeper Security ecosystem (April 2026 baseline).

## Positioning: what DSK fills

Keeper already ships orthogonal surfaces: Terraform provider v1.0.2 for enterprise admin (nodes, roles, teams, MSP), Commander CLI 17.2.16 for interactive and scripted operations, Commander Service Mode REST API v2 for queued execution with FILEDATA-backed commands (POST `/api/v2/executecommand-async`, poll, GET result; `api-key` header; 60 requests per minute), KSM MCP servers (Go v2.3.0 and Node.js) for secret CRUD to models, plus SCIM push and standard vault flows. Together they cover config-as-code admin, synchronous automation, secrets-to-LLMs, and directory sync—not a single deterministic manifest that spans PAM operational resources, vault record shape, sharing, enterprise graph, identity and events integrations, EPM posture, MSP discovery, or compliance reporting envelopes.

DSK fills that gap as a Python CLI and library: **declarative lifecycle** for Keeper PAM and related surfaces with one pipeline—`validate` → `plan` → `apply` → `diff` → `import` → `export`—and machine-readable exit codes plus redacted reports for pipelines and auditors. Terraform continues to own the enterprise admin plane; KSM MCP owns minimal secret CRUD at the model boundary; Commander Service Mode complements subprocess Commander. DSK does not compete with those products; it **composes** with them as the operational reconciliation layer for manifests and drift.

At runtime, DSK uses `MockProvider` for offline work, `CommanderCliProvider` (subprocess; current default) for live Commander, and `CommanderServiceProvider` (HTTP REST v2 toward Service Mode—in development) for environments that standardise on the async API rather than local CLI installs.

### Manifest families (roadmap shorthand)

Authoritative classifications (`supported` / `preview-gated` / `upstream-gap`): `docs/SDK_DA_COMPLETION_PLAN.md`.

- `pam-environment.v1` — Gateways, `pam_configuration`, machines, databases, directories, users, remote-browser (RBI) resources; roadmap stance: supported with live proof.
- `keeper-vault.v1` — Login records with typed fields; offline supported plus L1 live coverage.
- `keeper-vault-sharing.v1` — Shared folders and members; offline supported; live reconciliation pending ecosystem brief.
- `keeper-enterprise.v1` — Nodes, users, roles, teams, enforcement concepts; offline supported.
- `keeper-ksm.v1` — KSM apps, tokens, record shares, config outputs as modeled; offline supported.
- `keeper-integrations-identity.v1` — Domains, SCIM, SSO, outbound email as modeled; offline supported.
- `keeper-integrations-events.v1` — Automator rules, audit-alert wiring, API keys, event routes as modeled; offline supported.
- `keeper-pam-extended.v1` — Extended gateway configs, rotation schedules, discovery rules as modeled; offline supported.
- `keeper-epm.v1` — EPM watchlists, policies, approvers as modeled; offline supported.
- `msp-environment.v1` — Managed companies; validate and discover supported; Commander `apply` preview-gated per DA plan—not restated here.
- `keeper-secrets/bus.py` — KSM inter-agent compare-and-swap message bus; offline proven integration point; live proof pending parity with MCP secret flows.

`dsk report` subcommands (`password-report`, `compliance-report`, `security-audit-report`) sit beside these families: they summarise Commander session state into redacted JSON for leak checks—orthogonal to Terraform’s enterprise primitives and MCP’s credential edge.

## Integration map

Integrations listed in **priority order** (delivery stack); effort S/M/L, strategic value H/M/L, ship-as OSS / product / connector per row.

| Integration | What it does | DSK role | Effort | Strategic value | Ship as |
|---|---|---|---|---|---|
| CommanderServiceProvider (HTTP REST v2) | Calls Service Mode execute-async, polls completion, supports FILEDATA inline JSON for file-based commands; api-key auth; 60/min | Second live backend beside `CommanderCliProvider`; same planner/marker semantics over HTTP | S | H | OSS |
| DSK as MCP server | Tools such as validate, plan, apply, diff, report, bus-adjacent helpers | Agent-safe façade; identical contracts to CLI for CI and assistants | M | H | OSS |
| GitHub Actions gate | `dsk plan` (and/or validate) on PR; drift fails merge | Policy-as-code without one-off shell | S | H | OSS |
| KSM bus (`keeper-secrets/bus.py`) | Inter-agent CAS coordination over KSM | Credential and step handoff between agents; pairs with MCP secret tools | M | H | OSS |
| HashiCorp Vault → Keeper migration | Export/mapping from Vault to manifest shapes DSK can plan/apply | Migration and adoption using existing `export`/`import` choreography | M | H | OSS |
| Kubernetes External Secrets Operator bridge | KSM app lifecycle and config outputs → ESO SecretStore patterns | Clusters consume Keeper without bespoke operators per team | M | H | OSS / product |
| Backstage plugin | Entities or metadata from `dsk report` envelopes | Catalog and developer portal truth from posture snapshots | M | M | OSS |
| MSP fleet templates | Parameterised manifests for bulk managed-company provisioning | Scales `msp-environment.v1` patterns where product owns rollout | S | H | product |
| Drift reconciliation daemon | Cron `dsk plan` → GitHub issue or Slack on delta | Continuous reconciliation signal outside PR cadence | S | M | OSS |
| SIEM feed connector | `keeper-integrations-events.v1`-related streams → Splunk, Datadog, ELK | Normalised security analytics path | M | M | connector |
| Compliance-as-code packages | SOC2 / ISO27001 evidence shaped from `dsk report` + sanitisation | Maps redacted artefacts to control narratives | M | H | connector |
| Multi-tenant federation | Cross-tenant `uid_ref` with explicit tenant prefix/boundary rules | Fleet ambiguity reduction for MSP-style operations | L | M | product |
| Crossplane provider | DSK as reconciliation engine behind Crossplane compositions | Optional for teams invested in Crossplane control planes | L | L | OSS |

**Reading the columns.** *Effort* estimates engineering cost for a credible first ship; it does **not** always match calendar ordering when one Medium-cost item removes duplicate work downstream. *Strategic value* informs portfolio investment; High still defers when dependencies (providers, CI) are unfinished. *Ship as* distinguishes Apache-2 OSS work, Keeper product-managed accelerators, and customer-run connectors outside the core wheel.

## Integrator bindings (non-normative)

Integration work assumes behaviours documented for agents in `AGENTS.md`:

- **`validate` versus `plan` exit 2.** `dsk validate` uses exit **2** for schema/validation failures. `dsk plan` and `dsk diff` also use exit **2** when a non-empty delta exists—CI must branch on **subcommand**, not treat all exit **2** as failure.
- **Plan JSON.** GitHub Actions, drift daemons, and prospective MCP tooling should consume `dsk plan --json` (`summary`, `changes[]`) instead of scraping human-readable tables—stable for automation.
- **`dsk report`.** Compliance and SIEM integrations must honour sanitisation switches (`--sanitize-uids`, `--quiet`) before forwarding envelopes to sinks that are not Keeper-vault compartments.
- **`dsk export`.** Vault → Keeper migration paths align with Commander-shaped JSON lift already supported for PAM—not inventing alternate schema dialects beside `AGENTS.md` contracts.

**Layering notes.** MCP tools should forward Commander/Service credential env deliberately (no silent inheritance across hosts). Periodic drift runners may use read-only Commander sessions while PR workflows use ephemeral credentials—same manifest, different IAM posture. Enterprise Terraform remains available for MSP/nodes roles where customers already invested; migrating those into DSK manifests is explicitly out of scope unless a later product decision merges planes.

## 6-month implementation sequence

Order rationale: unblock **providers and CI** first (predictable backends + merge gates); then **agent interfaces** (MCP, bus live proof); then **migration and runtime drift** (Vault, daemon); then **Kubernetes and MSP productisation**; then **SOC/analytics/catalog** once report shapes stabilize; finally **multi-tenant model** and **Crossplane exploration**—highest coupling and weakest forced rank.

1. **CommanderServiceProvider** — Close the trio Mock / CLI subprocess / HTTP Service so Hosted Commander and air-gapped policies can converge on one reconciliation story.
2. **GitHub Actions gate** — Ships with minimal deps: install `dsk`, run validate/plan, surface exit **2** on drift—matches existing CLI contract documented in AGENTS tables.
3. **DSK MCP server** — Thin tool mapping after CLI verbs are frozen for Actions users; avoids double semantics between “chat ops” and “repo ops”.
4. **KSM bus live path** — Move bus from offline-proven CAS stories to audited live usage beside KSM MCP; defines agent coordination without collapsing into raw secret bleed.
5. **HashiCorp Vault migration** — Proves portability narrative early; leverages export patterns already central to Keeper adoption motions.
6. **Drift daemon** — Operationalises the same plan JSON operators already inspect in Actions; separates merge-time hygiene from steady-state alerting.
7. **ESO bridge** — Targets platform teams; optional product packaging covers enterprise support wrappers if Keeper product owns GA stamp.
8. **MSP fleet templates** — Validates bulk MSP flows implied by discovery where `msp-environment.v1` apply stays preview-gated until product aligns upstream hooks.
9. **SIEM + compliance connectors** — Consumes stabilised automator/events/report contracts; postpones churn from immature schemas.
10. **Backstage plugin** — Once report JSON is stable enough for third-party UI embeds.
11. **Multi-tenant federation** — Requires sustained single-tenant Service+CLI proof at scale; impacts graph and ref semantics—defer until lower-risk wins land.
12. **Crossplane provider** — Exploratory; overlaps Terraform for admin plane; only after DSK core provider matrix is boring.

### Quarterly cut (informal)

| Quarter | Theme | Dominant integrations (table above) |
|---|---|---|
| Q1 | Close live backends + CI signal | CommanderServiceProvider; GitHub Actions gate; early DSK MCP tool list locked to CLI |
| Q2 | Agents + migrations + drift | MCP hardening; KSM bus live proof; Vault → Keeper exporter; drift daemon |
| Q3 | Platforms + MSP | ESO bridge; MSP fleet templates; SIEM connector beta |
| Q4 | Evidence + federation + exploration | Compliance packages; Backstage; multi-tenant federation design spike; Crossplane prototype if still justified |

Quarter labels are planning aids only—they assume maintainers converge on branch policy, exit-code discipline, and provider parity without slipping preview gates documented in `docs/SDK_DA_COMPLETION_PLAN.md`.

## AI-native zero-trust stack

The practical AI stack stitches three layers: **KSM MCP** (Go v2.3.0 and Node.js) for minimally scoped secret CRUD to models; **DSK MCP** for validate/plan/report (dry-run-first) over manifests; and **`keeper-secrets/bus.py`** for compare-and-swap coordination so multiple agents do not stampede the same reconcile without KSM-backed claims. Together they reduce long-lived secrets in prompts while keeping intent in versioned manifests—not one-off shell—aligned with zero-trust patterns (least privilege, attestable steps, auditable drift).

```
                    +------------------------+
                    |   Operator / LLM       |
                    |   (policy, intent)     |
                    +-----------+------------+
                                |
            +-------------------+-------------------+
            |                                       |
            v                                       v
   +------------------+                    +------------------+
   | KSM MCP          |                    | DSK MCP          |
   | secret CRUD      |                    | validate|plan     |
   | (Go / Node)      |                    | apply|diff|report|
   +--------+---------+                    +--------+---------+
            | creds / refs                           | desired state
            v                                       v
   +------------------+                    +------------------+
   | keeper-secrets   |<---- CAS bus ----->| Agents / CI      |
   | bus.py           |     handoff       | GitHub, k8s cron |
   +------------------+                    +------------------+
            |                                       |
            +------------------+--------------------+
                               v
                    +------------------------+
                    | Keeper tenant +        |
                    | Commander / Service    |
                    +------------------------+
```

**Composition:** MCP answers *which secret*; DSK MCP answers *which declared state*; the bus answers *which agent owns the next mutation step*—stacked, not redundant.

**Guardrails for agent surfaces.** Nothing in the stack replaces interactive Commander review for destructive applies: dry-run (`plan`, `--dry-run` where applicable) remains the default agent posture; Service Mode rate limits imply backoff policies in MCP tool implementations; `dsk report` leak checks (exit **1** on suspected material exposure) should surface to orchestrators before posting logs to tickets.

## Open questions (escalate to human)

1. **Service Mode SLA and blast radius.** When `CommanderServiceProvider` executes mutating plans in production, who owns incident response for Keeper-hosted execution versus customer-controlled Commander CLI paths? Customer-facing SLAs and forensic clarity (“which principal issued which async command”) matter for regulated buyers even when DSK remains OSS.
2. **Product versus OSS boundaries for MSP accelerators and federation.** Which templates stay commercial-only deliverables versus reference manifests under Apache-2? Misalignment here drives fork risk and duplicate community effort.
3. **Rate limit strategy (60 requests per minute).** Should DSK transparently batch or serialise Service Mode calls, or should orchestration layers (GitHub Actions, operators, agent frameworks) own pacing? Picking wrong default starves large manifests or hides backpressure from operators.
4. **Evidence retention for compliance-as-code packages.** SOC2 and ISO27001 evidence derived from `dsk report` outputs may require customer-controlled storage and explicit retention windows; connector defaults must not silently centralise multi-year archives in vendor SaaS without contractual basis.

## Adjacent canonical docs

| Document | Why integrators open it |
|---|---|
| `AGENTS.md` | Command table (`dsk validate|plan|apply|…`), exit-code binding contract, autonomy rules for harness-backed live tenants. |
| `docs/SDK_DA_COMPLETION_PLAN.md` | Supported vs preview-gated vs upstream-gap classifications per modeled capability—not duplicated here. |
| `docs/VALIDATION_STAGES.md` | Stage-by-stage semantics that explain overloaded exit **2** on `validate`. |
| `docs/LIVE_TEST_RUNBOOK.md` | Runbook for committed live harnesses (`scripts/smoke/`) when proving Commander paths with standing lab policy. |

**Terminology (roadmap shorthand).**

- **Operational plane vs admin plane.** DSK manifests describe tenant operational resources (PAM stacks, integrations, vault share graphs, MSP discovery inputs). Terraform/Keeper provider maps enterprise admin knobs (MSP/nodes roles teams) cited above—overlap is intentional orchestration across products, not duplicate CRUD semantics.
- **Preview-gated.** A capability passes offline validation yet mutating paths stay blocked until Keeper CLI/Service verbs exist or policy unlocks—the DA plan retains the authoritative list (`msp-environment.v1` apply called out upstream).
- **Connector.** Ships outside core `pip install dsk` distribution—maintained as integration glue (SIEM exporters, SOC evidence bundlers).

---

Ecosystem reference (April 2026): Commander CLI 17.2.16; Terraform provider v1.0.2; Commander Service REST v2 (async queue, FILEDATA); KSM MCP Go v2.3.0 and Node.js; SCIM push. DSK capability matrix: `docs/SDK_DA_COMPLETION_PLAN.md`.
