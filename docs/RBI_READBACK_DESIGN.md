# RBI Readback Design

Status: mixed per-field support, audited on 2026-04-29.

Scope: W9 readback design for `resources[type=pamRemoteBrowser]` in
`pam-environment.v1`.

## Decision

Do not claim blanket RBI support. Claim only the fields with writer and
readback evidence. Keep list-shaped, audio-only, and unproven typed fields out
of the supported bucket until they have safe writer/readback proof.

Issue #5 can close with the per-field table below. Future work should link this
document instead of reopening a broad "RBI support" issue.

## Source Audit

Audit terms:

- `rbi`
- `remote_browser`
- `remote-browser`
- `rbiUrl`
- `pam rbi`
- `pamRemoteBrowserSettings`
- `allowedSettings`

Evidence:

| Area | Evidence | Meaning |
|------|----------|---------|
| Commander matrix | `docs/CAPABILITY_MATRIX.md` `pam rbi edit` | Commander exposes RBI edit flags, including list and audio flags. |
| Commander doc | `docs/COMMANDER.md` P3.1 table | Current SDK bucket language and field map. |
| Model/schema | `keeper_sdk/core/models.py`, `keeper_sdk/core/schemas/pam-environment.v1.schema.json` | Manifest shape for `pamRemoteBrowser`. |
| URL readback | `_coalesce_pam_remote_browser_url` | Commander `rbiUrl` maps to manifest `url`. |
| Typed settings readback | `_merge_pam_remote_browser_from_get_payload` | `pamRemoteBrowserSettings.connection` maps to manifest connection fields. |
| DAG tri-state readback | `_enrich_pam_remote_browser_dag_options` | `allowedSettings.connections` and `sessionRecording` map to options. |
| Writer argv | `_build_pam_rbi_edit_argv` | SDK wires the supported RBI edit subset. |
| Tests | `tests/test_rbi_readback.py`, `tests/test_commander_cli.py` | Offline readback/argv behavior is pinned. |
| Live proof | `docs/live-proof/keeper-pam-environment.v1.89047920.rbi.sanitized.json` | E2E smoke passed with clean re-plan and leak check. |

## Commander Surfaces

Pinned Commander exposes `pam rbi edit` flags for:

- `--configuration`
- `--remote-browser-isolation`
- `--connections-recording`
- `--autofill-credentials`
- `--autofill-targets`
- `--allow-url-navigation`
- `--allowed-urls`
- `--allowed-resource-urls`
- `--key-events`
- `--allow-copy`
- `--allow-paste`
- `--ignore-server-cert`
- `--disable-audio`
- `--audio-bit-depth`
- `--audio-channels`
- `--audio-sample-rate`

Commander does not expose a URL edit flag for RBI records. URL support is import
and readback only: `pam project import/extend` writes it, and `keeper get`
returns typed field `rbiUrl`, which DSK maps to manifest `url`.

## Field Status

Status meanings:

- `supported`: enough import/edit and readback evidence exists for a clean
  re-plan claim.
- `preview-gated`: DSK has a modeled or wired shape, but field-specific live
  proof is still missing.
- `upstream-gap`: pinned Commander/DSK shape lacks a safe writer/readback path
  for a support claim.

Base `pamRemoteBrowser` fields:

| Manifest path | Status | Evidence / caveat |
|---------------|--------|-------------------|
| `uid_ref` | supported | SDK identity/marker field; ignored in Commander field diff. |
| `type` | supported | Schema discriminator and import record type. |
| `title` | supported | Base PAM resource lifecycle. |
| `notes` | supported | Base typed record field; not RBI-specific. |
| `url` | supported | Live smoke clean re-plan; Commander `rbiUrl` -> manifest `url`. |
| `otp` | supported | Inherited base PAM typed-field surface; not part of W9 RBI gate. |
| `pam_configuration_uid_ref` | supported | Used for import/edit config binding and DAG readback resolution; ignored as placement metadata in field diff. |
| `shared_folder` | supported | Used for PAM project placement; ignored as placement metadata in field diff. |
| `attachments` | preview-gated | Modeled but ignored in PAM diff; no RBI-specific attachment writer/readback proof in W9. |

RBI options and connection fields:

