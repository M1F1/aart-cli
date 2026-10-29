"""CLI wiring: argparse subcommands -> Request -> command dispatch -> exit code.

One core, two skins (Product Specification §33). This module is the flag-mode skin: it parses ``argv``
into the frozen :class:`~aart_cli.model.Request`, dispatches to the matching command's
``run(request) -> int`` (the commands already map their `Result`s to the §7 exit-code
vocabulary via ``commands._common.exit_code``), and returns that code. A bare invocation on a
TTY launches the TUI; otherwise it prints help.

This module owns only the *wiring*: no decision logic lives here. argparse handles usage errors with
its own exit code ``2`` (== ``_common.USAGE``); ``--help`` exits ``0``.

The TUI module exposes ``tui.run() -> int``. It is imported lazily so flag-mode commands do not
load it.
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Optional, Sequence, Tuple

from . import cli_docs
from .cli_parser import build_parser
from .command_outcome import OK
from .commands import upgrade
from .model import Request
from .outcomes import CommandOutcome


def _run_registry(request: Request) -> int:
    from .commands import registry

    return registry.run(request)


def _run_security(request: Request) -> int:
    from .commands import security

    return security.run(request)


def _run_source(request: Request) -> int:
    from .commands import source

    return source.run(request)


def _run_marketplace(request: Request) -> int:
    from .commands import marketplace

    return marketplace.run(request)


def _run_doctor(request: Request) -> int:
    from .commands import doctor

    return doctor.run(request)


def _run_reset(request: Request) -> int:
    from .commands import reset

    return reset.run(request)


def _run_author(request: Request) -> int:
    from .commands import author

    return author.run(request)


def _run_candidate(request: Request) -> int:
    from .commands import candidate

    return candidate.run(request)


def _run_mcp(request: Request) -> int:
    from .commands import mcp

    return mcp.run(request)


def _run_usage(request: Request) -> int:
    from .commands import usage

    return usage.run(request)


def _run_inputs(request: Request) -> int:
    """`consume inputs` (§198): the TUI's own application, so it is not a `commands` module.

    `commands` may not depend on the TUI, which depends on it; every `DISPATCH` entry is a
    `commands` module's `run`, so this one is routed before the table is read.
    """

    from . import cli_inputs

    return cli_inputs.run(request)


# Command name -> handler. Value-keyed dispatch, not a class hierarchy.
DISPATCH: dict[str, Callable[[Request], int]] = {
    "upgrade": upgrade.run,
    "registry": _run_registry,
    "security": _run_security,
    "source": _run_source,
    "marketplace": _run_marketplace,
    "doctor": _run_doctor,
    "reset": _run_reset,
    "author": _run_author,
    "mcp": _run_mcp,
    "usage": _run_usage,
    "candidate": _run_candidate,
}

# Structured results used by interactive frontends. Flag mode retains ``DISPATCH`` and its
# integer contract; both paths execute the same command application service exactly once.
RESULT_DISPATCH: dict[str, Callable[[Request], CommandOutcome]] = {}


# --------------------------------------------------------------------------- #
# argparse Namespace -> Request                                                #
# --------------------------------------------------------------------------- #
def _split_csv(values) -> Tuple[str, ...]:
    """Flatten a repeated, optionally comma-separated option into an ordered tuple.

    Accepts ``--profile a,b --profile c`` and ``--profile a --profile b`` alike.
    """
    if not values:
        return ()
    items = values if isinstance(values, list) else [values]
    out: list[str] = []
    for chunk in items:
        out.extend(part.strip() for part in str(chunk).split(",") if part.strip())
    return tuple(out)


#: `maintain upstream` actions that are Registry maintenance rather than a connection change.
_UPSTREAM_REGISTRY_ACTIONS = {"scan": "scan", "adopt": "adopt", "check": "check-upstream"}


def _route(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    """The handler a role-family command reaches, and the request fields it implies (§175.2).

    The public surface is `consume`, `maintain` and `author` (INV-270); the handlers behind them
    are the ones the old families had, so only this mapping knows both names.
    """

    command = args.command
    if command == "consume":
        action = args.consume_action
        if action == "registry":
            return "source", {"source_family": "registry"}
        if action == "mcp":
            return "mcp", {}
        if action == "inputs":
            return "inputs", {}
        if action == "usage":
            return "usage", {}
        return "marketplace", {"marketplace_action": action}
    if command == "maintain":
        action = args.maintain_action
        if action == "upstream":
            if args.source_action in _UPSTREAM_REGISTRY_ACTIONS:
                return "registry", {
                    "registry_action": _UPSTREAM_REGISTRY_ACTIONS[args.source_action],
                    "source_action": None,
                }
            return "source", {"source_family": "upstream"}
        if action == "candidate":
            if args.candidate_action == "list":
                return "candidate", {}
            return "registry", {"registry_action": args.candidate_action}
        return "registry", {}
    return command, {}


def _source_kind(args: argparse.Namespace, family: object) -> Optional[str]:
    transport = getattr(args, "source_kind", None)
    if transport is None:
        return None
    return f"{'registry' if family == 'registry' else 'source'}-{transport}"


def _to_request(args: argparse.Namespace) -> Request:
    """Map a parsed namespace to a frozen :class:`Request`.

    Uses ``getattr`` with defaults because each subparser defines only its own flags.
    """
    command, routed = _route(args)
    return Request(
        command=command,
        names=tuple(getattr(args, "names", None) or ()),
        profiles=_split_csv(getattr(args, "profile", None)),
        source_dir=getattr(args, "source_dir", None),
        project=getattr(args, "project", None),
        scope=getattr(args, "scope", "project"),
        artifact_kind=getattr(args, "artifact_kind", None),
        yes=bool(getattr(args, "yes", False)),
        expect=getattr(args, "expect", None),
        for_default_branch=bool(getattr(args, "for_default_branch", False)),
        install_inputs=tuple(getattr(args, "install_inputs", None) or ()),
        set_later=bool(getattr(args, "set_later", False)),
        inputs_action=getattr(args, "inputs_action", None),
        inputs_scope=getattr(args, "inputs_scope", None),
        inputs_argument=getattr(args, "inputs_argument", None),
        force=bool(getattr(args, "force", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
        json=bool(getattr(args, "json", False)),
        prune=bool(getattr(args, "prune", False)),
        ref=getattr(args, "ref", None),
        native_url=getattr(args, "native_url", None),
        adoption_renames=tuple(getattr(args, "adoption_renames", None) or ()),
        registry_action=routed.get("registry_action", getattr(args, "registry_action", None)),  # type: ignore[arg-type]
        candidate_checkout=getattr(args, "candidate_checkout", None),
        candidate_source_alias=getattr(args, "candidate_source_alias", None),
        candidate_source_url=getattr(args, "candidate_source_url", None),
        target_registry_alias=getattr(args, "target_registry_alias", None),
        promotion_candidate_ids=tuple(getattr(args, "promotion_candidate_ids", ()) or ()),
        content_mode=getattr(args, "content_mode", "self-contained"),
        check=bool(getattr(args, "check", False)),
        source_id=getattr(args, "source_id", None),
        display_name=getattr(args, "display_name", None),
        summary=getattr(args, "summary", None),
        collection_members=tuple(getattr(args, "collection_members", ()) or ()),
        publish_message=getattr(args, "publish_message", None),
        publication_branch=getattr(args, "publication_branch", None),
        publication_remote=getattr(args, "publication_remote", "origin"),
        minimum_version=getattr(args, "minimum_version", None),
        maximum_version=getattr(args, "maximum_version", None),
        latest_version=getattr(args, "latest_version", None),
        compatibility=getattr(args, "compatibility", None),
        security_action=getattr(args, "security_action", None),
        security_input=getattr(args, "security_input", None),
        security_artifact=getattr(args, "security_artifact", None),
        security_registry=getattr(args, "security_registry", None),
        security_cache=getattr(args, "security_cache", None),
        security_object_digest=getattr(args, "security_object_digest", None),
        security_rules_digest=getattr(args, "security_rules_digest", None),
        security_options_digest=getattr(args, "security_options_digest", None),
        security_policy_digest=getattr(args, "security_policy_digest", None),
        security_provider_version=getattr(args, "security_provider_version", None),
        publisher_source_id=getattr(args, "publisher_source_id", None),
        security_registry_inputs_digest=getattr(args, "security_registry_inputs_digest", None),
        publisher_trust=getattr(args, "publisher_trust", None),
        author_action=getattr(args, "author_action", None),
        author_name=getattr(args, "author_name", None),
        author_into=getattr(args, "author_into", None),
        author_source=getattr(args, "author_source", None),
        reset_restore=getattr(args, "reset_restore", None),
        source_action=routed.get("source_action", getattr(args, "source_action", None)),  # type: ignore[arg-type]
        source_family=routed.get("source_family"),  # type: ignore[arg-type]
        source_alias=getattr(args, "source_alias", None),
        source_kind=_source_kind(args, routed.get("source_family")),
        source_location=getattr(args, "source_location", None),
        source_make_default=getattr(args, "source_make_default", None),
        marketplace_action=routed.get("marketplace_action"),  # type: ignore[arg-type]
        mcp_action=getattr(args, "mcp_action", None),
        all_installed=bool(getattr(args, "all_installed", False)),
        show_response=bool(getattr(args, "show_response", False)),
        query=tuple(getattr(args, "query", ()) or ()),
        search_limit=getattr(args, "search_limit", None),
        receipt_action=getattr(args, "receipt_action", None),
        runtime_environment=getattr(args, "runtime_environment", None),
        offline=bool(getattr(args, "offline", False)),
        authorize_untrusted_source=bool(getattr(args, "authorize_untrusted_source", False)),
        authorize_custom_entrypoint=bool(getattr(args, "authorize_custom_entrypoint", False)),
        approve_setup_effects=bool(getattr(args, "approve_setup_effects", False)),
        upgrade_wheel=getattr(args, "upgrade_wheel", None),
        upgrade_source_checkout=getattr(args, "upgrade_source_checkout", None),
        upgrade_how=bool(getattr(args, "upgrade_how", False)),
        usage_action=getattr(args, "usage_action", None),
        usage_forget=bool(getattr(args, "usage_forget", False)),
    )


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #
def _seeds_first_run(args: argparse.Namespace, request: Request) -> bool:
    """Whether this command connects the Registry the build carried, on a first run (B-168).

    Only `consume` reads Registries; a maintainer works in a checkout and an author in a workspace.
    `consume registry add` is the person choosing a Registry, which the seed must not pre-empt, and
    `--offline` forbids the fetch a connection needs.
    """

    if args.command != "consume" or request.offline:
        return False
    return not (request.source_family == "registry" and request.source_action == "add")


def _seed_first_run(request: Request) -> None:
    """Connect the baked Registry before the command reads its configuration.

    Said on stderr: stdout belongs to the command, and a `--json` reader must get only the document.
    """

    from .commands.first_run import announce_first_run_seed, seed_first_run

    report = seed_first_run(request.command, request.user_home)
    announce_first_run_seed(report, lambda line: print(line, file=sys.stderr))


def _run_bare(parser: argparse.ArgumentParser, args: Optional[argparse.Namespace] = None) -> int:
    """Bare invocation: launch the TUI on a TTY, else print help."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        from . import tui  # Always present in the package.

        kwargs = {}
        if args and getattr(args, "project", None):
            kwargs["project"] = args.project
        return int(tui.run(**kwargs))
    parser.print_help()
    return OK


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse ``argv``, dispatch to a command, and return its process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        return _run_bare(parser, args)
    if args.command == "docs":
        # The reference is read from the parser itself, so it reaches no command handler.
        return cli_docs.run(
            parser, args.docs_path, as_json=args.json, out=sys.stdout, err=sys.stderr
        )
    request = _to_request(args)
    if _seeds_first_run(args, request):
        _seed_first_run(request)
    code = (
        _run_inputs(request) if request.command == "inputs" else DISPATCH[request.command](request)
    )
    if args.command == "consume":
        # §211: after the command, on stderr, so a `--json` document on stdout is unchanged.
        upgrade.announce_newer_aart_cli(
            lambda line: print(line, file=sys.stderr), user_home=request.user_home
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
