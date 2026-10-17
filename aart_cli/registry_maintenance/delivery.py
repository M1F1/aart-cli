"""What installing a package delivers, for a kind where that is not the whole payload.

`registry audit` runs this over every package: an `mcp` descriptor that launches a payload file, or
declares no server, installs successfully and cannot start on any consumer machine.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from aart_cli.domain.identifiers import ArtifactIdentity
from aart_cli.domain.result import Err
from aart_cli.protocol.json import JsonArray, JsonObject, parse_json

_PAYLOAD_ROOT = "payload"


@dataclass(frozen=True, slots=True)
class DeliveryFinding:
    """What installing this artifact actually delivers, for a type where that is not all of it.

    Installing applies the effects the type declares. For `mcp` those effects touch one file of the
    payload, so the package's bytes and the delivered bytes are different sets — and a descriptor
    naming a file inside the payload names one that will not be on the consumer's machine.
    """

    withheld: int
    referenced: tuple[str, ...]
    note: str
    # True when the descriptor declares no `server` object at all: the merge still runs and writes
    # an empty entry, so the artifact installs successfully and starts nothing.
    starts_nothing: bool = False


def _names_payload_file(raw: str, payload: Mapping[str, bytes]) -> bool:
    """Does this descriptor string name a file inside the payload?

    Deliberately narrow: only a string that resolves to a file actually present under `payload/`
    counts. Refusing anything that merely looks like a path would be refusing for a guess, and an
    MCP server legitimately launched from an absolute path outside the package is none of AART's
    business.
    """

    candidate = raw.removeprefix("./")
    return candidate in payload or f"{_PAYLOAD_ROOT}/{candidate}" in payload


def describe_delivery(kind: str, payload: Mapping[str, bytes]) -> DeliveryFinding | None:
    """What a consumer receives from this payload, or `None` where they receive all of it.

    `skill` and `hook` copy the payload tree; `guideline` and `memory` write the one document that
    is the whole payload. `mcp` merges the `server` object out of `payload/mcp.json` and copies
    nothing, which is the case worth reporting.
    """

    if kind != "mcp":
        return None
    document = payload.get(f"{_PAYLOAD_ROOT}/mcp.json")
    withheld = sum(1 for path in payload if path != f"{_PAYLOAD_ROOT}/mcp.json")
    note = (
        "installing this artifact merges the server entry from payload/mcp.json into the "
        f"profile's MCP file and copies nothing; {withheld} payload "
        f"{'file is' if withheld == 1 else 'files are'} not delivered to consumers"
    )
    if document is None:
        return DeliveryFinding(withheld, (), note)
    parsed = parse_json(document)
    if isinstance(parsed, Err) or not isinstance(parsed.value, JsonObject):
        # An unparsable descriptor is refused by the loader that reads it; saying so twice, in
        # different words, would send the maintainer looking for two faults.
        return DeliveryFinding(withheld, (), note)
    server = parsed.value.get("server")
    values: list[str] = []
    if isinstance(server, JsonObject):
        command = server.get("command")
        if isinstance(command, str):
            values.append(command)
        arguments = server.get("args")
        if isinstance(arguments, JsonArray):
            values.extend(item for item in arguments.items if isinstance(item, str))
    return DeliveryFinding(
        withheld,
        tuple(sorted({item for item in values if _names_payload_file(item, payload)})),
        note,
        # An `aart-cli-mcp-v1` descriptor is `{"name": …, "server": {…}}`.  A document shaped like the
        # harness file it ends up in — `{"mcpServers": {…}}` — parses, loads, installs, and merges
        # an empty object: the artifact is delivered and starts nothing.
        starts_nothing=not isinstance(server, JsonObject) or not server.entries,
    )


def mcp_descriptor_message(identity: ArtifactIdentity) -> str:
    """The one sentence for a descriptor that installs successfully and starts nothing."""

    return (
        f"mcp descriptor declares no server, so installing it "
        f'writes an empty entry: {identity} needs payload/mcp.json shaped {{"name": …, '
        f'"server": {{"command": …}}}}; a document shaped like the harness file it merges into '
        "installs and starts nothing"
    )


def delivery_reference_message(identity: ArtifactIdentity, finding: DeliveryFinding) -> str:
    """The one sentence for a configuration that cannot work on any consumer machine."""

    named = ", ".join(finding.referenced)
    return (
        f"mcp descriptor names a payload file consumers never receive: "
        f"{identity} launches {named}, and installing this artifact writes only the server entry "
        "from payload/mcp.json. State a command the consumer's machine already resolves"
    )
