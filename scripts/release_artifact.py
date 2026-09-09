#!/usr/bin/env python3
"""Verify the wheel a release is about to publish, against the tag that names it.

The release run used to prove that a version pinned in a script matched a version written into
three source files matched the tag somebody pushed.  Every one of those facts is a property of the
source tree, and the pull request that put the tree on `main` had already proven the tree.  What it
never proved -- what it could not have proven, because the archive did not exist yet -- is anything
about the artifact.

So the subject moved.  The tag is the released identity (INV-099); this asks whether the thing
being shipped agrees with it, declares nothing at run time, and runs.

    python scripts/release_artifact.py --tag v1.4.0
    python scripts/release_artifact.py --tag v1.4.0 --dist dist --json

The clean-environment smoke test installs the wheel into a throwaway virtual environment built
with `--without-pip`-free `venv` and asks the installed command what version it is.  A wheel whose
metadata says one thing and whose code says another passes every check made of the source and
would still be wrong.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import venv
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "aart-cli"
DISTRIBUTION = "aart_cli"
_TAG_RE = re.compile(r"^v(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))$")
_FILENAME_RE = re.compile(rf"^{DISTRIBUTION}-(?P<version>[^-]+)-.+\.whl$")

# `(returncode, combined output)` for a command.  Injected so the checks can be tested for
# noticing a wrong answer without installing anything.
Runner = Callable[[tuple[str, ...]], "tuple[int, str]"]


class ArtifactError(RuntimeError):
    """The run cannot proceed: there is no artifact to check, or no released identity."""


@dataclass(frozen=True, order=True)
class ArtifactDiagnostic:
    check: str
    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"check": self.check, "code": self.code, "message": self.message}


def released_version(tag: str) -> str:
    """The version a release tag names.

    Stable `vX.Y.Z` only.  A prerelease tag is refused rather than accepted and stripped: the
    release engine cuts stable releases from `main`, and a tag shaped like something else means
    the pipeline is being run over something it was not built to publish.
    """

    match = _TAG_RE.fullmatch(tag)
    if match is None:
        raise ArtifactError(f"{tag!r} is not a release tag; expected vX.Y.Z")
    return match.group("version")


def wheel_in(directory: Path) -> Path:
    """The one wheel in `directory`.

    Exactly one, because "check the wheel" has no meaning over two of them: a stale archive left
    beside a fresh one makes the checks a coin toss, and the coin lands on whichever the
    filesystem lists first.
    """

    wheels = sorted(directory.glob("*.whl"))
    if not wheels:
        raise ArtifactError(f"no wheel was built in {directory}")
    if len(wheels) > 1:
        found = ", ".join(path.name for path in wheels)
        raise ArtifactError(f"expected exactly one wheel in {directory}, found: {found}")
    return wheels[0]


def _metadata(wheel: Path) -> list[str] | None:
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            return None
        return archive.read(names[0]).decode("utf-8").splitlines()


def _field(lines: Sequence[str], field: str) -> str | None:
    prefix = f"{field}:"
    for line in lines:
        if not line:  # the blank line ends the headers; the body may say anything.
            return None
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _diagnostic(code: str, message: str) -> ArtifactDiagnostic:
    return ArtifactDiagnostic("artifact", code, message)


def verify_artifact(wheel: Path, tag: str) -> tuple[ArtifactDiagnostic, ...]:
    """Everything the archive itself can be asked, without installing it."""

    version = released_version(tag)
    diagnostics: list[ArtifactDiagnostic] = []

    filename = _FILENAME_RE.fullmatch(wheel.name)
    if filename is None or filename.group("version") != version:
        diagnostics.append(
            _diagnostic(
                "artifact-filename-mismatch",
                f"{wheel.name} is not the wheel {tag} names",
            )
        )

    lines = _metadata(wheel)
    if lines is None:
        diagnostics.append(
            _diagnostic(
                "artifact-metadata-unreadable",
                "the wheel carries no single dist-info METADATA",
            )
        )
        return tuple(sorted(diagnostics))

    name = _field(lines, "Name")
    if name != PROJECT:
        diagnostics.append(
            _diagnostic("artifact-name-unexpected", f"the wheel names the project {name!r}")
        )
    declared = _field(lines, "Version")
    if declared != version:
        diagnostics.append(
            _diagnostic(
                "artifact-version-mismatch",
                f"{tag} names {version}; the wheel's metadata says {declared!r}",
            )
        )
    # Zero runtime dependencies is an architectural promise, and the archive is where it is kept
    # or broken.  A source tree with an empty `dependencies` list and a wheel that requires
    # something are both possible at once; only one of them is what a user installs.
    requires = [line for line in lines if line.startswith("Requires-Dist:")]
    if requires:
        listed = ", ".join(line.partition(":")[2].strip() for line in requires)
        diagnostics.append(
            _diagnostic("artifact-runtime-dependency", f"the wheel requires: {listed}")
        )
    return tuple(sorted(diagnostics))


def smoke(version: str, *, runner: Runner) -> tuple[ArtifactDiagnostic, ...]:
    """The installed command runs, and says it is the version that was released.

    The version is asked of the *program*, not of the metadata: they come from different places
    -- one from `pyproject.toml` at build time, one from the module the wheel carries -- so a
    build that packaged the wrong tree agrees with itself everywhere except here.
    """

    diagnostics: list[ArtifactDiagnostic] = []
    reported = runner(("aart", "--version"))
    if reported[0] != 0:
        diagnostics.append(
            _diagnostic("artifact-smoke-failed", f"`aart --version` failed: {reported[1].strip()}")
        )
    elif reported[1].strip() != f"{PROJECT} {version}":
        diagnostics.append(
            _diagnostic(
                "artifact-smoke-version",
                f"the installed command reports {reported[1].strip()!r}, not {version}",
            )
        )
    helped = runner(("aart", "--help"))
    if helped[0] != 0:
        diagnostics.append(
            _diagnostic("artifact-smoke-failed", f"`aart --help` failed: {helped[1].strip()}")
        )
    return tuple(sorted(diagnostics))


def _clean_environment_runner(wheel: Path, home: Path) -> Runner:
    """Install the wheel into a throwaway environment and run its commands from there.

    `--no-deps` and `--no-index`: the promise under test is that the wheel needs nothing, and an
    installer allowed to reach an index would quietly supply whatever it was missing.
    """

    environment = home / "env"
    venv.create(environment, with_pip=True, clear=True)
    binaries = environment / ("Scripts" if sys.platform == "win32" else "bin")
    python = binaries / ("python.exe" if sys.platform == "win32" else "python")
    subprocess.run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--disable-pip-version-check",
            str(wheel),
        ),
        check=True,
        capture_output=True,
    )

    def run(command: tuple[str, ...]) -> tuple[int, str]:
        executable = binaries / (f"{command[0]}.exe" if sys.platform == "win32" else command[0])
        finished = subprocess.run(
            (str(executable), *command[1:]), capture_output=True, text=True, timeout=120
        )
        return (finished.returncode, finished.stdout + finished.stderr)

    return run


def check_artifact(tag: str, dist: Path) -> dict[str, Any]:
    version = released_version(tag)
    wheel = wheel_in(dist)
    diagnostics = list(verify_artifact(wheel, tag))
    with tempfile.TemporaryDirectory() as raw:
        diagnostics.extend(smoke(version, runner=_clean_environment_runner(wheel, Path(raw))))
    return {
        "schema_version": 1,
        "status": "passed" if not diagnostics else "failed",
        "tag": tag,
        "version": version,
        "wheel": wheel.name,
        "diagnostics": [item.to_json() for item in sorted(diagnostics)],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="the release tag under inspection")
    parser.add_argument(
        "--dist", type=Path, default=ROOT / "dist", help="directory holding the built wheel"
    )
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        receipt = check_artifact(arguments.tag, arguments.dist)
    except (ArtifactError, OSError, subprocess.SubprocessError) as error:
        print(f"release artifact error: {error}", file=sys.stderr)
        return 2
    if arguments.json:
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    else:
        for diagnostic in receipt["diagnostics"]:
            print(f"{diagnostic['code']}: {diagnostic['message']}", file=sys.stderr)
        print(f"release artifact {receipt['status']}: {receipt['wheel']}")
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
