"""Connect the Registry this build was configured with, once, on a first run (CP-27, D-373).

The decision is `application/first_run_seed`; this is the transaction that carries it out. It
carries it out through `source add`'s own path rather than a second one: organization policy, the
snapshot acquisition and the atomic compare-and-swap write all apply to a seeded Registry exactly
as they apply to one a person typed in, and a second path is how one of them would come to be
missing from the other.

Nothing here returns an error. Every failure is somebody's *first* run failing, and the state it
falls back to -- asking for a Registry -- is what the product did before any of this existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from aart_cli.application.first_run_seed import (
    SEED_UNUSABLE,
    FirstRunSeedOutcome,
    plan_first_run_seed,
)
from aart_cli.configuration.seed import SeededRegistry, baked_default_registry
from aart_cli.domain.diagnostics import Diagnostic, Severity
from aart_cli.domain.result import Err, Result
from aart_cli.model import Request

from ._configured_runtime import ConfiguredRuntime, load_runtime_configuration
from .source import AddedConfiguredSource, add_configured_source

LoadRuntime = Callable[[Request], Result[ConfiguredRuntime]]
AddSource = Callable[[Request], Result[AddedConfiguredSource]]
ReadBaked = Callable[[], Result[SeededRegistry | None]]


@dataclass(frozen=True, slots=True)
class FirstRunSeedReport:
    """What the first run connected, what it will say, and why it did nothing when it did not."""

    connected: AddedConfiguredSource | None
    lines: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]


def _report(outcome: FirstRunSeedOutcome) -> FirstRunSeedReport:
    return FirstRunSeedReport(None, (), outcome.diagnostics)


def connect_baked_default_registry(
    request: Request,
    *,
    load: LoadRuntime = lambda request: load_runtime_configuration(request, content_required=False),
    add: AddSource = add_configured_source,
    read_baked: ReadBaked = baked_default_registry,
) -> FirstRunSeedReport:
    """Connect the baked Registry if this run is the first one and nothing is configured.

    The seams are arguments because the decision this wraps is worth testing without a machine
    underneath it, and because the transaction it delegates to is the one `source add` runs -- a
    copy of that transaction here would be the thing that drifts.
    """

    runtime = load(request)
    if isinstance(runtime, Err):
        # A configuration that will not load is a problem the run is about to report properly.
        # Seeding on top of it would replace that report with a second, less informative one.
        return FirstRunSeedReport(None, (), ())
    outcome = plan_first_run_seed(runtime.value.loaded, read_baked())
    if outcome.seed is None:
        return _report(outcome)
    seed = outcome.seed
    added = add(
        Request(
            command="source",
            source_action="add",
            source_alias=seed.source.alias.value,
            source_kind=seed.source.kind.value,
            source_location=seed.source.location,
            ref=seed.source.ref,
            source_make_default=seed.make_default,
            user_home=request.user_home,
            yes=True,
        )
    )
    if isinstance(added, Err):
        # The transaction writes atomically, so a refusal here has left nothing behind -- which is
        # the reason it is delegated to rather than reimplemented.
        return FirstRunSeedReport(
            None,
            (),
            (
                Diagnostic(
                    SEED_UNUSABLE,
                    Severity.WARNING,
                    "this build names a default Registry that could not be connected: "
                    + "; ".join(diagnostic.message for diagnostic in added.diagnostics),
                    remediation=(
                        "open Registries and choose Add Registry to connect one yourself",
                    ),
                ),
            ),
        )
    return FirstRunSeedReport(added.value, seed.announcement, ())


__all__ = ["FirstRunSeedReport", "connect_baked_default_registry"]
