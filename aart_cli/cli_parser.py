"""The argument parser: every command, flag and choice this executable accepts.

Split out of `cli` so a probe can ask the shipped parser whether a recorded command is valid
without importing the dispatcher. `cli` reaches every command module, and the commands reach the
probes, so a probe that imported `cli` closed an import cycle (B-186).
"""

from __future__ import annotations

import argparse

from . import __version__
from .curation.model import DEFAULT_MAXIMUM_AART, DEFAULT_MINIMUM_AART
from .protocol.authoring import AUTHORED_KINDS

_ARTIFACT_TYPES = ("skill", "guideline", "mcp", "hook", "memory")
_INSTALL_SCOPES = ("project", "user")
_HELP_FORMATTER = argparse.RawDescriptionHelpFormatter


# --------------------------------------------------------------------------- #
# Parser construction                                                          #
# --------------------------------------------------------------------------- #
def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _add_profile(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--profile",
        action="append",
        metavar="P[,P...]",
        help="target harness profile(s); comma-separated or repeated",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the full argparse parser for the public command surface."""
    parser = argparse.ArgumentParser(
        prog="aart-cli",
        formatter_class=_HELP_FORMATTER,
        description="Install a team's AI artifacts (skills, guidelines, MCP configs, hooks) "
        "into agentic harnesses.",
    )
    parser.add_argument("--version", action="version", version=f"aart-cli {__version__}")

    def _add_project(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--project",
            metavar="DIR",
            help="project-scope consumer directory (default: current dir)",
        )

    def _add_scope(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--scope",
            choices=_INSTALL_SCOPES,
            default="project",
            help="target Project or User configuration/state (default: project)",
        )

    def _add_source(p: argparse.ArgumentParser, help_text: str) -> None:
        p.add_argument("--source", dest="source_dir", metavar="DIR", help=help_text)

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser(
        "reset",
        formatter_class=_HELP_FORMATTER,
        help="start aart-cli clean, keeping the old state in a backup",
        description=(
            "Move AART-owned per-user configuration, managed snapshots, receipts, settings and "
            "caches into <application home>-backups/<UTC timestamp>/ and start as on a new "
            "machine. Nothing is deleted. Projects, harness files, organization policy and "
            "credentials owned by other applications are not touched."
        ),
    )
    p.add_argument(
        "--restore",
        dest="reset_restore",
        metavar="DIR",
        help="bring a backup back, after backing up the current state",
    )
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation")

    # doctor ------------------------------------------------------------------ #
    p = sub.add_parser(
        "doctor",
        formatter_class=_HELP_FORMATTER,
        help="report installed health, offline readiness, activity, credentials and configuration",
        description=(
            "Inspect the installed environment and report it in one place: measured drift with the "
            "smallest policy-permitted reconciliation plans; offline readiness for each enabled "
            "source, as metadata, canonical payload and runtime dependencies separately; any "
            "working copy an interrupted run left behind; the recorded activity trail and what "
            "each action can undo; credential health and which installations depend on it; and the "
            "configuration this machine is ignoring, meaning disabled sources and fields your "
            "organization's policy has locked. On its own the report changes nothing. With "
            "--repair, review one exact installed artifact's plan; applying it requires both --yes "
            "and the prior review's --expect digest. This command never reinstalls everything."
        ),
    )
    p.add_argument(
        "--repair",
        dest="names",
        nargs=1,
        metavar="COORDINATE",
        help="review one installed artifact's minimal repair plan",
    )
    _add_scope(p)
    p.add_argument(
        "--yes",
        action="store_true",
        help="apply the selected repair; requires --expect from a prior review",
    )
    p.add_argument(
        "--expect",
        metavar="DIGEST",
        help="review digest returned by the prior --repair review",
    )
    _add_project(p)
    _add_json(p)

    # upgrade ----------------------------------------------------------------- #
    p = sub.add_parser(
        "upgrade",
        help="reinstall AART from one explicit local wheel or checkout",
        description=(
            "Replace this AART executable from one reviewed local input. "
            "AART never discovers an index or source repository implicitly."
        ),
    )
    upgrade_source = p.add_mutually_exclusive_group(required=True)
    upgrade_source.add_argument(
        "--wheel",
        dest="upgrade_wheel",
        metavar="FILE",
        help="install an exact local aart_cli wheel without an index",
    )
    upgrade_source.add_argument(
        "--source-checkout",
        dest="upgrade_source_checkout",
        metavar="DIR",
        help="reinstall editable from an exact local AART checkout without an index",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the pip invocation; install nothing"
    )

    # consume / maintain ------------------------------------------------------ #
    # Three role families (§175.2, INV-270): the first word says whose command it is.
    p = sub.add_parser(
        "consume",
        formatter_class=_HELP_FORMATTER,
        help="connect Registries and install, update and inspect their artifacts",
        description=(
            "Everything a consumer does: connect Registries, synchronize them, and install, update, "
            "inspect, set up and test the artifacts they approve. A consumer reads Registries "
            "only; an Upstream repository is the maintainer's."
        ),
    )
    consume_sub = p.add_subparsers(dest="consume_action", metavar="ACTION", required=True)
    p = sub.add_parser(
        "maintain",
        formatter_class=_HELP_FORMATTER,
        help="keep a Registry: its Upstream repositories, Candidates and published versions",
        description=(
            "Everything a Registry maintainer does: connect the Upstream repositories authors "
            "keep, discover and promote their Candidates, and validate and publish the Registry."
        ),
    )
    maintain_sub = p.add_subparsers(dest="maintain_action", metavar="ACTION", required=True)

    def _add_connection_family(family_sub: argparse._SubParsersAction, noun: str) -> None:
        """`add|list|sync|remove|resubscribe|health` for Registries or Upstream repositories."""

        p_add_source = family_sub.add_parser(
            "add",
            help=f"synchronize, validate, then connect one {noun}",
            description=(
                f"Parse one exact {noun}, validate a fresh immutable snapshot, then atomically "
                "save it to the configuration. No interactive confirmation is required because "
                "every origin choice is an explicit command argument."
            ),
        )
        p_add_source.add_argument(
            "--alias",
            dest="source_alias",
            required=True,
            metavar="ALIAS",
            help=f"{noun} alias slug",
        )
        p_add_source.add_argument(
            "--kind",
            dest="source_kind",
            choices=("git", "local"),
            required=True,
            help="git (a remote Git URL) or local (a repository on this machine)",
        )
        p_add_source.add_argument(
            "--location",
            dest="source_location",
            required=True,
            metavar="URL_OR_PATH",
            help="credential-free Git URL, or a normalized absolute local path",
        )
        p_add_source.add_argument(
            "--ref",
            metavar="REF",
            help=(
                "Git ref: defaults to main for git; for a local Registry the branch to read, "
                "required; not valid for a local upstream"
            ),
        )
        if noun != "Registry":
            _add_json(p_add_source)
        else:
            source_default = p_add_source.add_mutually_exclusive_group()
            source_default.add_argument(
                "--default",
                dest="source_make_default",
                action="store_const",
                const=True,
                help="make this the default Registry",
            )
            source_default.add_argument(
                "--no-default",
                dest="source_make_default",
                action="store_const",
                const=False,
                help="preserve the current default Registry",
            )
            _add_json(p_add_source)

        p_source_list = family_sub.add_parser(
            "list",
            help=f"show connected {noun} entries and managed snapshot health",
            description=(
                f"List every {noun} this machine is connected to, with its alias, location, "
                "whether it is the default, and the health of its managed snapshot. This reads "
                "local state only; it fetches nothing and changes nothing."
            ),
        )
        _add_json(p_source_list)

        def _add_alias(p: argparse.ArgumentParser, help_text: str) -> None:
            p.add_argument("--alias", dest="source_alias", metavar="ALIAS", help=help_text)

        p_source_sync = family_sub.add_parser(
            "sync",
            formatter_class=_HELP_FORMATTER,
            help=f"refresh the managed snapshot of each connected {noun}",
            description=(
                f"Re-synchronize already-connected {noun} entries. This never adds, renames, "
                "removes or re-identifies one, and never changes policy defaults - use it "
                "instead of re-adding an existing alias."
                + (
                    " Afterwards it says which installed artifacts have a newer approved version; "
                    "`aart-cli consume update` applies them."
                    if noun == "Registry"
                    else ""
                )
            ),
        )
        _add_alias(p_source_sync, "synchronize only this alias (default: every enabled one)")
        _add_json(p_source_sync)

        p_source_remove = family_sub.add_parser(
            "remove",
            formatter_class=_HELP_FORMATTER,
            help=f"forget one connected {noun} and delete its managed snapshot",
            description=(
                "Drop the configuration entry, clear the default Registry if it named this alias, "
                "and delete the managed snapshot so the origin is free to be added again. No "
                "installed artifact and no file in any project is touched."
            ),
        )
        p_source_remove.add_argument(
            "--alias",
            dest="source_alias",
            required=True,
            metavar="ALIAS",
            help=f"connected {noun} alias to remove",
        )
        p_source_remove.add_argument(
            "--yes",
            action="store_true",
            help="finalize the reviewed removal (without this the command only reviews)",
        )
        _add_json(p_source_remove)

        p_source_resubscribe = family_sub.add_parser(
            "resubscribe",
            formatter_class=_HELP_FORMATTER,
            help="adopt a changed declared identity at an unchanged origin and ref",
            description=(
                "Adopt the identity an already-configured origin now declares, keeping the alias, "
                "kind, location, ref, and default-registry flag. Without --yes it prints both "
                "identities and changes nothing; --yes adopts exactly the reviewed transition and "
                "refuses if the origin moved again in between. Use `sync` when the identity did "
                "not change."
            ),
        )
        p_source_resubscribe.add_argument(
            "--alias",
            dest="source_alias",
            required=True,
            metavar="ALIAS",
            help=f"connected {noun} alias whose declared identity changed",
        )
        p_source_resubscribe.add_argument(
            "--yes",
            action="store_true",
            help="adopt the reviewed identity change (without this the command only reviews)",
        )
        p_source_resubscribe.add_argument(
            "--expect",
            metavar="FROM:TO",
            help=(
                "adopt only this exact identity change, written as the two declared IDs; "
                "otherwise refuse and show the transition that is actually offered"
            ),
        )
        _add_json(p_source_resubscribe)

        p_source_health = family_sub.add_parser(
            "health",
            formatter_class=_HELP_FORMATTER,
            help=f"report managed snapshot health for each connected {noun}",
            description=(
                "Read-only health: pointer presence, resolved revision, and snapshot age against "
                "the configured freshness window. Exits non-zero if an enabled one is not healthy."
            ),
        )
        _add_alias(p_source_health, "report only this alias (default: every connected one)")
        _add_json(p_source_health)

    p = consume_sub.add_parser(
        "registry",
        formatter_class=_HELP_FORMATTER,
        help="connect, synchronize and inspect the Registries this machine installs from",
        description=(
            "Connect a Registry, synchronize what it offers, and see which installed artifacts "
            "have a newer approved version. `registry add` validates and snapshots the exact "
            "Registry before saving it, so it is safe for non-interactive agent use."
        ),
    )
    _add_connection_family(
        p.add_subparsers(dest="source_action", metavar="ACTION", required=True), "Registry"
    )
    p = maintain_sub.add_parser(
        "upstream",
        formatter_class=_HELP_FORMATTER,
        help="connect the Upstream repositories authors keep, and discover their Candidates",
        description=(
            "An Upstream repository is a repository its authors keep, from which this Registry "
            "takes artifacts. Connect one, synchronize it to discover Candidates, scan an explicit "
            "checkout, or adopt and check manifests by URL."
        ),
    )
    upstream_sub = p.add_subparsers(dest="source_action", metavar="ACTION", required=True)
    _add_connection_family(upstream_sub, "upstream")
    p = maintain_sub.add_parser(
        "candidate",
        formatter_class=_HELP_FORMATTER,
        help="review and promote the Candidates upstreams offer",
        description=(
            "A Candidate is an artifact an Upstream repository offers that this Registry has not "
            "approved yet. List the Candidates the connected Upstream repositories recorded, and "
            "promote exact ones into the Registry after review."
        ),
    )
    candidate_sub = p.add_subparsers(dest="candidate_action", metavar="ACTION", required=True)

    # marketplace ------------------------------------------------------------- #
    # The Marketplace actions are the consumer family itself: `consume install`, `consume list`.
    marketplace_sub = consume_sub
    p_marketplace_list = marketplace_sub.add_parser(
        "list",
        help="emit all canonical marketplace sources and artifacts",
        description=(
            "Print every connected Registry and every artifact it offers, from the managed "
            "snapshots on this machine. On a large catalog, `consume search` finds one artifact "
            "without reading the whole list. This reads only; run `consume registry sync` to "
            "refresh the snapshots first."
        ),
    )
    _add_json(p_marketplace_list)

    p_marketplace_search = marketplace_sub.add_parser(
        "search",
        formatter_class=_HELP_FORMATTER,
        help="find marketplace artifacts by name, coordinate, or summary",
        description=(
            "Match every word given against each artifact's name, coordinate, summary, authors, "
            "licence, and collection members, and print what matches all of them, best first. "
            "Matching is plain case-insensitive substring: looking for `code-review` finds it "
            "from `review`. A second word narrows the answer rather than widening it."
        ),
    )
    p_marketplace_search.add_argument(
        "query",
        nargs="+",
        metavar="WORD",
        help="word(s) to look for; an artifact must match all of them",
    )
    p_marketplace_search.add_argument(
        "--limit",
        dest="search_limit",
        type=int,
        metavar="N",
        help="print at most N matches (the best N, not the first N)",
    )
    _add_json(p_marketplace_search)

    p_marketplace_health = marketplace_sub.add_parser(
        "health",
        formatter_class=_HELP_FORMATTER,
        help="compare advisory artifact requirements with a repository runtime inventory",
        description=(
            "Read advisory per-artifact runtime requirements and compare them with an explicit "
            "JSON environment description supplied by the consuming repository. AART does not "
            "probe or install runtimes, and health results never block artifact installation."
        ),
    )
    p_marketplace_health.add_argument(
        "names",
        nargs="*",
        metavar="COORDINATE",
        help=(
            "artifact or collection coordinate(s) to inspect; omit to inspect every marketplace "
            "artifact"
        ),
    )
    p_marketplace_health.add_argument(
        "--environment",
        dest="runtime_environment",
        required=True,
        metavar="PATH",
        help="repository-owned runtime environment description in JSON format",
    )
    _add_project(p_marketplace_health)
    _add_json(p_marketplace_health)

    def _add_lifecycle(
        action: str,
        help_text: str,
        *,
        coordinates: str,
        prune: bool = False,
    ) -> argparse.ArgumentParser:
        """Declare one canonical lifecycle action over configured sources.

        Every mutating flag is opt-in: without ``--yes`` the command stops at Review.
        """

        lifecycle = marketplace_sub.add_parser(
            action,
            formatter_class=_HELP_FORMATTER,
            help=help_text,
            description=(
                f"{help_text.capitalize()}. Artifacts are addressed as "
                "<source>/<kind>/<name>[@<version>] and collections as "
                "<source>/collection/<name>; an unqualified <kind>/<name> is accepted only when "
                "exactly one configured source provides it. Without --yes the command prints the "
                "reviewed plan and exits without changing anything."
            ),
        )
        lifecycle.add_argument(
            "names",
            nargs="*",
            metavar="COORDINATE",
            help=coordinates,
        )
        _add_profile(lifecycle)
        _add_project(lifecycle)
        _add_scope(lifecycle)
        lifecycle.add_argument(
            "--offline",
            action="store_true",
            help="use last-known-good snapshots and cached objects only",
        )
        lifecycle.add_argument(
            "--force",
            action="store_true",
            help="authorize overwrites and merge-entry collisions",
        )
        if prune:
            lifecycle.add_argument(
                "--prune",
                action="store_true",
                help="remove installed entries no longer in the selection",
            )
        lifecycle.add_argument(
            "--yes",
            action="store_true",
            help="finalize the reviewed plan (without this the command only reviews)",
        )
        lifecycle.add_argument(
            "--expect",
            metavar="DIGEST",
            help=(
                "finalize only if the recomputed review digest equals DIGEST; otherwise refuse "
                "and show the new review"
            ),
        )
        _add_json(lifecycle)
        return lifecycle

    p_marketplace_install = _add_lifecycle(
        "install",
        "install configured-source artifacts for the selected harness profiles",
        coordinates="artifact or collection coordinate(s) to install",
    )
    p_marketplace_update = _add_lifecycle(
        "update",
        "update installed artifacts against their configured sources",
        coordinates="artifact or collection coordinate(s) to update; omit for all installed",
        prune=True,
    )
    _add_lifecycle(
        "uninstall",
        "remove installed artifacts recorded for the selected profiles",
        coordinates="artifact or collection coordinate(s) to remove",
    )
    _add_lifecycle(
        "status",
        "report installed artifact state against the configured sources",
        coordinates="artifact or collection coordinate(s) to inspect; omit for all installed",
    )
    p_marketplace_setup = _add_lifecycle(
        "setup",
        "run declared post-install setup for installed artifacts",
        coordinates="artifact or collection coordinate(s) whose setup should run",
    )

    def _add_setup_controls(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--authorize-untrusted-source",
            action="store_true",
            help="authorize setup declared by a source that is not company-reviewed",
        )
        parser.add_argument(
            "--authorize-custom-entrypoint",
            action="store_true",
            help="authorize a setup recipe that declares a non-standard entrypoint",
        )
        parser.add_argument(
            "--approve-setup-effects",
            action="store_true",
            help="approve every reviewed setup effect; without it each effect is declined",
        )

    for setup_capable in (p_marketplace_install, p_marketplace_update, p_marketplace_setup):
        _add_setup_controls(setup_capable)

    # installed MCP verification --------------------------------------------- #
    p = consume_sub.add_parser(
        "mcp",
        formatter_class=_HELP_FORMATTER,
        help="verify declared read-only operations of already installed MCPs",
        description=(
            "Test already installed MCPs in one explicit local scope. The command never installs, "
            "updates, repairs, configures, synchronizes or publishes content."
        ),
    )
    mcp_sub = p.add_subparsers(dest="mcp_action", metavar="ACTION", required=True)
    p_mcp_test = mcp_sub.add_parser(
        "test",
        formatter_class=_HELP_FORMATTER,
        help="run each installation's declared smoke operation and report both stages",
        description=(
            "For each installed MCP named, or every one with --all, check its installation "
            "configuration, then start it and make the one read-only call its manifest declares. "
            "Missing credentials or AART_NOT_SET values stop at NOT CONFIGURED and the server is "
            "never started. A PASS does not prove the call reached the external service. Exits "
            "non-zero unless every installation passes."
        ),
    )
    p_mcp_test.add_argument(
        "names",
        nargs="*",
        metavar="INSTALLED",
        help="installed MCP coordinate(s) to test; use --all instead to test every one",
    )
    p_mcp_test.add_argument(
        "--all",
        dest="all_installed",
        action="store_true",
        help="test every installed MCP in the selected scope and harnesses",
    )
    p_mcp_test.add_argument(
        "--harness",
        dest="profile",
        action="append",
        required=True,
        metavar="NAME[,NAME...]",
        help="installed harness target(s): opencode, tabnine or claude",
    )
    p_mcp_test.add_argument(
        "--show-response",
        action="store_true",
        help="show a bounded current MCP response; it may contain confidential service data",
    )
    _add_scope(p_mcp_test)
    _add_project(p_mcp_test)
    _add_json(p_mcp_test)

    # `receipt` lives under `marketplace` rather than under a top-level `setup` group, because
    # `marketplace setup` already owns that word: a second `aart setup` would name two different
    # operations.  A receipt is a read over one installation, which is this family's subject.
    p_marketplace_receipt = marketplace_sub.add_parser(
        "receipt",
        formatter_class=_HELP_FORMATTER,
        help="read what a setup run recorded for one installation",
        description=(
            "Read the persisted setup record AART writes for every setup run: plan hash, "
            "timings, exit status, and each step with its module, target and disposition. "
            "This is a read; it starts no run and locks nothing."
        ),
    )
    receipt_sub = p_marketplace_receipt.add_subparsers(
        dest="receipt_action", metavar="ACTION", required=True
    )
    p_receipt_show = receipt_sub.add_parser(
        "show",
        help="print the persisted setup record for one installed artifact",
        description=(
            "Print the setup record of one installed artifact as it was written: plan hash, "
            "installer hash, timings, exit status, and one receipt per step with its module, "
            "target and disposition. It asks the machine nothing; `receipt verify` does that."
        ),
    )
    p_receipt_show.add_argument(
        "names",
        nargs=1,
        metavar="COORDINATE",
        help="the installed artifact coordinate whose setup record should be printed",
    )
    _add_profile(p_receipt_show)
    _add_project(p_receipt_show)
    _add_scope(p_receipt_show)
    _add_json(p_receipt_show)

    p_receipt_verify = receipt_sub.add_parser(
        "verify",
        formatter_class=_HELP_FORMATTER,
        help="ask whether what the setup record claims is still true",
        description=(
            "Put each claim in a persisted setup record to the machine: does the image still "
            "exist, does the tag still resolve to the recorded id, does the Keychain item hold a "
            "value, is the managed block still in the file. Reports and never repairs; exits "
            "non-zero when any claim is false."
        ),
    )
    p_receipt_verify.add_argument(
        "names",
        nargs=1,
        metavar="COORDINATE",
        help="the installed artifact coordinate whose setup record should be checked",
    )
    _add_profile(p_receipt_verify)
    _add_project(p_receipt_verify)
    _add_scope(p_receipt_verify)
    _add_json(p_receipt_verify)

    p_receipt_undo = receipt_sub.add_parser(
        "undo",
        formatter_class=_HELP_FORMATTER,
        help="reverse the effects a setup run recorded",
        description=(
            "Replay a persisted setup receipt in reverse, with the ownership checks the run "
            "itself uses. The only mutating action in this family: without --yes it prints "
            "every effect it would reverse and every effect it would not, and changes nothing."
        ),
    )
    p_receipt_undo.add_argument(
        "names",
        nargs=1,
        metavar="COORDINATE",
        help="the installed artifact coordinate whose setup effects should be reversed",
    )
    _add_profile(p_receipt_undo)
    _add_project(p_receipt_undo)
    _add_scope(p_receipt_undo)
    p_receipt_undo.add_argument(
        "--yes",
        action="store_true",
        help="apply the reviewed undo (without this the command only reviews)",
    )
    p_receipt_undo.add_argument(
        "--expect",
        metavar="DIGEST",
        help=(
            "apply only if the recomputed undo digest equals DIGEST; otherwise refuse and show "
            "the undo that is actually offered"
        ),
    )
    _add_json(p_receipt_undo)

    # registry ---------------------------------------------------------------- #
    p = maintain_sub.add_parser(
        "registry",
        formatter_class=_HELP_FORMATTER,
        help="initialize, compile, and audit an AART registry",
        description=(
            "Maintain a writable AART registry checkout. Read/check commands never mutate it; "
            "mutation commands write only reviewed managed files. The explicit publish action "
            "also commits every listed Git change and never pushes. "
            "An artifact's requires resolves inside this one registry, against artifacts this "
            "registry owns: depend on foreign content by publishing it here, never by naming "
            "another registry's artifact."
        ),
    )
    registry_sub = p.add_subparsers(dest="registry_action", metavar="ACTION", required=True)

    def _add_registry_source(target: argparse.ArgumentParser) -> None:
        _add_source(target, "registry checkout or read-only registry snapshot")

    def _add_check(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--check",
            action="store_true",
            help="report drift without writing; return non-zero when generated files differ",
        )

    def _add_registry_finalize(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--yes",
            action="store_true",
            help="finalize the reviewed registry mutation (without this only review)",
        )

    p_init = registry_sub.add_parser(
        "init",
        help="initialize a canonical registry checkout",
        description=(
            "Turn a local Git checkout into an AART Registry: protocol markers, `.aart-cli-version`, "
            "a README and the registry CI workflows. Without --yes this only reviews the files it "
            "would write; a file that already exists with different content is refused, never "
            "replaced."
        ),
    )
    _add_registry_source(p_init)
    p_init.add_argument(
        "--source-id", required=True, metavar="SLUG", help="stable registry/source identity"
    )
    p_init.add_argument(
        "--display-name", required=True, metavar="TEXT", help="human-readable registry name"
    )
    p_init.add_argument(
        # A registry initialised today cannot honestly claim an older AART can read it: the
        # scaffolded markers, manifests, and setup recipes are the current dialect.  The floor is
        # therefore the AART that wrote them, and an author who really supports more says so.
        "--minimum-version",
        default=DEFAULT_MINIMUM_AART,
        metavar="VERSION",
        help=f"minimum supported AART version (default: {DEFAULT_MINIMUM_AART})",
    )
    p_init.add_argument(
        # The ceiling is the next major after the running release, not a literal: a literal
        # ceiling collides with the floor above once AART reaches it.  Both bounds come from the
        # one place that derives them, so a skin cannot drift from the boundary.
        "--maximum-version",
        default=DEFAULT_MAXIMUM_AART,
        metavar="VERSION",
        help=f"exclusive maximum AART version (default: {DEFAULT_MAXIMUM_AART})",
    )
    _add_registry_finalize(p_init)
    _add_json(p_init)

    p_collection = registry_sub.add_parser(
        "collection",
        help="define or change a Collection of artifacts this registry approved",
        description=(
            "Write a Collection: a named set of artifacts this Registry already approved, each "
            "pinned at its highest approved version. A new Collection needs --summary. Without "
            "--yes this only reviews the change."
        ),
    )
    _add_registry_source(p_collection)
    p_collection.add_argument(
        "names", nargs=1, metavar="NAME", help="the Collection name, as a lowercase slug"
    )
    p_collection.add_argument(
        "--summary",
        metavar="TEXT",
        help="one-line Collection description (required for a new Collection)",
    )
    p_collection.add_argument(
        "--include",
        action="append",
        required=True,
        dest="collection_members",
        metavar="KIND/NAME",
        help="approved artifact, pinned at its highest approved version (repeatable)",
    )
    _add_registry_finalize(p_collection)
    _add_json(p_collection)

    p_scan = upstream_sub.add_parser(
        "scan",
        help="discover native Candidates in one pinned author checkout",
        description=(
            "Read a clean Git author checkout at its exact HEAD, compile only explicit aart-cli.json "
            "or aart-cli.yaml manifests, and report Candidate state. Upstream scan never changes the "
            "target registry and never promotes a Candidate."
        ),
    )
    _add_registry_source(p_scan)
    p_scan.add_argument(
        "--checkout",
        required=True,
        dest="candidate_checkout",
        metavar="DIR",
        help="clean local Git checkout of the author source",
    )
    p_scan.add_argument(
        "--source-alias",
        required=True,
        dest="candidate_source_alias",
        metavar="ALIAS",
        help="stable alias for the author source",
    )
    p_scan.add_argument(
        "--source-url",
        required=True,
        dest="candidate_source_url",
        metavar="URL",
        help="credential-free provenance URL for the author source",
    )
    p_scan.add_argument(
        "--target-registry",
        required=True,
        dest="target_registry_alias",
        metavar="ALIAS",
        help="trust-domain registry that may later review the Candidates",
    )
    _add_json(p_scan)

    p_candidate_list = candidate_sub.add_parser(
        "list",
        help="list the Candidates recorded for the connected Upstream repositories",
        description=(
            "List the active Candidates bound to each Upstream repository's pinned snapshot, with "
            "what the Registry checkout records about their promotion. Changes nothing."
        ),
    )
    p_candidate_list.add_argument(
        "--source",
        dest="source_dir",
        metavar="DIR",
        help="registry checkout to read promotion records from (default: the project)",
    )
    p_candidate_list.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    p_candidate_promote = candidate_sub.add_parser(
        "promote",
        help="review or locally promote exact Candidate IDs as one registry transaction",
        description=(
            "Re-observe a clean pinned author checkout, select exact Candidate IDs, and plan one "
            "atomic registry promotion. Without --yes this only reviews. With --yes it writes the "
            "local registry checkout but never commits, pushes, merges, or publishes it."
        ),
    )
    p_candidate_promote.add_argument(
        "--source",
        dest="source_dir",
        required=True,
        metavar="DIR",
        help="writable local registry Git checkout",
    )
    p_candidate_promote.add_argument(
        "--checkout",
        required=True,
        dest="candidate_checkout",
        metavar="DIR",
        help="clean local Git checkout of the author source",
    )
    p_candidate_promote.add_argument(
        "--source-alias",
        required=True,
        dest="candidate_source_alias",
        metavar="ALIAS",
        help="stable alias for the author source",
    )
    p_candidate_promote.add_argument(
        "--source-url",
        required=True,
        dest="candidate_source_url",
        metavar="URL",
        help="credential-free provenance URL for the author source",
    )
    p_candidate_promote.add_argument(
        "--target-registry",
        required=True,
        dest="target_registry_alias",
        metavar="ALIAS",
        help="trust-domain registry receiving the promotion",
    )
    p_candidate_promote.add_argument(
        "--candidate",
        required=True,
        action="append",
        dest="promotion_candidate_ids",
        metavar="SHA256",
        help="exact Candidate ID selected during registry scan (repeatable)",
    )
    p_candidate_promote.add_argument(
        "--mode",
        choices=("self-contained", "pinned-reference"),
        default="self-contained",
        dest="content_mode",
        help="content mode: self-contained (enterprise default) or the weaker pinned-reference",
    )
    _add_registry_finalize(p_candidate_promote)
    _add_json(p_candidate_promote)

    p_adopt = upstream_sub.add_parser(
        "adopt",
        help="scan explicit manifests and adopt selected artifacts without subscribing",
        description=(
            "Acquire one credential-free Git URL/ref without saving it as a Source, compile only "
            "explicit aart-cli.yaml/aart-cli.json manifests, and report them. Repeat --artifact to prepare "
            "selected immutable Registry copies. Without --yes this is review-only; with --yes it "
            "writes the reviewed local transaction and never commits, pushes or merges."
        ),
    )
    p_adopt.add_argument(
        "--source",
        dest="source_dir",
        required=True,
        metavar="DIR",
        help="writable local registry Git checkout",
    )
    p_adopt.add_argument(
        "--url",
        dest="native_url",
        required=True,
        metavar="URL",
        help="credential-free Git repository URL",
    )
    p_adopt.add_argument("--ref", required=True, metavar="REF", help="branch or tag to inspect")
    p_adopt.add_argument(
        "--artifact",
        action="append",
        dest="names",
        metavar="KIND/NAME@VERSION",
        help="exact scanned coordinate to adopt (repeatable; omit to scan only)",
    )
    p_adopt.add_argument(
        "--rename",
        action="append",
        dest="adoption_renames",
        metavar="KIND/NAME=NEW-NAME",
        help=(
            "adopt a selected artifact under another Registry name, needed when this Registry "
            "already took KIND/NAME from another upstream (repeatable)"
        ),
    )
    _add_registry_finalize(p_adopt)
    p_adopt.add_argument(
        "--expect",
        metavar="DIGEST",
        help="also require the freshly prepared transaction to match this review digest",
    )
    _add_json(p_adopt)

    p_check_adoption = upstream_sub.add_parser(
        "check",
        help="compare one adopted artifact with its recorded upstream branch or tag",
        description=(
            "Read one repository-adopted Registry package, resolve its recorded branch or tag, "
            "and distinguish unchanged, changed, missing, unreachable and invalid declarations. "
            "A validated new version is review-only unless --yes is present; --expect can bind "
            "finalization to a digest returned by a prior JSON review."
        ),
    )
    p_check_adoption.add_argument(
        "--source",
        dest="source_dir",
        required=True,
        metavar="DIR",
        help="writable local registry Git checkout",
    )
    p_check_adoption.add_argument(
        "names",
        nargs=1,
        metavar="KIND/NAME@VERSION",
        help="the adopted artifact version to compare with its upstream",
    )
    _add_registry_finalize(p_check_adoption)
    p_check_adoption.add_argument(
        "--expect",
        metavar="DIGEST",
        help="require the proposed transaction to match this prior review digest",
    )
    _add_json(p_check_adoption)

    p_format = registry_sub.add_parser(
        "format",
        help="canonicalize registry JSON files",
        description=(
            "Rewrite every managed JSON document in its canonical form. With --check it changes "
            "nothing and exits 1 when any file would change; without --yes it only reviews."
        ),
    )
    _add_registry_source(p_format)
    _add_check(p_format)
    _add_registry_finalize(p_format)
    _add_json(p_format)

    p_validate = registry_sub.add_parser(
        "validate",
        help="validate registry protocol content",
        description=(
            "Check the approved version records, catalogs, packages, compatibility bounds and "
            "dependency graph against the Registry protocol. This reads only and works on a plain "
            "snapshot without .git."
        ),
    )
    _add_registry_source(p_validate)
    _add_json(p_validate)

    for action in ("lock", "build"):
        target = registry_sub.add_parser(
            action,
            help=(
                "check that approved versions carry their pins"
                if action == "lock"
                else "compile the index"
            ),
            description=(
                "Check that every approved version record under registry/versions/ already carries "
                "its source and content pins. There is nothing to resolve and no separate lock "
                "file is written."
                if action == "lock"
                else "Rebuild registry/index.json and registry/snapshot.json deterministically from "
                "the approved versions. With --check it changes nothing and exits 1 when either "
                "file is out of date; without --yes it only reviews."
            ),
        )
        _add_registry_source(target)
        _add_check(target)
        _add_registry_finalize(target)
        _add_json(target)

    p_audit = registry_sub.add_parser(
        "audit",
        help="audit review, provenance, setup, and available security metadata",
        description=(
            "Report evidence gaps: missing review, provenance, license or setup information, and "
            "absent assessment evidence. When security/index.json exists, every attestation is "
            "verified against the compiled objects, and critical installation risk is refused. "
            "Warnings are gaps in evidence, not risk conclusions."
        ),
    )
    _add_registry_source(p_audit)
    _add_json(p_audit)

    p_publish = registry_sub.add_parser(
        "publish",
        help="lock, build, validate, audit, and commit every listed registry change",
        description=(
            "Prepare lock and index in memory, run validate and audit over that exact snapshot, "
            "and list every path Git would commit. Without --yes this is review-only. With --yes "
            "it writes the reviewed generated files and creates one commit; it never pushes."
        ),
    )
    _add_registry_source(p_publish)
    p_publish.add_argument(
        "-m", "--message", dest="publish_message", metavar="TEXT", help="commit subject"
    )
    _add_registry_finalize(p_publish)
    _add_json(p_publish)

    p_push = registry_sub.add_parser(
        "push",
        help="push the reviewed registry commit to its publication branch",
        description=(
            "Push the commit this checkout is on to a remote branch, so other people can review "
            "it. The registry's default branch is refused by name: publication is a push to a "
            "branch, and only a merge makes reviewed bytes the registry. AART never merges."
        ),
    )
    _add_registry_source(p_push)
    p_push.add_argument(
        "--branch",
        dest="publication_branch",
        metavar="NAME",
        required=True,
        help="remote branch to publish to; the default branch is refused",
    )
    p_push.add_argument(
        "--remote",
        dest="publication_remote",
        metavar="NAME",
        default="origin",
        help="Git remote to publish to (default: origin)",
    )
    _add_json(p_push)

    p_test = registry_sub.add_parser(
        "test",
        help="run a compatibility validation fixture",
        description=(
            "Validate the Registry as the oldest AART it supports would read it, as the latest "
            "would, or both. The latest defaults to the running version. This reads only."
        ),
    )
    _add_registry_source(p_test)
    p_test.add_argument(
        "--compatibility",
        choices=("minimum", "latest", "all"),
        default="all",
        help="compatibility point to validate (default: all)",
    )
    p_test.add_argument(
        # The upper compatibility point is the AART doing the publishing, not a version frozen in
        # the parser: a default that never moves tests a phantom release, so a registry whose floor
        # sits above it fails as "incompatible" while one below it proves nothing about today.
        "--latest-version",
        default=__version__,
        metavar="VERSION",
        help=f"latest compatible AART version under test (default: {__version__})",
    )
    _add_json(p_test)

    p_diff = registry_sub.add_parser(
        "diff",
        help="show deterministic managed-file drift",
        description=(
            "Show how each managed file differs from its canonical form, without changing the "
            "checkout. The same input always prints the same diff."
        ),
    )
    _add_registry_source(p_diff)
    _add_json(p_diff)

    # security --------------------------------------------------------------- #
    p = sub.add_parser(
        "security",
        help="inspect explainable installation-risk evidence",
        description=(
            "Scan immutable artifacts, inspect assessment evidence, and discover optional "
            "analyzers. Assessments reduce uncertainty; they are not safety guarantees."
        ),
    )
    security_sub = p.add_subparsers(dest="security_action", metavar="ACTION", required=True)

    p_security = security_sub.add_parser(
        "scan",
        help="run the zero-dependency baseline over an immutable object envelope",
        description=(
            "Verify the object against the approved Registry that publishes the artifact, run the "
            "built-in baseline over it, and report its installation risk. With --cache the result "
            "is also written as a canonical local attestation. An assessment reduces uncertainty; "
            "it is not a safety guarantee."
        ),
    )
    p_security.add_argument(
        "security_input", metavar="OBJECT", help="immutable object envelope (JSON) to scan"
    )
    p_security.add_argument(
        "--registry",
        dest="security_registry",
        required=True,
        metavar="DIR",
        help="local checkout of the approved Registry that publishes the selected artifact",
    )
    p_security.add_argument(
        "--artifact",
        dest="security_artifact",
        required=True,
        metavar="KIND/NAME",
        help="exact artifact identity published by that Registry",
    )
    p_security.add_argument(
        "--cache", dest="security_cache", metavar="DIR", help="publish canonical local attestation"
    )
    _add_json(p_security)

    p_security = security_sub.add_parser(
        "show",
        help="show a canonical assessment or attestation",
        description=(
            "Print an assessment or attestation file: provider version, rules digest, coverage, "
            "installation risk, findings with remediation, and status. This reads only."
        ),
    )
    p_security.add_argument(
        "security_input", metavar="EVIDENCE", help="assessment or attestation file to show"
    )
    _add_json(p_security)

    p_security = security_sub.add_parser(
        "verify",
        help="verify canonical attestation identity, freshness, and locally derived trust",
        description=(
            "Check that an attestation is canonical and that its identity matches every expected "
            "digest and version given; any mismatch marks it stale and exits non-zero. Publisher "
            "trust is derived only when --publisher-source-id, --registry-inputs-digest and "
            "--publisher-trust are given together."
        ),
    )
    p_security.add_argument(
        "security_input", metavar="ATTESTATION", help="attestation file to verify"
    )
    p_security.add_argument(
        "--object-digest",
        dest="security_object_digest",
        metavar="SHA256",
        help="expected immutable object digest; a mismatch marks evidence stale",
    )
    p_security.add_argument(
        "--rules-digest",
        dest="security_rules_digest",
        metavar="SHA256",
        help="expected analyzer rules digest; a mismatch marks evidence stale",
    )
    p_security.add_argument(
        "--options-digest",
        dest="security_options_digest",
        metavar="SHA256",
        help="expected analyzer options digest; a mismatch marks evidence stale",
    )
    p_security.add_argument(
        "--policy-digest",
        dest="security_policy_digest",
        metavar="SHA256",
        help="expected effective policy digest; a mismatch marks evidence stale",
    )
    p_security.add_argument(
        "--provider-version",
        dest="security_provider_version",
        metavar="VERSION",
        help="expected provider version; a mismatch marks evidence stale",
    )
    p_security.add_argument(
        "--publisher-source-id",
        metavar="SLUG",
        help="locally configured publisher identity used to derive trust",
    )
    p_security.add_argument(
        "--registry-inputs-digest",
        dest="security_registry_inputs_digest",
        metavar="SHA256",
        help="exact locally resolved registry inputs digest used to derive trust",
    )
    p_security.add_argument(
        "--publisher-trust",
        choices=("unverified", "registry-reviewed", "company-reviewed"),
        help="local trust classification for the exact publisher and registry inputs",
    )
    _add_json(p_security)

    p_security = security_sub.add_parser(
        "analyzers",
        help="list reviewed optional analyzer adapters and local availability",
        description=(
            "List the optional analyzers AART knows how to run and whether each is installed on "
            "this machine. AART never installs one; a missing analyzer means less evidence, not "
            "a failure."
        ),
    )
    _add_json(p_security)
    p_security = security_sub.add_parser(
        "suites",
        help="list built-in analyzer suites",
        description=(
            "List the built-in analyzer suites: what each one adds and which optional providers "
            "it runs when they are installed."
        ),
    )
    _add_json(p_security)

    # author ------------------------------------------------------------------ #
    p = sub.add_parser(
        "author",
        formatter_class=_HELP_FORMATTER,
        help="start and check an artifact you are writing",
        description=(
            "Write artifacts. This group targets your own working directory: a Registry is "
            "somewhere an artifact is published to, never where it is written."
        ),
    )
    author_sub = p.add_subparsers(dest="author_action", metavar="ACTION", required=True)
    p_author_init = author_sub.add_parser(
        "init",
        formatter_class=_HELP_FORMATTER,
        help="write an aart-cli.yaml carrying every accepted field, plus a payload skeleton",
        description=(
            "Write a manifest that carries the whole accepted field surface, with the optional "
            "blocks commented out and one line of explanation each, so narrowing it down is an "
            "edit rather than a search through the schema. Nothing existing is replaced."
        ),
    )
    p_author_init.add_argument(
        "--kind",
        dest="artifact_kind",
        required=True,
        # The parser's own vocabulary. A Collection is in it only to be refused with where the
        # Registry makes one (D-430).
        choices=AUTHORED_KINDS,
        help="what kind of artifact to start",
    )
    p_author_init.add_argument(
        "--name",
        dest="author_name",
        required=True,
        metavar="SLUG",
        help="the artifact name, as a lowercase slug",
    )
    p_author_init.add_argument(
        "--into",
        dest="author_into",
        metavar="DIR",
        help="where to write the workspace (default: the working directory)",
    )
    p_author_check = author_sub.add_parser(
        "check",
        formatter_class=_HELP_FORMATTER,
        help="parse every aart-cli.yaml/aart-cli.json under a directory",
        description=(
            "Read the directory the way a Upstream sync reads one and put every manifest it "
            "finds through the parser a Registry uses. The verdict is the parser's, so a "
            "manifest that passes here is one `registry scan` will accept."
        ),
    )
    p_author_check.add_argument(
        "--source",
        dest="author_source",
        metavar="DIR",
        help="the directory to check (default: the working directory)",
    )
    _add_json(p_author_check)

    # docs -------------------------------------------------------------------- #
    p = sub.add_parser(
        "docs",
        formatter_class=_HELP_FORMATTER,
        help="print the command reference, read from this parser",
        description=(
            "Print every command with what it does, or one command's description, usage, options "
            "and defaults. It is read from this installed version when it runs, so it always "
            "matches it. --json gives the same reference as one document, for agents."
        ),
    )
    p.add_argument(
        "docs_path",
        nargs="*",
        metavar="COMMAND",
        help="the command or group to describe, such as `consume install` (default: all)",
    )
    _add_json(p)

    return parser
