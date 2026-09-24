# Release Process

For maintainers. Releasing a new version of `barndoor` on PyPI.

## What changed

**This repository no longer holds the source of the SDK, and `pyproject.toml`
is generated.** The client, its hand-written half, the README and the examples
are maintained in Barndoor's platform monorepo and pushed here by CI; this
repository is where the package is built, published and read by customers.

Two consequences for releasing:

- **Do not edit the version by hand.** It comes from `sdk/VERSION` in the
  monorepo. An edit here is overwritten by the next regeneration, and the
  version you published disappears.
- **There is no release branch.** Every push to `main` is a regeneration, and
  each one publishes a prerelease. A release is a tag and a GitHub Release on
  `main` as it already stands.

## How versions reach PyPI

| Channel | Trigger | Version | Installed by |
|---|---|---|---|
| prerelease | every push to `main` | `<version>.dev<UTC-YYYYMMDDHHMM>` | `pip install --pre barndoor` |
| release | a GitHub Release, by hand | `<version>` | `pip install barndoor` |

`pyproject.toml` always carries the **clean** version. The `.devN` segment is
stamped in the workflow at build time and never committed, so a release
publishes exactly what is in the tree.

PEP 440 is why this differs from the TypeScript SDK, which encodes the commit
sha. `2.0.0-dev.g1a2b3c4` is not a valid Python version, and PyPI rejects local
identifiers (`+g1a2b3c4`) outright — the sha cannot appear in the version at
all. A UTC timestamp is a valid `.devN`, sorts correctly, and does not reset the
way a run number does. Traceability lives in the commit message, which records
the monorepo commit that produced the tree.

Publishing authenticates via
[trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC). There is
no API token and nothing to rotate. The binding is configured on PyPI and is
scoped to this repository, the `release.yml` workflow, and the `release`
environment — so **renaming that workflow file breaks publishing** until the
binding is recreated. That is why both channels live in the one file.

## The version number

Set in `sdk/VERSION` in the monorepo. It is the version of the **API contract**,
independent of the Barndoor platform's own release version.

| Part | Driven by |
|---|---|
| MAJOR | a breaking API change |
| MINOR | an additive API change |
| PATCH | an SDK-only change |

`make check-api-version` in the monorepo compares the spec against its state at
the last bump and fails if the declared number is lower than the change
requires.

## Releasing

### 1. Make sure `main` here is what you want to ship

```bash
git checkout main && git pull origin main
python3 -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])"
```

That version is what will be published. If it is not the number you want, bump
`sdk/VERSION` in the monorepo, merge, and wait for the regeneration to arrive
here as a `chore: regenerate the SDK at X.Y.Z` commit.

Check the last push published cleanly: the most recent `Release` run on `main`
should be green, including its `Confirm the index serves it` step.

### 2. Tag it

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

### 3. Cut the GitHub Release

Choose that tag, title it `vX.Y.Z`, write the notes, mark it the latest release
and publish. That is what triggers the `publish` job.

### 4. Confirm it

The workflow polls PyPI until the version is served and fails if it never is —
a green publish step is not evidence the index serves anything. Then,
independently:

```bash
pip install barndoor==X.Y.Z
```

## Emergency rollback

PyPI versions cannot be replaced, only superseded, and a yank hides a release
without deleting it.

1. Fix the problem in the **monorepo** — that is where the source lives.
2. Bump `sdk/VERSION` (a PATCH, unless the fix changes the API).
3. Merge, let the regeneration land here, then tag and release.
4. Yank the bad version on PyPI so new installs skip it while existing pins
   keep resolving.

## Contributing changes

Not here. Pull requests against files this repository does not own cannot be
merged — the next regeneration overwrites them. The inputs live in the monorepo
under `sdk/python/`:

| To change | Edit |
|---|---|
| the API surface | the service that owns the endpoint; the spec is generated from it |
| auth, retries, MCP, the CLI | `sdk/python/barndoor/lib/` |
| the published README or examples | `sdk/python/README.md`, `sdk/python/examples/` |
| the version | `sdk/VERSION` |
| generation itself | `sdk/python/gen-config.yaml`, `sdk/python/templates/` |

Files this repository **does** own, and which no regeneration touches:
`.github/` (including the workflows), `.pre-commit-config.yaml`, `LICENSE`,
`CONTRIBUTING.md`, `SECURITY.md`, and this document.
