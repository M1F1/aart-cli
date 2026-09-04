#!/usr/bin/env python3
"""Fail-closed AART release checklist and schema-freeze generator."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
# The release series this checklist governs.  Its schema freeze is immutable: once issued, it is
# never regenerated or edited (D-154).  A new release series adds its own contract here and its
# own versioned documents beside the frozen ones.
#
# There is deliberately no `EXPECTED_VERSION` here any more.  It pinned a release by hand, and a
# checklist that refuses every version but the one somebody typed into a script is the manual
# bookkeeping INV-085 and INV-101 forbid.  The version now comes from one place, the release
# engine writes it, and this checklist reports it rather than ruling on it.
RELEASE_CONTRACT_VERSION = 18
_DECLARED_VERSION_RE = re.compile(r'(?m)^__version__\s*=\s*"([^"]+)"')
REFERENCE_REGISTRY_ORIGIN = "https://github.com/M1F1/agent-artifacts-registry"
SCHEMA_FREEZE_PATH = f"docs/release/schema-freeze-v{RELEASE_CONTRACT_VERSION}.json"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCHEMA_INPUTS = (
    "agent_artifacts/configuration/schema.py",
    "agent_artifacts/domain/outcomes.py",
    "agent_artifacts/install_state/schema.py",
    "agent_artifacts/protocol/capabilities.py",
    "agent_artifacts/protocol/native_models.py",
    "agent_artifacts/protocol/native_schema.py",
    "agent_artifacts/protocol/registry_models.py",
    "agent_artifacts/protocol/registry_schema.py",
    "agent_artifacts/reporting/schema.py",
    "agent_artifacts/security/analyzers.py",
    "agent_artifacts/security/attestation_schema.py",
    "agent_artifacts/security/schema.py",
    "agent_artifacts/setup.py",
    "docs/protocol/native-source-v1.md",
    "docs/protocol/registry-v1.md",
)
# Documents that must exist and say something.  They used to have to *name the release*, which
# meant every one of them was edited by hand at every release and the checklist was the thing that
# noticed when one was missed -- release bookkeeping wearing a checklist's clothes (INV-098).  The
# changelog is now written by the release engine and the release body with it, so what is left to
# check is that the contract's own documents are still here and still have content.
REQUIRED_RELEASE_DOCS = (
    "CHANGELOG.md",
    f"docs/release/compatibility-v{RELEASE_CONTRACT_VERSION}.md",
    f"docs/release/release-checklist-v{RELEASE_CONTRACT_VERSION}.md",
)
# Documents that stay shipped and referenced across release series.  They are still gated — a
# release must not silently drop the 0.1.x migration guide or the onboarding tutorials — but they
# describe an earlier boundary and are not expected to name the current version.
REQUIRED_PERSISTENT_DOCS = (
    "docs/release/migration-v1.md",
    "docs/tutorials/direct-source-v1.md",
    "docs/tutorials/company-registry-v1.md",
    "docs/tutorials/vendoring-v1.md",
)
RELEASE_CHECKS = (
    "repository",
    "schema-freeze",
    "system-matrix",
    "package",
    "registry-origin",
    "registry-format",
    "registry-validate",
    "registry-lock",
    "registry-build",
    "registry-audit",
    "registry-compatibility",
)
REGISTRY_CONTENT_CHECKS = RELEASE_CHECKS[5:]
PROTOCOL_VERSIONS = {
    "artifact_manifest": 1,
    "configuration": 1,
    "installation_state": 2,
    "native_source": 1,
    "registry": 1,
    "reporting": 1,
    "security_assessment": 1,
    # Raised for the 2.0.0 series: revision 1 is rejected at parse time rather than carried behind
    # a compatibility branch, so the single supported revision is the one recorded here.
    "setup_recipe": 2,
}

ProcessRunner = Callable[
    [tuple[str, ...], Path, Mapping[str, str], int], subprocess.CompletedProcess[str]
]


@dataclass(frozen=True, order=True)
class ReleaseDiagnostic:
    check: str
    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"check": self.check, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class RegistryEvidence:
    diagnostics: tuple[ReleaseDiagnostic, ...]
    commit: str | None
    content_checks_ran: bool


def declared_version(root: Path = ROOT) -> str:
    """What this tree says it is, read from the one file that says it.

    This is a report, not a ruling.  Nothing here compares it to a tag, to `pyproject.toml` or to
    a document: the release engine writes every place the version appears, so a disagreement is
    not a thing a human can cause and not a thing a checklist has to police.
    """

    text = (root / "agent_artifacts" / "__init__.py").read_text(encoding="utf-8")
    match = _DECLARED_VERSION_RE.search(text)
    if match is None:
        raise ValueError("agent_artifacts/__init__.py declares no __version__")
    return match.group(1)


def frozen_release_version(root: Path = ROOT) -> str:
    """The release the schema freeze was issued for, read back out of the freeze itself.

    An issued freeze is immutable (D-154), so the release it records is the freeze's own data --
    not a copy of a version that has to be kept in step with anything.  Reading it back is what
    lets `schema-freeze-stale` go on meaning exactly one thing: a normative schema moved.
    """

    document = json.loads((root / SCHEMA_FREEZE_PATH).read_text(encoding="utf-8"))
    return str(document["release_version"])


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def schema_freeze_bytes(root: Path = ROOT, *, release_version: str | None = None) -> bytes:
    inputs = [
        {"path": relative, "sha256": _sha256((root / relative).read_bytes())}
        for relative in SCHEMA_INPUTS
    ]
    document = {
        "protocol_versions": PROTOCOL_VERSIONS,
        "release_version": (
            frozen_release_version(root) if release_version is None else release_version
        ),
        "schema_inputs": inputs,
        "schema_version": 1,
    }
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_aart_release_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wheel_digest(root: Path = ROOT, *, output_dir: Path | None = None) -> tuple[str, str]:
    """Build this commit's wheel in a throwaway copy and return ``(filename, digest)``.

    The published wheel is dated from the commit it was built at, so its digest is a property of
    the tag and cannot be recorded inside the tag: writing it into a tracked file would change the
    commit that determines it.  This command is how the digest reaches the release evidence — run
    it at the tag and publish what it prints beside the artifact
    (``docs/release/wheel-reproducibility-v1.md``).

    ``output_dir`` receives that artifact, and the digest is then read back from the written file:
    what the caller is handed is the file the printed digest describes.  `LAF-75`: the wheel used
    to live in a temporary directory removed before this returned, which left the publisher to
    build a second wheel by another route and attach that one — a *different* file, because a
    build from the checkout carries no commit stamp.  `2.6.0` came within one ``curl`` of
    publishing a digest line that did not describe its own attachment.
    """

    inject = _script("inject_commit")
    packaging = _script("packaging_check")
    with tempfile.TemporaryDirectory(prefix="aart-wheel-digest-") as raw:
        temp_root = Path(raw)
        source_copy = temp_root / "source"
        source_copy.mkdir()
        packaging._copy_project(root, source_copy)
        # The copy has no ``.git``, so the stamp is taken from the real checkout and written in —
        # otherwise this would hash a wheel no release ever publishes.
        (source_copy / "agent_artifacts" / "_commit.py").write_text(
            inject.render(inject.current_commit(), inject.current_commit_epoch()),
            encoding="utf-8",
        )
        subprocess.run(
            [PYTHON, "scripts/build_wheel.py"],
            cwd=source_copy,
            check=True,
            capture_output=True,
        )
        built = tuple((source_copy / "dist").glob("aart_cli-*-py3-none-any.whl"))
        if len(built) != 1:
            raise ValueError(f"expected one built wheel, found {built}")
        if output_dir is None:
            return built[0].name, _sha256(built[0].read_bytes())
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / built[0].name
        shutil.copyfile(built[0], destination)
        # Hashed from the destination rather than from the source, so a copy that arrived short
        # cannot be described by the digest of the file it was copied from.
        return destination.name, _sha256(destination.read_bytes())


def _environment(cwd: Path) -> dict[str, str]:
    """The scrubbed environment every checklist subprocess runs in.

    System and global git config are switched off on purpose: release evidence must not depend on
    what happens to be configured on the machine that produced it.

    That also switches off the one setting a container needs.  `actions/checkout` writes the
    workspace as the runner's uid, a container job usually runs as another, and git then refuses
    every command in it with `detected dubious ownership` -- so a CI job would mark its own
    workspace safe with `git config --global`, and this process would not read it.  The result was
    two diagnostics at once, both saying a git command "could not prove" something, neither saying
    why.

    So the exception is stated here instead, through `GIT_CONFIG_COUNT` rather than a file: no
    configuration is read, one directory is trusted, and it is the directory this command runs in
    rather than a wildcard.
    """

    environment = {
        "PATH": os.environ.get("PATH", os.defpath),
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": str(cwd),
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }
    for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TMPDIR"):
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


def _run_process(
    command: tuple[str, ...],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=dict(environment),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _run(
    runner: ProcessRunner,
    command: tuple[str, ...],
    cwd: Path,
    timeout_seconds: int = 120,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return runner(command, cwd, _environment(cwd), timeout_seconds)
    except (OSError, subprocess.SubprocessError):
        return None


def _diagnostic(check: str, code: str, message: str) -> ReleaseDiagnostic:
    return ReleaseDiagnostic(check, code, message)


def _why(result: subprocess.CompletedProcess[str] | None) -> str:
    """What the command said, appended to a diagnostic that would otherwise only say it failed.

    "cannot prove the release worktree is clean" is true and useless.  Git had already explained
    itself on stderr and the explanation was dropped, so the log showed two checks failing for
    reasons it did not print.  Three separate failures on one Enterprise walk were diagnosed by
    guessing at a message that had already been produced.
    """

    if result is None:
        return "; the command could not be started"
    detail = (result.stderr or result.stdout or "").strip().splitlines()
    return f"; git said: {detail[0]}" if detail else ""


def _repository_diagnostics(
    root: Path,
    *,
    process_runner: ProcessRunner,
    require_clean: bool,
    require_main: bool,
) -> tuple[ReleaseDiagnostic, ...]:
    diagnostics: list[ReleaseDiagnostic] = []
    # The version is read, not ruled on.  What used to be here -- "the source must be exactly
    # stable 0.0.1", a sweep of the PROGRESS.md task ledger, and a demand that four documents each
    # contain the version string -- was three ways of asking a human to have remembered something.
    # The release engine remembers instead.
    try:
        declared_version(root)
    except (OSError, ValueError) as error:
        diagnostics.append(_diagnostic("repository", "version-invalid", str(error)))
    for relative in (*REQUIRED_RELEASE_DOCS, *REQUIRED_PERSISTENT_DOCS):
        try:
            carried = (root / relative).read_text(encoding="utf-8").strip()
        except OSError:
            carried = ""
        if not carried:
            diagnostics.append(
                _diagnostic(
                    "repository",
                    "release-doc-missing",
                    f"release document is missing or empty: {relative}",
                )
            )
    if require_clean:
        status = _run(
            process_runner,
            ("git", "status", "--porcelain=v1", "--untracked-files=all"),
            root,
            30,
        )
        if status is None or status.returncode != 0:
            diagnostics.append(
                _diagnostic(
                    "repository",
                    "repository-state-unavailable",
                    "cannot prove the release worktree is clean" + _why(status),
                )
            )
        elif status.stdout:
            diagnostics.append(
                _diagnostic(
                    "repository",
                    "repository-dirty",
                    "release worktree contains changed or generated output",
                )
            )
    if require_main:
        main_membership = _run(
            process_runner,
            ("git", "merge-base", "--is-ancestor", "HEAD", "origin/main"),
            root,
            30,
        )
        if main_membership is None or main_membership.returncode != 0:
            diagnostics.append(
                _diagnostic(
                    "repository",
                    "source-not-merged-into-main",
                    "release source commit is not proven to be merged into origin/main"
                    + _why(main_membership),
                )
            )
    return tuple(diagnostics)


def _schema_diagnostics(root: Path) -> tuple[ReleaseDiagnostic, ...]:
    try:
        expected = schema_freeze_bytes(root)
        actual = (root / SCHEMA_FREEZE_PATH).read_bytes()
    except OSError:
        return (
            _diagnostic(
                "schema-freeze",
                "schema-freeze-missing",
                "schema freeze or one of its declared inputs is missing",
            ),
        )
    if actual != expected:
        return (
            _diagnostic(
                "schema-freeze",
                "schema-freeze-stale",
                "schema freeze does not match the normative schema inputs",
            ),
        )
    return ()


def _tool_diagnostics(
    root: Path,
    process_runner: ProcessRunner,
) -> tuple[ReleaseDiagnostic, ...]:
    commands = (
        (
            "system-matrix",
            "system-matrix-failed",
            (PYTHON, "scripts/system_matrix.py", "--json"),
        ),
        (
            "package",
            "release-package-invalid",
            (PYTHON, "scripts/packaging_check.py"),
        ),
    )
    diagnostics: list[ReleaseDiagnostic] = []
    for check, code, command in commands:
        outcome = _run(process_runner, command, root, 180)
        if outcome is None or outcome.returncode != 0:
            diagnostics.append(_diagnostic(check, code, f"{check} release evidence did not pass"))
    return tuple(diagnostics)


def _normalize_origin(raw: str) -> str:
    return raw.strip().removesuffix(".git").removesuffix("/")


def approved_registry_origin() -> str:
    """The registry origin this checklist will accept, defaulting to this project's own.

    The release workflow already clones whatever `REFERENCE_REGISTRY_URL` names, because a fork
    publishes to its own registry and cannot reach this one.  Reading the same variable here is
    what makes that setting mean something: without it the workflow clones the fork's registry and
    this check rejects it as "not the approved public reference repository", which is a variable
    contradicted by a constant.

    The guard itself is unchanged.  On this repository the variable is unset, the default applies,
    and a release still reconciles against exactly one approved registry.  A fork states its own,
    and the registry it clones is then the registry it is checked against -- one value, not two
    that can disagree.
    """

    return _normalize_origin(os.environ.get("REFERENCE_REGISTRY_URL", "")) or (
        REFERENCE_REGISTRY_ORIGIN
    )


def _remote_head_commit(result: subprocess.CompletedProcess[str] | None) -> str | None:
    if result is None or result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == "HEAD" and GIT_SHA_RE.fullmatch(fields[0]):
            return fields[0]
    return None


def _registry_diagnostics(
    root: Path,
    registry: Path,
    process_runner: ProcessRunner,
    version: str,
) -> RegistryEvidence:
    if registry.is_symlink() or not registry.is_dir():
        return RegistryEvidence(
            (
                _diagnostic(
                    "registry-origin",
                    "registry-path-invalid",
                    "reference registry must be an existing real directory",
                ),
            ),
            None,
            False,
        )
    origin = _run(
        process_runner,
        ("git", "remote", "get-url", "origin"),
        registry,
        30,
    )
    if (
        origin is None
        or origin.returncode != 0
        or _normalize_origin(origin.stdout) != approved_registry_origin()
    ):
        return RegistryEvidence(
            (
                _diagnostic(
                    "registry-origin",
                    "registry-origin-invalid",
                    "reference registry origin is "
                    f"{_normalize_origin(origin.stdout) if origin else '(unreadable)'}, "
                    f"not the approved {approved_registry_origin()}; "
                    "set REFERENCE_REGISTRY_URL to the registry this release publishes to",
                ),
            ),
            None,
            False,
        )
    status = _run(
        process_runner,
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        registry,
        30,
    )
    if status is None or status.returncode != 0:
        return RegistryEvidence(
            (
                _diagnostic(
                    "registry-origin",
                    "registry-state-unavailable",
                    "cannot prove the reference registry worktree is clean" + _why(status),
                ),
            ),
            None,
            False,
        )
    if status.stdout:
        return RegistryEvidence(
            (
                _diagnostic(
                    "registry-origin",
                    "registry-dirty",
                    "reference registry contains changed or generated output",
                ),
            ),
            None,
            False,
        )
    head = _run(process_runner, ("git", "rev-parse", "HEAD"), registry, 30)
    origin_head = _run(process_runner, ("git", "rev-parse", "origin/HEAD"), registry, 30)
    advertised_head = _remote_head_commit(
        _run(process_runner, ("git", "ls-remote", "--symref", "origin", "HEAD"), registry, 30)
    )
    commit = head.stdout.strip() if head is not None and head.returncode == 0 else None
    expected_commit = (
        origin_head.stdout.strip()
        if origin_head is not None and origin_head.returncode == 0
        else None
    )
    if (
        commit is None
        or expected_commit is None
        or GIT_SHA_RE.fullmatch(commit) is None
        or commit != expected_commit
    ):
        return RegistryEvidence(
            (
                _diagnostic(
                    "registry-origin",
                    "registry-revision-not-current",
                    "reference registry HEAD is not the clean fetched origin/HEAD revision",
                ),
            ),
            commit if commit is not None and GIT_SHA_RE.fullmatch(commit) else None,
            False,
        )
    if advertised_head != commit:
        return RegistryEvidence(
            (
                _diagnostic(
                    "registry-origin",
                    "registry-remote-revision-mismatch",
                    "reference registry HEAD does not match the origin-advertised default revision",
                ),
            ),
            commit,
            False,
        )
    diagnostics: list[ReleaseDiagnostic] = []
    base = (PYTHON, "-m", "agent_artifacts", "registry")
    source = ("--source", str(registry), "--json")
    commands = (
        ("registry-format", "registry-format-stale", (*base, "format", *source, "--check")),
        (
            "registry-validate",
            "registry-incompatible",
            (*base, "validate", *source, "--strict", "--frozen"),
        ),
        ("registry-lock", "registry-lock-stale", (*base, "lock", *source, "--check")),
        ("registry-build", "registry-index-stale", (*base, "build", *source, "--check")),
        ("registry-audit", "registry-audit-failed", (*base, "audit", *source)),
        (
            "registry-compatibility",
            "registry-compatibility-failed",
            (
                *base,
                "test",
                *source,
                "--compatibility",
                "all",
                # The version under test is the one this tree declares, not one pinned in this
                # script: reconciling a registry against a release nobody is cutting proves
                # nothing about the release being cut.
                "--latest-version",
                version,
            ),
        ),
    )
    for check, code, command in commands:
        outcome = _run(process_runner, command, root, 180)
        if outcome is None or outcome.returncode != 0:
            diagnostics.append(_diagnostic(check, code, f"{check} release evidence did not pass"))
    final_status = _run(
        process_runner,
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        registry,
        30,
    )
    if final_status is None or final_status.returncode != 0:
        diagnostics.append(
            _diagnostic(
                "registry-origin",
                "registry-state-unavailable",
                "cannot prove the reference registry worktree stayed clean",
            )
        )
    elif final_status.stdout:
        diagnostics.append(
            _diagnostic(
                "registry-origin",
                "registry-dirty",
                "reference registry changed while release checks ran",
            )
        )
    final_head = _run(process_runner, ("git", "rev-parse", "HEAD"), registry, 30)
    final_origin_head = _run(process_runner, ("git", "rev-parse", "origin/HEAD"), registry, 30)
    final_advertised_head = _remote_head_commit(
        _run(process_runner, ("git", "ls-remote", "--symref", "origin", "HEAD"), registry, 30)
    )
    if (
        final_head is None
        or final_origin_head is None
        or final_head.returncode != 0
        or final_origin_head.returncode != 0
        or final_head.stdout.strip() != commit
        or final_origin_head.stdout.strip() != commit
        or final_advertised_head != commit
    ):
        diagnostics.append(
            _diagnostic(
                "registry-origin",
                "registry-revision-changed",
                "reference registry revision changed while release checks ran",
            )
        )
    return RegistryEvidence(tuple(diagnostics), commit, True)


def check_release(
    root: Path,
    registry: Path | None,
    *,
    process_runner: ProcessRunner = _run_process,
    require_clean: bool = True,
    require_main: bool = True,
) -> dict[str, Any]:
    before = _repository_diagnostics(
        root,
        process_runner=process_runner,
        require_clean=require_clean,
        require_main=require_main,
    )
    # Read once and carried, so a tree that cannot say what version it is is reported by the
    # `version-invalid` diagnostic above rather than by an exception out of a registry command.
    try:
        version = declared_version(root)
    except (OSError, ValueError):
        version = "unknown"
    # `registry is None` is the deliberate "this fork has no registry" case, not a missing
    # argument: the caller has to ask for it by name.  Reconciliation is then not performed, and
    # nothing pretends it was -- the seven registry checks report `skipped`, never `passed`.
    registry_evidence = (
        _registry_diagnostics(root, registry, process_runner, version)
        if registry is not None
        else RegistryEvidence((), None, False)
    )
    after = _repository_diagnostics(
        root,
        process_runner=process_runner,
        require_clean=require_clean,
        require_main=require_main,
    )
    diagnostics = tuple(
        sorted(
            set(
                (
                    *before,
                    *_schema_diagnostics(root),
                    *_tool_diagnostics(root, process_runner),
                    *registry_evidence.diagnostics,
                    *after,
                )
            )
        )
    )
    failed_checks = {item.check for item in diagnostics}
    skipped_checks: frozenset[str] = frozenset()
    if registry is None:
        skipped_checks = frozenset(("registry-origin", *REGISTRY_CONTENT_CHECKS))
    elif not registry_evidence.content_checks_ran:
        failed_checks.update(REGISTRY_CONTENT_CHECKS)
    return {
        "schema_version": 1,
        "status": "passed" if not diagnostics else "failed",
        "version": version,
        "registry_commit": registry_evidence.commit,
        "registry_reconciliation": "skipped" if registry is None else "performed",
        "checks": [
            {
                "name": name,
                "passed": name not in failed_checks and name not in skipped_checks,
                "skipped": name in skipped_checks,
            }
            for name in RELEASE_CHECKS
        ],
        "diagnostics": [item.to_json() for item in diagnostics],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="write exact schema-freeze evidence")
    freeze.add_argument("--write", action="store_true", help="required write acknowledgement")
    # An issued freeze records the release it was taken for and is never rewritten (D-154), so
    # regenerating one keeps the release it already names.  Only a freeze being issued for the
    # first time has one to state, and stating it is the point: it is evidence about a release,
    # not a mirror of a version somebody has to maintain.
    freeze.add_argument(
        "--release-version",
        default=None,
        help="the release this freeze is issued for (default: the one it already records)",
    )
    digest = commands.add_parser(
        "wheel-digest", help="build the wheel this commit publishes and print its digest"
    )
    digest.add_argument(
        "--output",
        type=Path,
        default=None,
        help="directory the wheel is written into (default: dist/)",
    )
    check = commands.add_parser("check", help="run the complete stable-release checklist")
    # Exactly one of the two, and `--without-registry` has to be typed.  A fork that publishes no
    # artifact catalogue has nothing to reconcile against, but "no registry" must be a statement
    # rather than an omission -- an optional `--registry` would let the reconciliation disappear
    # from a release by accident, which is the failure mode worth spending a flag to avoid.
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--registry", type=Path)
    source.add_argument(
        "--without-registry",
        action="store_true",
        help="reconcile against no registry; the seven registry checks report skipped",
    )
    check.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    args = _parser().parse_args(argv)
    if args.command == "freeze":
        if not args.write:
            print("release error: refusing to write schema freeze without --write", file=sys.stderr)
            return 1
        try:
            content = schema_freeze_bytes(root, release_version=args.release_version)
            destination = root / SCHEMA_FREEZE_PATH
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        except OSError as error:
            print(f"release error: cannot write schema freeze: {error}", file=sys.stderr)
            return 1
        print(f"schema freeze written: {SCHEMA_FREEZE_PATH}")
        return 0
    if args.command == "wheel-digest":
        output_dir = args.output if args.output is not None else root / "dist"
        try:
            name, digest = wheel_digest(root, output_dir=output_dir)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f"release error: cannot build the wheel to digest: {error}", file=sys.stderr)
            return 1
        print(f"{digest}  {name}")
        print(f"wrote {output_dir / name}")
        return 0
    receipt = check_release(root, None if args.without_registry else args.registry)
    if args.json:
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    else:
        if receipt["registry_reconciliation"] == "skipped":
            # Loud, on stderr, and every time.  A release that verified less than the last one is
            # worth one line now rather than a question in six months about why a regression got
            # through.
            print(
                "release warning: no registry was reconciled against, so seven checks did not "
                "run. This release proves the tool, not its agreement with an artifact catalogue.",
                file=sys.stderr,
            )
        for check in receipt["checks"]:
            if check["skipped"]:
                state = "skipped"
            else:
                state = "passed" if check["passed"] else "failed"
            print(f"{check['name']}: {state}")
        for diagnostic in receipt["diagnostics"]:
            print(f"{diagnostic['code']}: {diagnostic['message']}", file=sys.stderr)
        print(f"release checklist {receipt['status']}: {receipt['version']}")
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
