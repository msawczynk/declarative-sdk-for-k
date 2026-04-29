## Commander upstream fix — `pam rotation list` UID filter + JSON output

### Problem

`PAMListRecordRotationCommand` (`discoveryrotation.py:1220`) has no `--record-uid` filter and no `--format json`. Any UID passed as a positional argument raises `ParseError`. `pam access user list` raises `CommandError: not yet implemented`.

### SDK impact

Nested `pamUser.rotation_settings` re-plan is blocked; `preview-gated` classification holds until Commander ships the fix.

**Offline gate:** `tests/test_diff.py::test_diff_nested_pam_user_rotation_drift_surfaces_rotation_settings_key`

### Proposed Commander patch

Additive argparse extension to `PAMListRecordRotationCommand`:

```python
parser.add_argument("--record-uid", "-r", dest="record_uid", required=False)
parser.add_argument("--format", dest="output_format", choices=["table","json"], default="table")
```

### SDK-side wiring (after Commander fix)

Add in-process dispatch for `["pam", "rotation", "list", "--record-uid", uid, "--format", "json"]` in `commander_cli.py`, mirroring the `pam config list` / `pam gateway list` pattern.

### GH#35 comment posted

2026-04-29 — comment id **4342788306**.

### Status

Waiting for upstream keepercommander release. No SDK workaround (table parsing too fragile).
