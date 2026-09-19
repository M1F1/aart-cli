# Wheel reproducibility

`aart_cli-<version>-py3-none-any.whl` is **byte-reproducible**: rebuilding the tagged commit
anywhere produces an archive with the same sha256 digest, not merely the same contents.

This is a standing promise, held by a test rather than by intent
(`tests/packaging_test.py::ReproducibleWheelTest`). Every later packaging change has to keep it.

## What is pinned

Poetry builds the wheel. `scripts/build_wheel.py` is the one place that invokes it, because
`poetry build` on its own does not hold this promise, and it is the script that closes each gap.

- **Member dates** are one constant, `2016-01-01`, which poetry-core writes into every member.
  They come from neither the clock nor the commit, so two commits an hour apart differ only where
  their content differs.
- **`SOURCE_DATE_EPOCH` is removed from the environment before Poetry runs.** poetry-core honours
  it, and a digest an environment variable can move is a digest nobody can check: the publisher and
  the verifier would have to have set it the same way, and neither would know that they had to.
- **The builder's version is part of the archive.** `WHEEL` records
  `Generator: poetry-core <version>`, so an upgrade changes the digest of an unchanged commit.
  It is pinned exactly in `[build-system]`, installed at that same version by the dev group, and
  checked against the built file afterwards — so upgrading Poetry fails a build rather than
  quietly invalidating every digest already published.
- **Compression** is deflate; **create-system** is Unix, so a build on Windows cannot change the
  header.
- **Contents** are checked against the resource allowlist twice: once over the source before
  Poetry runs, and once over the archive Poetry produced. A stray file under `aart_cli/`
  fails the build instead of shipping inside it.

Member order is Poetry's. It is stable, which is what byte-reproducibility needs.

`tests/packaging_test.py::ReproducibleWheelTest` holds all of this, including a test that sets
`SOURCE_DATE_EPOCH` and asserts the bytes do not move.

## Building it needs Poetry

Besides git and an interpreter, a CI image that builds the wheel must carry Poetry. An image that keeps Poetry off `PATH` names it in the `AART_POETRY`
repository variable — `/opt/poetry/bin/poetry` is the usual place.

Poetry is needed for the *build* only. The quality gates install their tools with pip, from the
exact versions `poetry.lock` pins, because Poetry cannot install from a per-fork internal index:
it takes an install source only from a `[[tool.poetry.source]]` block inside `pyproject.toml`,
adding that block at run time changes the file's hash, and `poetry install` then refuses the lock.
`scripts/dev_tools.py` carries the lock's pins to pip, which reads `PIP_INDEX_URL` and always could.

## Verifying a published wheel

```sh
git checkout v<version>
make wheel
shasum -a 256 dist/aart_cli-<version>-py3-none-any.whl
```

Compare that digest with the one published beside the release artifact. `make wheel` runs
`scripts/inject_commit.py` first, which stamps the commit being verified into the source. The stamp
does not date the archive, but it is content, so it is part of the digest.

The verifier needs the pinned Poetry. Any other version builds a wheel whose `WHEEL` file names it,
and `scripts/build_wheel.py` refuses that build rather than printing a digest that will not match.

## Where the digest is published

The digest is a property of the tagged commit, so it cannot live inside it: writing it into a
tracked file would change the commit that determines it. It is produced at the tag, beside the
release artifact, rather than committed to this repository.

```sh
python scripts/release.py wheel-digest
```

The command builds the wheel this commit publishes in a throwaway copy — stamping `HEAD` exactly as
`make wheel` would — writes it into `dist/`, and prints two lines:

```
sha256:<hex>  aart_cli-<version>-py3-none-any.whl
wrote dist/aart_cli-<version>-py3-none-any.whl
```

The digest is read back from the file after it is written, so the first line describes the second.
`--output <dir>` writes it somewhere else instead.

`python scripts/build_wheel.py` alone builds a *different* file: the checkout carries no commit
stamp, so `aart_cli/_commit.py` differs and the digest does not match the release.