| Manifest path | Status | Writer / readback |
|---------------|--------|-------------------|
| `pam_settings.options.remote_browser_isolation` | supported | `pam rbi edit --remote-browser-isolation`; read back from DAG `allowedSettings.connections`; live smoke clean. |
| `pam_settings.options.graphical_session_recording` | supported | `pam rbi edit --connections-recording`; read back from DAG `allowedSettings.sessionRecording`; live smoke clean. |
| `pam_settings.options.text_session_recording` | upstream-gap | Schema/model can carry it as extra, but `pam rbi edit` has no text recording flag and no readback proof. |
| `pam_settings.connection.protocol` | supported | Fixed `http` import/readback field; no post-import tunability claim. |
| `pam_settings.connection.autofill_credentials_uid_ref` | preview-gated | `pam rbi edit --autofill-credentials` is wired; needs focused live proof that `httpCredentialsUid` readback converges. |
| `pam_settings.connection.autofill_targets` | upstream-gap | Commander flag is repeatable, but manifest schema/model are scalar and no list-native readback proof exists. |
| `pam_settings.connection.allow_url_manipulation` | supported | `pam rbi edit --allow-url-navigation`; typed `pamRemoteBrowserSettings` readback; live smoke clean for false value. |
| `pam_settings.connection.allowed_url_patterns` | upstream-gap | Commander flag is repeatable, but manifest schema/model are scalar and readback can stay dirty. |
| `pam_settings.connection.allowed_resource_url_patterns` | upstream-gap | Same list-shape/readback gap as `allowed_url_patterns`. |
| `pam_settings.connection.recording_include_keys` | preview-gated | `pam rbi edit --key-events` is wired; needs focused live proof that `recordingIncludeKeys` readback converges. |
| `pam_settings.connection.disable_copy` | supported | `pam rbi edit --allow-copy` with inverted polarity; typed readback; live smoke clean for false value. |
| `pam_settings.connection.disable_paste` | supported | `pam rbi edit --allow-paste` with inverted polarity; typed readback; live smoke clean for false value. |
| `pam_settings.connection.ignore_server_cert` | supported | `pam rbi edit --ignore-server-cert`; typed readback via `ignoreInitialSslCert`; live smoke clean for false value. |
| `pam_settings.connection.disable_audio` | upstream-gap | Commander exposes `--disable-audio`, but DSK does not wire it and no readback proof exists. |
| `pam_settings.connection.audio_channels` | upstream-gap | Commander exposes `--audio-channels`, but DSK does not wire it and no readback proof exists. |
| `pam_settings.connection.audio_bps` | upstream-gap | Commander exposes `--audio-bit-depth`; DSK schema name differs and no writer/readback proof exists. |
| `pam_settings.connection.audio_sample_rate` | upstream-gap | Commander exposes `--audio-sample-rate`, but DSK does not wire it and no readback proof exists. |

Remaining risk fields classified by this pass: 10.

## Live-Proven Fields

The 2026-04-28 `pamRemoteBrowser` smoke proves:

- create -> verify -> clean re-plan -> destroy
- `url` readback through `rbiUrl`
- `remote_browser_isolation` readback through DAG `allowedSettings.connections`
- `graphical_session_recording` readback through DAG `allowedSettings.sessionRecording`
- typed connection readback for `protocol`, `allow_url_manipulation`,
  `disable_copy`, `disable_paste`, and `ignore_server_cert` as used in the
  scenario

Artifact:

```text
docs/live-proof/keeper-pam-environment.v1.89047920.rbi.sanitized.json
```

## Fields Still Needing Proof

Before moving any remaining field to `supported`, require:

1. SDK writer argv or import mapping.
2. Commander readback mapping into the exact manifest path used by
   `compute_diff`.
3. Offline test for argv and readback.
4. Live smoke showing apply -> discover -> clean re-plan.

Current proof gaps:

| Field group | Fields | Required next proof |
|-------------|--------|---------------------|
| Autofill credential | `autofill_credentials_uid_ref` | Live proof that `httpCredentialsUid` readback matches manifest refs after apply. |
| Key-event recording | `recording_include_keys` | Live proof that `recordingIncludeKeys` readback converges. |
| List-shaped controls | `autofill_targets`, `allowed_url_patterns`, `allowed_resource_url_patterns` | Schema/model must become list-native or Commander readback must normalize to scalar without dirty plans. |
| Audio controls | `disable_audio`, `audio_channels`, `audio_bps`, `audio_sample_rate` | Add SDK writer mapping, confirm Commander readback keys, then run focused smoke. |
| Text recording | `pam_settings.options.text_session_recording` | Needs a Commander RBI writer/readback surface or explicit schema removal for RBI. |

Audio keys are schema-permitted today and survive the permissive model as
extra fields, but they are not explicit `RbiConnection` attributes, are not
included in `_build_pam_rbi_edit_argv`, and have no proven Commander readback
mapping. They stay `upstream-gap` until all three are fixed together.

## GitHub #5 Close Body

Suggested close body:

```markdown
RBI readback is closed as a per-field support decision, not blanket RBI support.

Evidence:
- Live proof: `docs/live-proof/keeper-pam-environment.v1.89047920.rbi.sanitized.json`
- Design: `docs/RBI_READBACK_DESIGN.md`
- Commander field map: `docs/COMMANDER.md` P3.1
- DA gate: `docs/SDK_DA_COMPLETION_PLAN.md` Phase 3

Supported now:
- `url` via Commander `rbiUrl` readback
- `remote_browser_isolation`
- `graphical_session_recording`
- fixed `protocol: http`
- `allow_url_manipulation`
- `disable_copy`
- `disable_paste`
- `ignore_server_cert`

Still not supported:
- `autofill_credentials_uid_ref` and `recording_include_keys` until focused
  live proof lands
- list-shaped controls (`autofill_targets`, `allowed_url_patterns`,
  `allowed_resource_url_patterns`)
- audio controls (`disable_audio`, `audio_channels`, `audio_bps`,
  `audio_sample_rate`)
- RBI `text_session_recording`
```
