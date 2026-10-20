#!/usr/bin/env python3
"""Hermetic editable-to-wheel AART lifecycle smoke test.

The driver creates disposable Python environments, but keeps source snapshots, objects,
configuration, installation state, and harness targets in a separate shared tree.  Its phase
processes intentionally run outside the AART checkout and import only the installed distribution.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any


def _unwrap(result: Any) -> Any:
    from aart_cli.domain.result import Ok

    if not isinstance(result, Ok):
        raise RuntimeError(f"AART operation failed: {result!r}")
    return result.value


def _config_paths(home: Path):
    from aart_cli.configuration.paths import Platform, resolve_config_paths

    platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
    return resolve_config_paths(
        platform,
        home=str(home),
        application_home=os.environ.get("AART_CLI_HOME") or None,
    )


def _assert_installed_origin(
    expected: str,
    *,
    source_root: Path,
    environment_root: Path,
) -> int:
    import aart_cli

    package_file = Path(aart_cli.__file__).resolve()
    if expected == "editable":
        if not package_file.is_relative_to(source_root):
            raise RuntimeError(f"editable phase imported unexpected package: {package_file}")
    elif not package_file.is_relative_to(environment_root) or package_file.is_relative_to(
        source_root
    ):
        raise RuntimeError(f"wheel phase imported unexpected package: {package_file}")
    requirements = importlib.metadata.requires("aart-cli") or []
    runtime = tuple(item for item in requirements if "extra ==" not in item)
    if runtime:
        raise RuntimeError(f"installed distribution has runtime dependencies: {runtime}")
    return len(runtime)


def _configure_and_sync(registry_root: Path, home: Path) -> str:
    # A consumer reads only Registries (INV-269), so the smoke connects the reference content as
    # the approved local Registry `run_smoke` published, on the branch that publication committed.
    from aart_cli.application.configuration import ConfigDocument
    from aart_cli.configuration.model import (
        ConfiguredSource,
        SourceKind,
        SyncSettings,
        UserConfiguration,
    )
    from aart_cli.configuration.schema import user_configuration_bytes
    from aart_cli.domain.identifiers import SourceAlias
    from aart_cli.io.config_store import write_configuration
    from aart_cli.io.source_runtime import sync_configured_source

    source = ConfiguredSource(
        SourceAlias("reference"),
        SourceKind.REGISTRY_LOCAL,
        str(registry_root),
        _REGISTRY_BRANCH,
        True,
    )
    configuration = UserConfiguration(
        1,
        (source,),
        None,
        SyncSettings(),
    )
    paths = _config_paths(home)
    _unwrap(
        write_configuration(
            ConfigDocument(paths.user_config_file, user_configuration_bytes(configuration))
        )
    )
    outcome = _unwrap(sync_configured_source(source, data_root=paths.data_root))
    return outcome.disposition.value


#: The one artifact both phases install: a Skill the reference Registry offers to both profiles.
_ARTIFACT = "reference/skill/code-review"
#: The profile whose placed tree the smoke follows across environment removal.
_PLACED_PROFILE = "tabnine"


def _consume(project: Path, *argv: str) -> tuple[str, ...]:
    """Run one `consume` command through the installed distribution; return each item's status.

    The phase's own interpreter is the one under test, so this is the CLI a consumer of that
    environment would run, with nothing from the checkout on its path.
    """

    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "aart_cli.cli",
            "consume",
            *argv,
            "--project",
            str(project),
            "--json",
        ),
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError:
        document = None
    if (
        completed.returncode != 0
        or not isinstance(document, dict)
        or document.get("ok") is not True
    ):
        raise RuntimeError(
            f"consume {' '.join(argv)} failed ({completed.returncode}):\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return tuple(str(item["status"]) for item in document["items"])


def _installations(home: Path) -> tuple[Any, ...]:
    """Every installation the application home records, as the consumer runtime stores them."""

    from aart_cli.io.receipt_store import LocalReceiptStore

    return _unwrap(
        LocalReceiptStore(os.path.join(_config_paths(home).data_root, "state")).installations()
    )


def tree_digest(root: str) -> str | None:
    from aart_cli.io.runtime_projection import tree_digest_at

    digest = tree_digest_at(root)
    return None if digest is None else str(digest)


def _placed_receipt(project: Path, home: Path) -> tuple[str, str]:
    """The tree a copy install placed for the followed profile, and the digest its record attests.

    A Registry installation copies a verified object out of the application home, so what has to
    outlive the Python environment is that placed tree, still matching its installation record.
    """

    deliveries = tuple(
        delivery
        for record in _installations(home)
        if record.receipt.owner is not None and Path(record.receipt.owner.root) == project
        for delivery in record.receipt.deliveries
        if delivery.harness == _PLACED_PROFILE
    )
    if len(deliveries) != 1:
        raise RuntimeError(f"expected one {_PLACED_PROFILE} delivery, found {len(deliveries)}")
    destination = Path(deliveries[0].destination)
    if destination.is_symlink() or not destination.is_dir():
        raise RuntimeError(f"placed tree is not a directory: {destination}")
    digest = str(deliveries[0].digest)
    if tree_digest(str(destination)) != digest:
        raise RuntimeError(f"placed tree does not match its installation record: {destination}")
    return str(destination), digest


def _phase_seed(args: argparse.Namespace) -> dict[str, Any]:
    registry_root = Path(args.source_root).resolve()
    project = Path(args.project).resolve()
    home = Path(args.home).resolve()
    runtime_dependencies = _assert_installed_origin(
        args.expected_origin,
        source_root=Path(args.checkout).resolve(),
        environment_root=Path(args.environment_root).resolve(),
    )
    disposition = _configure_and_sync(registry_root, home)
    first = _consume(project, "install", _ARTIFACT, "--profile", "claude", "--yes")
    second = _consume(project, "install", _ARTIFACT, "--profile", _PLACED_PROFILE, "--yes")
    destination, digest = _placed_receipt(project, home)
    return {
        "registry_sync": disposition,
        "initial_install": sum(status == "completed" for status in first),
        "second_profile_install": sum(status == "completed" for status in second),
        "runtime_dependencies": runtime_dependencies,
        "placed_destination": destination,
        "placed_digest": digest,
    }


def _phase_resume(args: argparse.Namespace) -> dict[str, Any]:
    project = Path(args.project).resolve()
    home = Path(args.home).resolve()
    runtime_dependencies = _assert_installed_origin(
        args.expected_origin,
        source_root=Path(args.checkout).resolve(),
        environment_root=Path(args.environment_root).resolve(),
    )
    profiles = f"claude,{_PLACED_PROFILE}"
    current = _consume(project, "status", _ARTIFACT, "--profile", profiles)
    removed = _consume(project, "uninstall", _ARTIFACT, "--profile", profiles, "--yes")
    reinstalled = _consume(project, "install", _ARTIFACT, "--profile", _PLACED_PROFILE, "--yes")
    destination, digest = _placed_receipt(project, home)
    return {
        "resumed_current": sum(status == "current" for status in current),
        "removed": sum(status == "removed" for status in removed),
        "reinstalled": sum(status == "completed" for status in reinstalled),
        "runtime_dependencies": runtime_dependencies,
        "placed_destination": destination,
        "placed_digest": digest,
    }


def _run(
    argv: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {argv!r}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def _environment_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _environment_script(root: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return root / ("Scripts" if os.name == "nt" else "bin") / f"{name}{suffix}"


def _make_environment(root: Path) -> Path:
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(root)
    python = _environment_python(root)
    if not python.is_file():
        raise RuntimeError(f"virtual environment Python is missing: {python}")
    return python


def _has_module(python: Path, module: str, environment: dict[str, str]) -> bool:
    probe = subprocess.run(
        [str(python), "-c", f"import {module}"],
        capture_output=True,
        env=environment,
    )
    return probe.returncode == 0


# `[build-system] build-backend` is `poetry.core.masonry.api`; this is the package that
# provides it, and the name both the presence check and the lending look for.
_BUILD_BACKEND_MODULE = "poetry.core"


def _lend_build_backend(workspace: Path) -> Path:
    """A directory holding just the build backend, for interpreters whose venv has none.

    The editable install below runs with ``--no-index --no-build-isolation``: it is a proof that
    the project installs with no index reachable, so pip has nowhere to fetch a backend from and
    the backend has to be on the path already. A fresh venv never has one -- ``ensurepip`` stopped
    bundling setuptools in Python 3.12, and it never bundled poetry-core -- and the failure is a
    hundred lines of pip traceback ending in ``Cannot import 'poetry.core.masonry.api'``, which
    never says that the build backend is the missing thing.

    The dev group names ``poetry-core`` at the version ``[build-system]`` pins, for exactly this,
    so this process has one to lend. Only the backend is lent: a directory of links, not the whole
    environment, so nothing else -- least of all an editable ``aart_cli`` from the
    developer's own environment -- can leak in and make the install look like it worked when it
    did not.
    """

    spec = importlib.util.find_spec(_BUILD_BACKEND_MODULE)
    if spec is None or spec.origin is None:
        raise RuntimeError(
            "no poetry-core to build an editable install with, in this environment or the new "
            "one.\nInstall the developer tools first:  poetry install --with dev"
        )
    # `poetry/core/__init__.py` -> `poetry/core` -> `poetry` -> site-packages.
    site_packages = Path(spec.origin).resolve().parent.parent.parent
    lent = workspace / "build-backend"
    lent.mkdir()
    for name in ("poetry",):
        source = site_packages / name
        if source.exists():
            (lent / name).symlink_to(source)
    for pattern in ("poetry_core-*.dist-info",):
        for metadata in site_packages.glob(pattern):
            (lent / metadata.name).symlink_to(metadata)
    return lent


def _load_packaging_check(source_root: Path):
    path = source_root / "scripts" / "packaging_check.py"
    spec = importlib.util.spec_from_file_location("_aart_distribution_packaging", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load packaging helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_local_wheel(source_root: Path, workspace: Path) -> Path:
    packaging = _load_packaging_check(source_root)
    source_copy = workspace / "build-source"
    wheel_dir = workspace / "wheel"
    source_copy.mkdir()
    wheel_dir.mkdir()
    packaging._copy_project(source_root, source_copy)
    packaging._build_wheel(source_copy, wheel_dir)
    wheels = tuple(wheel_dir.glob("aart_cli-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one local wheel, found {wheels}")
    packaging._validate_wheel(wheels[0], workspace / "wheel-inspection")
    return wheels[0]


def _phase_command(
    python: Path,
    script: Path,
    phase: str,
    *,
    source: Path,
    project: Path,
    home: Path,
    checkout: Path,
    environment_root: Path,
    expected_origin: str,
) -> list[str]:
    return [
        str(python),
        str(script),
        "--phase",
        phase,
        "--source-root",
        str(source),
        "--project",
        str(project),
        "--home",
        str(home),
        "--checkout",
        str(checkout),
        "--environment-root",
        str(environment_root),
        "--expected-origin",
        expected_origin,
    ]


def _parse_phase(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"distribution phase did not return JSON: {completed.stdout!r}"
        ) from error
    if not isinstance(value, dict):
        raise RuntimeError("distribution phase receipt must be an object")
    return value


def _survives_environment_removal(environment: Path, destination: str, digest: str) -> bool:
    shutil.rmtree(environment)
    return Path(destination).is_dir() and tree_digest(destination) == digest


#: The branch the reference Registry commits its approved content to.
_REGISTRY_BRANCH = "main"


def _publish_reference_registry(checkout: Path, registry: Path) -> None:
    """Promote the shared reference content into an approved Registry checkout at `registry`.

    Only the orchestrator runs this, from the checkout under test; the phases read the committed
    Registry through the installed distribution and never import the test tree.
    """

    if str(checkout) not in sys.path:
        sys.path.insert(0, str(checkout))
    from tests.reference_registry import BRANCH, write_reference_registry

    if BRANCH != _REGISTRY_BRANCH:
        raise RuntimeError(f"reference Registry commits to {BRANCH}, not {_REGISTRY_BRANCH}")
    write_reference_registry(registry)


def run_smoke(source_root: Path) -> dict[str, Any]:
    """Run the complete local distribution lifecycle and return a stable receipt."""

    source_root = source_root.resolve()
    script = source_root / "scripts" / "distribution_smoke.py"
    with tempfile.TemporaryDirectory(prefix="aart-distribution-") as raw:
        workspace = Path(raw).resolve()
        outside = workspace / "outside-checkout"
        project = workspace / "consumer-project"
        home = workspace / "user-home"
        source = workspace / "registry"
        editable_environment = workspace / "editable-environment"
        wheel_environment = workspace / "wheel-environment"
        for directory in (outside, project, home):
            directory.mkdir()
        _publish_reference_registry(source_root, source)
        wheel = _build_local_wheel(source_root, workspace)
        environment = os.environ.copy()
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        environment.update(
            {
                "HOME": str(home),
                "AART_CLI_HOME": str(workspace / "aart-cli-home"),
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_INDEX": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )

        editable_python = _make_environment(editable_environment)
        build_environment = dict(environment)
        if not _has_module(editable_python, _BUILD_BACKEND_MODULE, environment):
            build_environment["PYTHONPATH"] = str(_lend_build_backend(workspace))
        _run(
            [
                str(editable_python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--editable",
                str(source_root),
            ],
            cwd=outside,
            environment=build_environment,
        )
        _run(
            [str(_environment_script(editable_environment, "aart-cli")), "--version"],
            cwd=outside,
            environment=environment,
        )
        seed = _parse_phase(
            _run(
                _phase_command(
                    editable_python,
                    script,
                    "seed",
                    source=source,
                    project=project,
                    home=home,
                    checkout=source_root,
                    environment_root=editable_environment,
                    expected_origin="editable",
                ),
                cwd=outside,
                environment=environment,
            )
        )
        survived_editable = _survives_environment_removal(
            editable_environment,
            seed["placed_destination"],
            seed["placed_digest"],
        )

        wheel_python = _make_environment(wheel_environment)
        _run(
            [
                str(wheel_python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            cwd=outside,
            environment=environment,
        )
        aart = _environment_script(wheel_environment, "aart-cli")
        _run([str(aart), "--version"], cwd=outside, environment=environment)
        upgrade = _run(
            [str(aart), "upgrade", "--wheel", str(wheel), "--dry-run"],
            cwd=outside,
            environment=environment,
        )
        upgrade_dry_run = (
            "--no-index" in upgrade.stdout
            and "--no-deps" in upgrade.stdout
            and str(wheel) in upgrade.stdout
            and "pypi" not in upgrade.stdout.casefold()
        )
        resumed = _parse_phase(
            _run(
                _phase_command(
                    wheel_python,
                    script,
                    "resume",
                    source=source,
                    project=project,
                    home=home,
                    checkout=source_root,
                    environment_root=wheel_environment,
                    expected_origin="wheel",
                ),
                cwd=outside,
                environment=environment,
            )
        )
        survived_wheel = _survives_environment_removal(
            wheel_environment,
            resumed["placed_destination"],
            resumed["placed_digest"],
        )
        if seed["runtime_dependencies"] != resumed["runtime_dependencies"]:
            raise RuntimeError("editable and wheel dependency metadata disagree")
        return {
            "schema_version": 1,
            "registry_sync": seed["registry_sync"],
            "initial_install": seed["initial_install"],
            "second_profile_install": seed["second_profile_install"],
            "resumed_current": resumed["resumed_current"],
            "removed": resumed["removed"],
            "reinstalled": resumed["reinstalled"],
            "survived_editable_removal": survived_editable,
            "survived_wheel_removal": survived_wheel,
            "runtime_dependencies": seed["runtime_dependencies"],
            "upgrade_dry_run": upgrade_dry_run,
            "placed_destination": resumed["placed_destination"],
            "placed_digest": resumed["placed_digest"],
            "editable_environment": str(editable_environment),
            "wheel_environment": str(wheel_environment),
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("seed", "resume"))
    parser.add_argument("--source-root")
    parser.add_argument("--project")
    parser.add_argument("--home")
    parser.add_argument("--checkout")
    parser.add_argument("--environment-root")
    parser.add_argument("--expected-origin", choices=("editable", "wheel"))
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.phase is None:
        receipt = run_smoke(Path(__file__).resolve().parent.parent)
    else:
        required = (
            args.source_root,
            args.project,
            args.home,
            args.checkout,
            args.environment_root,
            args.expected_origin,
        )
        if any(value is None for value in required):
            raise SystemExit("phase mode requires all path and origin arguments")
        receipt = _phase_seed(args) if args.phase == "seed" else _phase_resume(args)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --- The documented install routes, executed ----------------------------------------------------

_INSTALL_DOCUMENT = "docs/install/installing-aart-v1.md"
_SHELL_BLOCK = re.compile(r"```sh\n(.*?)```", re.S)
#: Routes whose line can be run here. The rest name an address or a project that does not exist.
_RUNNABLE = ("clipboard", "disk", "authenticated-download")


def documented_commands(source_root: Path) -> tuple[str, ...]:
    """Every fenced shell block in the install document, verbatim and in order."""

    text = (Path(source_root) / _INSTALL_DOCUMENT).read_text(encoding="utf-8")
    return tuple(match.group(1).strip() for match in _SHELL_BLOCK.finditer(text))


def classify_command(command: str) -> str:
    """Which route a documented line belongs to, or `unclassified`.

    `unclassified` is not a failure mode of this function -- it is the answer for a line nobody has
    said anything about, and the gate fails on it. A line added to the page then has to be declared
    runnable or declared unrunnable, which is the question its author is in the best position to
    answer and the last moment anyone will be asked.
    """

    # Before the placeholder check: this line carries `<repository>` too, and reaching that check
    # first would quietly declare the one executable download route unrunnable.
    if "gh release download" in command:
        return "authenticated-download"
    if "<repository>" in command:
        return "network"
    if command.startswith("cd /path/to/"):
        return "consumer-example"
    if "scripts/install_commands.py" in command:
        return "generator"
    if "$(pbpaste)" in command:
        return "clipboard"
    # It moves an installation that already exists, so a fresh environment has nothing to upgrade.
    if command.startswith("aart-cli upgrade "):
        return "upgrade"
    if "./aart_cli-X.Y.Z-py3-none-any.whl" in command:
        return "disk"
    return "unclassified"


def installer_of(command: str) -> str:
    for installer in ("python -m pip", "pipx", "uv", "gh"):
        if command.startswith(installer):
            return installer
    return command.split(maxsplit=1)[0]


def _stand_ins(directory: Path, wheel: Path) -> Path:
    """`pbpaste` and `gh`, close enough to fail on a line the real ones would reject.

    The clipboard reader prints the path the reader would have copied. `gh` parses its arguments
    the way `gh release download` does and refuses anything else, so the documented flags are what
    is under test rather than this stub's tolerance; what it cannot prove is that GitHub answers,
    which is why the route is named for the download and not for the release.
    """

    directory.mkdir(parents=True, exist_ok=True)
    clipboard = directory / "pbpaste"
    clipboard.write_text(f'#!/bin/sh\nprintf %s "{wheel}"\n', encoding="utf-8")
    clipboard.chmod(0o755)
    stub = directory / "gh"
    stub.write_text(
        "\n".join(
            (
                "#!/usr/bin/env python3",
                "import argparse, glob, shutil, sys",
                "from pathlib import Path",
                "parser = argparse.ArgumentParser(prog='gh')",
                "group = parser.add_subparsers(dest='group', required=True)",
                "action = group.add_parser('release').add_subparsers(dest='action', required=True)",
                "download = action.add_parser('download')",
                "download.add_argument('tag')",
                # Required, because the real `gh` has nowhere else to learn the repository from:
                # without it, it reads the git remotes of the current directory, and this section
                # is the one for a reader who has no clone.
                "download.add_argument('--repo', required=True)",
                "download.add_argument('--pattern', required=True)",
                "download.add_argument('--dir', required=True)",
                "parsed = parser.parse_args()",
                f"assets = glob.glob({str(wheel.parent)!r} + '/' + parsed.pattern)",
                "if not assets:",
                "    sys.exit('no asset matched ' + parsed.pattern)",
                "Path(parsed.dir).mkdir(parents=True, exist_ok=True)",
                "shutil.copy(assets[0], Path(parsed.dir) / Path(assets[0]).name)",
                "",
            )
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return directory


def _installed_executable(roots: tuple[Path, ...]) -> Path | None:
    for root in roots:
        candidate = root / "aart-cli"
        if candidate.is_file():
            return candidate
    return None


def _run_route(command: str, *, workspace: Path, index: int, wheel: Path) -> dict[str, Any]:
    """One documented line, in its own environment, with the developer's tools out of reach.

    `UV_TOOL_DIR`, `PIPX_HOME` and their bin directories are redirected into the workspace. Without
    that, running this gate would reinstall the developer's own `aart-cli` from a throwaway wheel --
    a gate that damages the machine it runs on is worse than the drift it was written to catch.
    """

    root = workspace / f"route-{index}"
    environment = root / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    bin_directory = _environment_python(environment).parent
    uv_bin, pipx_bin = root / "uv-bin", root / "pipx-bin"
    stand_ins = _stand_ins(root / "stand-ins", wheel)
    downloads = root / "downloads"
    downloads.mkdir()
    shutil.copy(wheel, downloads / wheel.name)

    env = dict(os.environ)
    env.update(
        PATH=os.pathsep.join((str(bin_directory), str(stand_ins), env.get("PATH", ""))),
        UV_TOOL_DIR=str(root / "uv-tools"),
        UV_TOOL_BIN_DIR=str(uv_bin),
        PIPX_HOME=str(root / "pipx"),
        PIPX_BIN_DIR=str(pipx_bin),
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    env.pop("VIRTUAL_ENV", None)

    completed = subprocess.run(
        command,
        shell=True,
        cwd=downloads,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"documented install line failed: {command}\n{completed.stdout}{completed.stderr}"
        )
    if classify_command(command) == "authenticated-download":
        landed = tuple(downloads.glob(wheel.name))
        if not landed:
            raise RuntimeError(f"documented download left no wheel behind: {command}")
        return {"version": None}
    executable = _installed_executable((bin_directory, uv_bin, pipx_bin))
    if executable is None:
        raise RuntimeError(f"documented install line installed no `aart-cli`: {command}")
    version = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True, timeout=120, check=True
    )
    return {"version": version.stdout.strip().split()[-1]}


def run_install_routes(source_root: Path) -> dict[str, Any]:
    """Execute the install document's runnable lines and return a stable receipt."""

    source_root = Path(source_root).resolve()
    commands = documented_commands(source_root)
    with tempfile.TemporaryDirectory(prefix="aart-install-routes-") as raw:
        workspace = Path(raw)
        wheel = _build_local_wheel(source_root, workspace)
        version = wheel.name.split("-")[1]

        generated = subprocess.run(
            [sys.executable, "scripts/install_commands.py"],
            cwd=source_root,
            capture_output=True,
            text=True,
            timeout=120,
        )

        executed: list[dict[str, Any]] = []
        declined: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []
        unclassified: list[str] = []
        for index, command in enumerate(commands):
            route = classify_command(command)
            if route == "unclassified":
                unclassified.append(command)
                continue
            if route == "generator":
                # Run separately, before the routes, because its output is what the release body
                # carries rather than something a reader installs from.
                declined.append({"command": command, "route": route})
                continue
            if route not in _RUNNABLE:
                declined.append({"command": command, "route": route})
                continue
            installer = installer_of(command)
            # pip belongs to the isolated venv and gh is supplied by _stand_ins. Only optional
            # real installers depend on what the host has on PATH.
            if installer not in ("python -m pip", "gh") and shutil.which(installer) is None:
                unavailable.append({"command": command, "route": route, "installer": installer})
                continue
            outcome = _run_route(
                command.replace("X.Y.Z", version),
                workspace=workspace,
                index=index,
                wheel=wheel,
            )
            executed.append(
                {
                    "command": command,
                    "route": route,
                    "installer": installer,
                    "version": outcome["version"] or version,
                }
            )

    return {
        "schema_version": 1,
        "version": version,
        "wheel": wheel.name,
        "documented": len(commands),
        "executed": tuple(executed),
        "declined": tuple(declined),
        "unavailable": tuple(unavailable),
        "unclassified": tuple(unclassified),
        "generator_ran": generated.returncode == 0,
        "generated_lines": generated.stdout,
    }
