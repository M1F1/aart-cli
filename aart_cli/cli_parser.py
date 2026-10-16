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

    sub.add_parser(
        "reset",
        formatter_class=_HELP_FORMATTER,
        help="restore AART's per-user application state to factory defaults",
        description=(
            "Remove only AART-owned per-user configuration, managed source snapshots, receipts, "
            "settings and caches after two exact typed confirmations. Projects, harness files, "
            "organization policy and credentials owned by other applications are not removed."
        ),
    )

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

    # source ------------------------------------------------------------------ #
    p = sub.add_parser(
        "source",
        formatter_class=_HELP_FORMATTER,
        help="add and inspect configured canonical source origins",
        description=(
            "Manage configured registry/direct/local origins for the canonical marketplace. "
            "`source add` validates and snapshots the exact source before saving it, so it is "
            "safe for non-interactive agent use."
        ),
    )
    source_sub = p.add_subparsers(dest="source_action", metavar="ACTION", required=True)
    p_add_source = source_sub.add_parser(
        "add",
        help="synchronize, validate, then persist one source origin",
        description=(
            "Parse one exact source, validate a fresh immutable snapshot, then atomically save "
            "the source configuration. No interactive confirmation is required because all "
            "origin/default choices are explicit command arguments."
        ),
    )
    p_add_source.add_argument(
        "--alias", dest="source_alias", required=True, metavar="ALIAS", help="source alias slug"
    )
    p_add_source.add_argument(
        "--kind",
        dest="source_kind",
        choices=("registry-git", "registry-local", "source-git", "source-local"),
        required=True,
        help="registry-git, registry-local, source-git, or source-local",
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
            "Git ref: defaults to main for registry-git and source-git, required as the selected "
            "branch for registry-local, not valid for source-local"
        ),
    )
    source_default = p_add_source.add_mutually_exclusive_group()
    source_default.add_argument(
        "--default",
        dest="source_make_default",
        action="store_const",
        const=True,
        help="make this registry the default registry",
    )
    source_default.add_argument(
        "--no-default",
        dest="source_make_default",
        action="store_const",
        const=False,
        help="preserve the current default registry",
    )
    _add_json(p_add_source)

    p_source_list = source_sub.add_parser(
        "list",
        help="show configured origins and managed snapshot health",
    )
    _add_json(p_source_list)

    def _add_alias(p: argparse.ArgumentParser, help_text: str) -> None:
        p.add_argument("--alias", dest="source_alias", metavar="ALIAS", help=help_text)

    p_source_sync = source_sub.add_parser(
        "sync",
        formatter_class=_HELP_FORMATTER,
        help="refresh managed snapshots for configured sources",
        description=(
            "Re-synchronize already-configured sources. This never adds, renames, removes, or "
            "re-identifies a source, and never changes policy defaults - use it instead of "
            "re-adding an existing alias."
        ),
    )
    _add_alias(p_source_sync, "synchronize only this alias (default: every enabled source)")
    _add_json(p_source_sync)

    p_source_remove = source_sub.add_parser(
        "remove",
        formatter_class=_HELP_FORMATTER,
        help="forget one configured source and delete its managed snapshot",
        description=(
            "End one subscription: drop the configuration entry, clear the default registry if it "
            "named this alias, and delete the managed snapshot so the origin is free to be added "
            "again. No installed artifact and no file in any project is touched."
        ),
    )
    p_source_remove.add_argument(
        "--alias",
        dest="source_alias",
        required=True,
        metavar="ALIAS",
        help="configured source alias to remove",
    )
    p_source_remove.add_argument(
        "--yes",
        action="store_true",
        help="finalize the reviewed removal (without this the command only reviews)",
    )
    _add_json(p_source_remove)

    p_source_resubscribe = source_sub.add_parser(
        "resubscribe",
        formatter_class=_HELP_FORMATTER,
        help="adopt a changed declared identity at an unchanged origin and ref",
        description=(
            "Adopt the identity an already-configured origin now declares, keeping the alias, "
            "kind, location, ref, and default-registry flag. Without --yes it prints both "
            "identities and changes nothing; --yes adopts exactly the reviewed transition and "
            "refuses if the origin moved again in between. Use `source sync` when the identity "
            "did not change."
        ),
    )
    p_source_resubscribe.add_argument(
        "--alias",
        dest="source_alias",
        required=True,
        metavar="ALIAS",
        help="configured source alias whose declared identity changed",
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
            "adopt only this exact identity change, written as the two declared source IDs; "
            "otherwise refuse and show the transition that is actually offered"
        ),
    )
    _add_json(p_source_resubscribe)

    p_source_health = source_sub.add_parser(
        "health",
        formatter_class=_HELP_FORMATTER,
        help="report managed snapshot health for configured sources",
        description=(
            "Read-only per-source health: pointer presence, resolved revision, and snapshot age "
            "against the configured freshness window. Exits non-zero if an enabled source is not "
            "healthy."
        ),
    )
    _add_alias(p_source_health, "report only this alias (default: every configured source)")
    _add_json(p_source_health)

    # marketplace ------------------------------------------------------------- #
    p = sub.add_parser(
        "marketplace",
        formatter_class=_HELP_FORMATTER,
        help="browse the configured canonical marketplace",
        description=(
            "Read the local, already-validated configured source snapshots as one canonical "
            "marketplace. This is the one agent-facing consumer command family."
        ),
    )
    marketplace_sub = p.add_subparsers(dest="marketplace_action", metavar="ACTION", required=True)
    p_marketplace_list = marketplace_sub.add_parser(
        "list",
        help="emit all canonical marketplace sources and artifacts",
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
        placement: bool = True,
        memory_mode: bool = False,
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
        if placement:
            lifecycle.add_argument(
                "--mode",
                dest="install_mode",
                choices=("copy", "symlink"),
                default=None,
                help="install placement mode (default: copy)",
            )
        if memory_mode:
            lifecycle.add_argument(
                "--memory-mode",
                dest="memory_mode",
                choices=("replace", "prepend", "append", "skip"),
                default=None,
                help=(
                    "how a memory artifact meets an existing instruction file (default: prepend)"
                ),
            )
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
        memory_mode=True,
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
        placement=False,
    )
    _add_lifecycle(
        "status",
        "report installed artifact state against the configured sources",
        coordinates="artifact or collection coordinate(s) to inspect; omit for all installed",
        placement=False,
    )
    p_marketplace_setup = _add_lifecycle(
        "setup",
        "run declared post-install setup for installed artifacts",
        coordinates="artifact or collection coordinate(s) whose setup should run",
        placement=False,
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
    p = sub.add_parser(
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
    )
    p_mcp_test.add_argument("names", nargs="*", metavar="INSTALLED")
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
    p = sub.add_parser(
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

    p_init = registry_sub.add_parser("init", help="initialize a canonical registry checkout")
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
        help="author a collection from artifacts this registry already holds",
    )
    _add_registry_source(p_collection)
    p_collection.add_argument("names", nargs=1, metavar="NAME")
    p_collection.add_argument(
        "--summary",
        required=True,
        metavar="TEXT",
        help="one-line collection description",
    )
    p_collection.add_argument(
        "--include",
        action="append",
        required=True,
        dest="collection_members",
        metavar="KIND/NAME",
        help="artifact already held by this registry (repeatable)",
    )
    _add_registry_finalize(p_collection)
    _add_json(p_collection)

    p_scan = registry_sub.add_parser(
        "scan",
        help="discover native Candidates in one pinned author checkout",
        description=(
            "Read a clean Git author checkout at its exact HEAD, compile only explicit aart-cli.json "
            "or aart-cli.yaml manifests, and report Candidate state. Source Scan never changes the "
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

    p_candidate_promote = registry_sub.add_parser(
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
        choices=("vendored", "referenced"),
        default="vendored",
        dest="promotion_mode",
        help="enterprise default vendored, or explicit weaker referenced mode",
    )
    _add_registry_finalize(p_candidate_promote)
    _add_json(p_candidate_promote)

    p_adopt = registry_sub.add_parser(
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
    _add_registry_finalize(p_adopt)
    p_adopt.add_argument(
        "--expect",
        metavar="DIGEST",
        help="also require the freshly prepared transaction to match this review digest",
    )
    _add_json(p_adopt)

    p_check_adoption = registry_sub.add_parser(
        "check-upstream",
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
    p_check_adoption.add_argument("names", nargs=1, metavar="KIND/NAME@VERSION")
    _add_registry_finalize(p_check_adoption)
    p_check_adoption.add_argument(
        "--expect",
        metavar="DIGEST",
        help="require the proposed transaction to match this prior review digest",
    )
    _add_json(p_check_adoption)

    p_discover = registry_sub.add_parser(
        "discover",
        help="scan a foreign checkout and emit a reviewable vendoring manifest",
        description=(
            "Recognize conservative conventional shapes in an inert local checkout. The output "
            "is a vendor-batch manifest: candidates are rejected by default so discovery never "
            "turns a guess into registry content. Edit each accept field, then review the one "
            "atomic `registry vendor-batch` plan."
        ),
    )
    p_discover.add_argument(
        "--checkout",
        required=True,
        dest="discovery_checkout",
        metavar="DIR",
        help="foreign repository checkout to scan without following symlinks",
    )
    p_discover.add_argument(
        "--url", dest="native_url", required=True, metavar="URL", help="credential-free Git URL"
    )
    p_discover.add_argument(
        "--ref", default="main", metavar="REF", help="Git ref the later vendoring resolves"
    )
    p_discover.add_argument(
        "--artifact-version",
        default="1.0.0",
        metavar="VERSION",
        help="version proposed for every candidate (default: 1.0.0)",
    )
    p_discover.add_argument(
        "--profile",
        action="append",
        required=True,
        metavar="P[,P...]",
        help="target harness profile(s); comma-separated or repeated",
    )
    p_discover.add_argument(
        "--platform",
        action="append",
        required=True,
        metavar="PLATFORM",
        help="supported platform (repeatable)",
    )
    p_discover.add_argument(
        "--install-scope",
        action="append",
        choices=_INSTALL_SCOPES,
        dest="registry_scopes",
        default=[],
        help="supported install scope (repeatable; default: project)",
    )
    p_discover.add_argument(
        "--install-mode",
        action="append",
        choices=("copy", "symlink"),
        dest="registry_modes",
        default=[],
        help="supported install mode (repeatable; default: copy)",
    )
    p_discover.add_argument(
        "--review-policy",
        default="manual-review-v1",
        metavar="POLICY",
        help="approved review policy identifier (default: manual-review-v1)",
    )
    p_discover.add_argument(
        "--accept-all",
        action="store_true",
        dest="discovery_accept_all",
        help="mark every candidate accepted in the manifest; the batch still requires review",
    )
    p_discover.add_argument(
        "--output",
        dest="discovery_output",
        metavar="FILE",
        help="write the manifest to a new file instead of standard output",
    )

    p_format = registry_sub.add_parser("format", help="canonicalize registry JSON files")
    _add_registry_source(p_format)
    _add_check(p_format)
    _add_registry_finalize(p_format)
    _add_json(p_format)

    p_vendor = registry_sub.add_parser(
        "vendor",
        help="copy a foreign subtree in: this registry ships the bytes and owns the version",
        description=(
            "Copy a subtree of any Git repository into this registry as an owned package pinned "
            "to a resolved commit, with provenance recording where the bytes came from. The "
            "upstream needs no AART markers. This registry then owns the copy: it declares the "
            "version, and upstream fixes reach consumers only when it is vendored again. A "
            "successful vendor reports what was copied; it is not a safety claim. A "
            "repository containing a symlink anywhere cannot be acquired, and a symlink inside "
            "the subtree is refused."
        ),
    )
    _add_registry_source(p_vendor)
    p_vendor.add_argument("artifact_kind", choices=_ARTIFACT_TYPES, metavar="KIND")
    p_vendor.add_argument("names", nargs=1, metavar="NAME")
    p_vendor.add_argument(
        "--url", dest="native_url", required=True, metavar="URL", help="credential-free Git URL"
    )
    p_vendor.add_argument(
        "--ref", default="main", metavar="REF", help="Git ref to resolve (default: main)"
    )
    p_vendor.add_argument(
        "--path",
        dest="native_path",
        required=True,
        metavar="DIR",
        help="subtree to copy, relative to the repository root",
    )
    p_vendor.add_argument(
        # Upstream declares no version AART can trust, and deriving one would be a guess presented
        # as a fact.  The registry owns the version, so the maintainer states it.
        "--artifact-version",
        required=True,
        metavar="VERSION",
        help="version this registry publishes the copy under",
    )
    p_vendor.add_argument(
        "--summary", required=True, metavar="TEXT", help="one-line artifact description"
    )
    p_vendor.add_argument(
        # Discovery fills the silence; it never overrules the maintainer.  AART reads an upstream
        # licence file, it does not adjudicate the grant, so the registry states what it publishes.
        "--license",
        dest="artifact_license",
        metavar="SPDX",
        help="license this registry records for the copy (default: read from the taken subtree)",
    )
    p_vendor.add_argument(
        "--profile",
        action="append",
        required=True,
        metavar="P[,P...]",
        help="target harness profile(s); comma-separated or repeated",
    )
    p_vendor.add_argument(
        "--platform",
        action="append",
        required=True,
        metavar="PLATFORM",
        help="supported platform (repeatable)",
    )
    p_vendor.add_argument(
        "--install-scope",
        action="append",
        choices=_INSTALL_SCOPES,
        dest="registry_scopes",
        default=[],
        help="supported install scope (repeatable; default: project)",
    )
    p_vendor.add_argument(
        "--install-mode",
        action="append",
        choices=("copy", "symlink"),
        dest="registry_modes",
        default=[],
        help="supported install mode (repeatable; default: copy)",
    )
    p_vendor.add_argument(
        "--setup-recipe",
        metavar="PATH",
        help="package-relative setup recipe you have already authored beside the payload",
    )
    p_vendor.add_argument(
        "--review-policy",
        default="manual-review-v1",
        metavar="POLICY",
        help="approved review policy identifier (default: manual-review-v1)",
    )
    _add_registry_finalize(p_vendor)
    _add_json(p_vendor)

    p_vendor_batch = registry_sub.add_parser(
        "vendor-batch",
        help="vendor accepted manifest candidates in one acquisition and one atomic review",
    )
    _add_registry_source(p_vendor_batch)
    p_vendor_batch.add_argument(
        "--manifest",
        required=True,
        dest="vendor_manifest",
        metavar="FILE",
        help="reviewed discovery/vendor manifest whose accepted artifacts to vendor",
    )
    _add_registry_finalize(p_vendor_batch)
    _add_json(p_vendor_batch)

    p_revendor = registry_sub.add_parser(
        "revendor",
        help="re-resolve one vendored copy's upstream and report, or apply what moved",
        description=(
            "Re-resolve the ref this artifact was vendored at and compare the subtree with the "
            "copy this registry ships. Reports up-to-date, changed, or unreachable; an upstream "
            "that cannot be read is never reported as up-to-date. Upstream declares no version "
            "AART can trust, so applying a change requires the version you state for it."
        ),
    )
    _add_registry_source(p_revendor)
    p_revendor.add_argument("artifact_kind", choices=_ARTIFACT_TYPES, metavar="KIND")
    p_revendor.add_argument("names", nargs=1, metavar="NAME")
    p_revendor.add_argument(
        "--artifact-version",
        metavar="VERSION",
        help="version this registry publishes the moved copy under; without it, nothing is planned",
    )
    p_revendor.add_argument(
        "--review-policy",
        default="manual-review-v1",
        metavar="POLICY",
        help="approved review policy identifier (default: manual-review-v1)",
    )
    _add_check(p_revendor)
    _add_registry_finalize(p_revendor)
    _add_json(p_revendor)

    p_validate = registry_sub.add_parser("validate", help="validate registry protocol content")
    _add_registry_source(p_validate)
    _add_json(p_validate)

    for action in ("lock", "build"):
        target = registry_sub.add_parser(
            action,
            help=f"{'resolve authored references' if action == 'lock' else 'compile the index'}",
        )
        _add_registry_source(target)
        _add_check(target)
        _add_registry_finalize(target)
        _add_json(target)

    p_audit = registry_sub.add_parser(
        "audit", help="audit review, provenance, setup, and available security metadata"
    )
    _add_registry_source(p_audit)
    p_audit.add_argument(
        "--check-upstream",
        action="store_true",
        help=(
            "resolve each vendored artifact's origin and report the ones behind upstream; "
            "unreachable origins are reported as unknown, and neither finding fails the audit"
        ),
    )
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

    p_test = registry_sub.add_parser("test", help="run a compatibility validation fixture")
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

    p_diff = registry_sub.add_parser("diff", help="show deterministic managed-file drift")
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
        "scan", help="run the zero-dependency baseline over an immutable object envelope"
    )
    p_security.add_argument("security_input", metavar="OBJECT")
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

    p_security = security_sub.add_parser("show", help="show a canonical assessment or attestation")
    p_security.add_argument("security_input", metavar="EVIDENCE")
    _add_json(p_security)

    p_security = security_sub.add_parser(
        "verify", help="verify canonical attestation identity, freshness, and locally derived trust"
    )
    p_security.add_argument("security_input", metavar="ATTESTATION")
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
        "analyzers", help="list reviewed optional analyzer adapters and local availability"
    )
    _add_json(p_security)
    p_security = security_sub.add_parser("suites", help="list built-in analyzer suites")
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
        # The parser's own vocabulary: every artifact kind it accepts, and a Collection.
        choices=AUTHORED_KINDS,
        help="what kind of artifact, or a collection, to start",
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
            "Read the directory the way a Source Sync reads one and put every manifest it "
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

    return parser
