# Releasing

## Prereqs (one-time, by maintainer)

1. Create the project on PyPI as `declarative-sdk-for-k` if it does not
   exist yet.
2. In PyPI, add a trusted publisher for GitHub Actions:
   owner `msawczynk`, repository `declarative-sdk-for-k`, workflow
   `.github/workflows/publish.yml`, environment `pypi-publish`.
   Reference: <https://docs.pypi.org/trusted-publishers/>.
3. In GitHub repo settings, create protected environment
   `pypi-publish`, add required reviewers, and leave credentials empty.
   `publish.yml` uses GitHub OIDC, not a PyPI API token.

## Release ritual

1. Bump `version = "X.Y.Z"` in `pyproject.toml`.
2. Update `CHANGELOG.md` with a dated `## [X.Y.Z] - YYYY-MM-DD` section.
3. Commit the release prep.
4. Create the GitHub release:

   ```bash
   gh release create vX.Y.Z --generate-notes
   ```

   If maintainer signing is configured, create the signed tag first and
   then run `gh release create` against that tag.
5. Watch `.github/workflows/publish.yml` complete successfully in
   Actions.
6. Verify the package and version on PyPI.

## Rollback

1. Tell consumers to install the previous good version:

   ```bash
   pip install declarative-sdk-for-k==<prev>
   ```

2. File a short post-mortem with cause, blast radius, and follow-up.
3. Yank the bad release if needed, but never re-use that version number.
