"""What a first run connects when the build carried a default Registry (CP-27, D-373).

Every rule here is a rule about when *not* to act, which is why the decision is pure and separate
from the transaction that carries it out. A build may bake one Registry so that a person in an
organization that already decided on one does not have to be asked for it. That is a convenience,
so it must not be able to overrule a choice, and it must not be able to stop the tool starting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aart_cli.configuration.model import ConfiguredSource, SourceKind, git_location_parts
from aart_cli.configuration.seed import SeededRegistry
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Result

from .configuration import LoadedConfiguration

#: The branch a seeded Registry is tracked at. The variable carries an alias and a URL and no ref,
#: and this is the value configuration already reads when a source entry names none
#: (`configuration/schema.py`), so the seed agrees with a hand-written `config.json` rather than
#: introducing a second answer.
SEED_REF = "main"

SEED_UNUSABLE = DiagnosticCode("default-registry-unusable")


@dataclass(frozen=True, slots=True)
class FirstRunSeed:
    """One Registry this run will connect, and what it will say about having done so."""

    source: ConfiguredSource
    make_default: bool
    announcement: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FirstRunSeedOutcome:
    """Either a Registry to connect, or nothing and the reason, which is never an error."""

    seed: FirstRunSeed | None
    diagnostics: tuple[Diagnostic, ...]


def plan_first_run_seed(
    loaded: LoadedConfiguration,
    baked: Result[SeededRegistry | None],
) -> FirstRunSeedOutcome:
    """Decide whether this run connects the Registry its build carried.

    Three refusals, in order of how much they matter.

    A run that is not a first run is left alone, and so is a configuration that already names a
    source -- including a local one, because connecting a Registry on this machine is a choice too
    and an upgrade does not get to add to it. The second check is not implied by the first: a
    caller holding a `LoadedConfiguration` assembled some other way should not be able to seed over
    somebody's sources by passing the wrong flag.

    A value that cannot be used produces a warning and no seed. It is never an error, because the
    run it would fail is the first one, which is the one moment a person has no configuration to
    fall back on -- and the screen it falls back to, asking for a Registry, is exactly what the
    product did before any of this existed.
    """

    if loaded.first_run is None or loaded.user_configuration.sources:
        return FirstRunSeedOutcome(None, ())
    if isinstance(baked, Err):
        return FirstRunSeedOutcome(None, (_unusable(baked),))
    seeded = baked.value
    if seeded is None:
        return FirstRunSeedOutcome(None, ())
    source = ConfiguredSource(seeded.alias, SourceKind.REGISTRY_GIT, seeded.url, SEED_REF, True)
    return FirstRunSeedOutcome(
        FirstRunSeed(
            source,
            True,
            (
                f"Connected the Registry this build was configured with: "
                f"{seeded.alias.value} ({seeded.url}).",
                "You did not choose it; open Registries to change or remove it.",
            ),
        ),
        (),
    )


def _unusable(refused: Err) -> Diagnostic:
    """Carry every reason forward as one warning.

    `Err` cannot be constructed empty, so there is always something to say, and it is said once:
    the screen this lands on exists to tell a new person what to do next, and a list of parser
    complaints is not that.
    """

    reasons = "; ".join(diagnostic.message for diagnostic in refused.diagnostics)
    return Diagnostic(
        SEED_UNUSABLE,
        Severity.WARNING,
        f"this build names a default Registry that cannot be used: {reasons}",
        remediation=("open Registries and choose Add Registry to connect one yourself",),
    )


#: What Git says when it holds no credential for an HTTPS host and may not ask for one
#: (`credential.interactive=never`), or when the host refused the one it had.
_NO_CREDENTIAL = re.compile(
    r"unable to get password|could not read (?:username|password)|authentication failed"
    r"|returned error: 40[13]\b",
    re.IGNORECASE,
)
_NO_SSH_KEY = re.compile(r"permission denied \(publickey", re.IGNORECASE)


def unconnected_seed(source: ConfiguredSource, reasons: tuple[str, ...]) -> Diagnostic:
    """Why the baked Registry could not be connected, and what a person does next (B-268, D-515).

    Git's own error names the mirror's remote, `origin`, never the URL, so the Registry is named
    here; the URL carries no credential, since the build refused one (`configuration/seed.py`).
    Git is never allowed to prompt, so a host it holds no credential for fails the same way on
    every run, and the one useful answer is how to give Git one. Any other refusal is not answered
    with a sign-in, because signing in would not change it.
    """

    url = source.location
    parts = git_location_parts(url)
    host = parts[0] if parts is not None else ""
    said = "; ".join(reasons)
    # Each entry is one complete option, its commands indented under it: `Diagnostic` keeps
    # remediation sorted, so an entry may not lean on the one before it.
    remediation = [
        f"Check that Git can read it:\n    git -c credential.interactive=never ls-remote {url} HEAD",
        "Or connect it yourself:\n    aart-cli consume registry add "
        f"--alias {source.alias.value} --kind git --location {url} --default",
        "Or open Registries and choose Add Registry.",
    ]
    if host and url.startswith("https://") and _NO_CREDENTIAL.search(said):
        remediation.append(
            f"Git has no credential for {host}. Sign in and let Git use it, then rerun:\n"
            f"    gh auth login --hostname {host}\n"
            f"    gh auth setup-git --hostname {host}"
        )
    elif host and _NO_SSH_KEY.search(said):
        remediation.append(f"Git has no SSH key {host} accepts. Add one, then rerun.")
    return Diagnostic(
        SEED_UNUSABLE,
        Severity.WARNING,
        f"this build names a default Registry that could not be connected: "
        f"{source.alias.value} ({url}): {said}",
        remediation=tuple(remediation),
    )


__all__ = [
    "SEED_REF",
    "SEED_UNUSABLE",
    "FirstRunSeed",
    "FirstRunSeedOutcome",
    "plan_first_run_seed",
    "unconnected_seed",
]
