## Commander upstream fix — `pam rotation list` UID filter + JSON output

### Problem

`PAMListRecordRotationCommand` (`discoveryrotation.py:1220`) formerly had no
`--record-uid` filter and no `--format json`. Any UID passed as a positional
argument raised `ParseError`. `pam access user list` raised `CommandError: not
yet implemented`.

### SDK impact

Resolved in Commander 17.2.16 (pin
`6574827cf2993d2a54484516c2f4cc33238f98c9`): nested
`resources[].users[].rotation_settings` can now be read with
`pam rotation list --record-uid --format json`, and the SDK hydrates that state
during discover. Top-level `users[].rotation_settings`,
`resources[].rotation_settings`, and `default_rotation_schedule` remain blocked.

**Offline gate:** `tests/test_diff.py::test_diff_nested_pam_user_rotation_drift_surfaces_rotation_settings_key`

### Commander patch

Additive argparse extension to `PAMListRecordRotationCommand`:

```python
parser.add_argument("--record-uid", "-r", dest="record_uid", required=False)
parser.add_argument("--format", dest="output_format", choices=["table","json"], default="table")
```

### SDK-side wiring

Implemented in `commander_cli.py`: in-process dispatch for
`["pam", "rotation", "list", "--record-uid", uid, "--format", "json"]`,
mirroring the `pam config list` / `pam gateway list` pattern.

### GH#35 comment posted

2026-04-29 — comment id **4342788306**.

### Status

Closed for the nested `resources[].users[]` slice on Commander 17.2.16+.
