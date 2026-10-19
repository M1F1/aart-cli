"""`aart-cli docs`: the command reference, read from the parser when the CLI runs (§177, INV-276).

Nothing here is written down twice. The parser already holds every command's help, description,
usage, options, defaults and choices; this module walks it and prints what it finds, so the
reference always matches the installed version and a new command needs no documentation change.
"""

from __future__ import annotations

import argparse
import json
from typing import Iterator, Optional, Sequence, TextIO

from . import __version__
from .command_outcome import OK, USAGE

_PROG = "aart-cli"


def _subcommands(parser: argparse.ArgumentParser) -> Optional[argparse._SubParsersAction]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _children(
    parser: argparse.ArgumentParser,
) -> Iterator[tuple[str, str, argparse.ArgumentParser]]:
    group = _subcommands(parser)
    if group is None:
        return
    helps = {choice.dest: choice.help or "" for choice in group._choices_actions}
    for name, child in group.choices.items():
        yield name, helps.get(name, ""), child


def _leaves(
    parser: argparse.ArgumentParser, path: tuple[str, ...], help_text: str = ""
) -> Iterator[tuple[tuple[str, ...], str, argparse.ArgumentParser]]:
    children = list(_children(parser))
    if not children:
        yield path, help_text, parser
        return
    for name, child_help, child in children:
        yield from _leaves(child, (*path, name), child_help)


def _find(
    parser: argparse.ArgumentParser, path: Sequence[str]
) -> Optional[tuple[str, argparse.ArgumentParser]]:
    node, help_text = parser, ""
    for word in path:
        found = {name: (child_help, child) for name, child_help, child in _children(node)}
        if word not in found:
            return None
        help_text, node = found[word]
    return help_text, node


def _plain(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)


def _argument(action: argparse.Action) -> dict[str, object]:
    return {
        "name": action.dest,
        "flags": list(action.option_strings),
        "metavar": _plain(action.metavar),
        "help": action.help or "",
        "default": _plain(action.default),
        "choices": _plain(list(action.choices)) if action.choices is not None else None,
        "required": bool(action.required),
        "nargs": _plain(action.nargs),
    }


def _entry(
    path: tuple[str, ...], help_text: str, leaf: argparse.ArgumentParser
) -> dict[str, object]:
    return {
        "path": " ".join(path),
        "help": help_text,
        "description": leaf.description or "",
        "usage": leaf.format_usage().strip(),
        "arguments": [
            _argument(action)
            for action in leaf._actions
            if not isinstance(action, argparse._HelpAction)
        ],
    }


def run(
    parser: argparse.ArgumentParser,
    path: Sequence[str],
    *,
    as_json: bool,
    out: TextIO,
    err: TextIO,
) -> int:
    """Print the reference for `path` (the whole tree when empty) and return the exit code."""
    # `docs "consume install"` and `docs consume install` name one command.
    path = [word for part in path for word in part.split()]
    found = _find(parser, path)
    if found is None:
        err.write(
            f"{_PROG} docs: no command '{' '.join(path)}'; "
            f"run `{_PROG} docs` for the list of commands\n"
        )
        return USAGE
    help_text, node = found
    leaves = list(_leaves(node, tuple(path), help_text))
    if as_json:
        document = {
            "prog": _PROG,
            "version": __version__,
            "commands": [_entry(*leaf) for leaf in leaves],
        }
        out.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
        return OK
    if path:
        out.write(node.format_help())
        if len(leaves) > 1:
            out.write("\ncommands:\n")
            out.writelines(_tree(leaves))
        return OK
    out.write(f"{_PROG} {__version__}: every command, and what it does.\n\n")
    out.writelines(_tree(leaves))
    out.write(
        f"\nRun `{_PROG} docs COMMAND` for one command's description, usage and options, "
        f"or add --json for all of it as one document.\n"
    )
    return OK


def _tree(leaves: Sequence[tuple[tuple[str, ...], str, argparse.ArgumentParser]]) -> list[str]:
    names = [f"{_PROG} {' '.join(path)}" for path, _, _ in leaves]
    width = max(len(name) for name in names)
    return [
        f"  {name.ljust(width)}  {help_text}\n"
        for name, (_, help_text, _) in zip(names, leaves, strict=True)
    ]
