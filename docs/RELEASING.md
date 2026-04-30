# Releasing

Distribution is **GitHub only** (this repository and its **Releases**). There
is **no** PyPI project for `declarative-sdk-for-k`.

## Install for consumers

From a clone (contributors):

```bash
pip install -e '.[dev]'
```

From a **tag** without cloning the full repo (pinned version):

```bash
pip install git+https://github.com/msawczynk/declarative-sdk-for-k.git@v1.0.0
```

Or download **sdist / wheel** assets attached to the GitHub Release and:

```bash
pip install path/to/wheel.whl
```

## Maintainer release ritual

1. Bump `version = "X.Y.Z"` in `pyproject.toml`.
2. Update `CHANGELOG.md` with a dated `## [X.Y.Z] - YYYY-MM-DD` section.
3. Commit the release prep on `main`.
4. Create the GitHub release (tag `vX.Y.Z`):

   ```bash
   gh release create vX.Y.Z --generate-notes
   ```

5. Watch **Actions → Release assets** (workflow `publish.yml`) complete; it
   builds with `python -m build`, runs `twine check`, and uploads `dist/*`
   to the release via `gh release upload`.
6. Sanity-check install from git URL or from downloaded wheel in a clean venv.

No PyPI credentials, trusted publishers, or `pypi-publish` environment are
required.

## Rollback

1. Tell consumers to pin the previous tag or wheel:

   ```bash
   pip install git+https://github.com/msawczynk/declarative-sdk-for-k.git@v<prev>
   ```

2. File a short post-mortem with cause, blast radius, and follow-up.
3. On GitHub, edit the release notes or yank misleading assets if needed;
   do not re-use the same version number after a bad publish.
