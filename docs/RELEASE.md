# Release process

This repository has no release automation. Releases are manual and must be reproducible from a clean checkout.

## Versioning

Reachy uses semantic versioning for its own code:

- MAJOR for incompatible CLI, database, or policy behaviour.
- MINOR for backward-compatible features.
- PATCH for fixes.

Update both locations and keep them identical:

- `pyproject.toml` → `[project].version`
- `reachy/__init__.py` → `__version__`

Database migrations are append-only. Never edit an applied migration; add a new numbered file under `reachy/migrations/`. The schema version is the highest applied migration number.

## Pre-release checklist

- [ ] `git status` is clean except for intended release changes.
- [ ] No secrets, tokens, customer databases, browser profiles, or exports are staged.
- [ ] `README.md`, `AGENTS.md`, and docs match actual behaviour.
- [ ] New CLI options and policy fields are documented.
- [ ] Dependency and licence report is current (`docs/DEPENDENCY_LICENSES.md`).
- [ ] Version is consistent in `pyproject.toml` and `reachy/__init__.py`.
- [ ] Migration upgrade path is tested from the previous schema version.
- [ ] `reachy init` is idempotent on an existing database.
- [ ] Global pause, dry run, and test recipient were exercised.
- [ ] Browser diagnostics were exercised on at least one supported platform.
- [ ] Gmail/SMTP changes were tested with mocked or test accounts, never live prospects.
- [ ] No real prospect email was sent during testing.

## Test and verify

```bash
python3 -m compileall -q reachy google_maps_leads leads email_outreach
python3 -m pytest -q
python3 -m reachy --version
python3 -m reachy --help
```

Run the full test suite from a clean virtual environment that has the `dev`, `browser`, and `gmail` extras installed. The suite must not send real email; it uses mocked providers and test recipients.

Optionally check the installed metadata:

```bash
pip check
python -m pip show reachy
```

## Build

```bash
python -m pip install --upgrade build
rm -rf dist/ build/ *.egg-info
python -m build
```

Inspect the wheel contents:

```bash
python -m zipfile -l dist/reachy-<version>-py3-none-any.whl
```

Confirm that `reachy/migrations/001_initial.sql` is present and that no tests, local databases, keys, logs, browser profiles, or sample customer exports are included.

For a source install test:

```bash
python -m venv /tmp/reachy-release-venv
/tmp/reachy-release-venv/bin/pip install "dist/reachy-<version>-py3-none-any.whl[browser,gmail]"
/tmp/reachy-release-venv/bin/reachy init --home /tmp/reachy-release-home
/tmp/reachy-release-venv/bin/reachy --home /tmp/reachy-release-home doctor
```

Delete the temporary home and virtual environment afterwards.

## Commit and tag

```bash
git add <intended files>
git commit -m "release: v<version>"
git tag -a v<version> -m "Reachy v<version>"
git push origin main --tags
```

Do not commit generated `dist/` artifacts unless your distribution process explicitly requires them. Attach built artifacts and checksums to the release in your hosting platform.

## After release

- Smoke-test the published artifact in a fresh environment.
- Verify upgrade from the previous release using a copy of a real database, never the only copy.
- Record known limitations in the release notes.
- Revoke any test OAuth clients or sender credentials created for the release.

## Rollback

Application rollback does not automatically roll back the database schema. Before downgrading:

1. Stop workers and enable `reachy pause`.
2. Back up the database and key.
3. Restore the pre-upgrade database if the new schema is incompatible with the old code.
4. Reinstall the previous package version.
5. Run `reachy doctor` and a mock campaign smoke test.

Never downgrade by editing migration rows in place.
