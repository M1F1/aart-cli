"""`registry audit` says what a consumer receives from an `mcp` package, and what cannot run.

Installing an `mcp` writes exactly one thing: the server entry merged into the harness's MCP file.
The rest of the payload stays in the Registry, so a descriptor whose command names a file inside the
payload names a file that will never be on the consumer's machine, and a descriptor with no server
installs an empty entry.

`mcp` is the only kind where the shipped set and the delivered set differ, so it is the only kind
with a finding here; the tests hold that boundary in both directions.
"""

from __future__ import annotations

import json
import unittest

from aart_cli.domain.identifiers import ArtifactIdentity
from aart_cli.registry_maintenance.delivery import (
    delivery_reference_message,
    describe_delivery,
    mcp_descriptor_message,
)


def _descriptor(command: str, *arguments: str) -> bytes:
    return (
        json.dumps(
            {"name": "atlassian", "server": {"command": command, "args": list(arguments)}}
        ).encode()
        + b"\n"
    )


def _payload(document: bytes) -> dict[str, bytes]:
    """A package payload with its descriptor beside the files it ships."""

    return {
        "payload/mcp.json": document,
        "payload/index.js": b"console.log('serve');\n",
        "payload/install.sh": b"#!/bin/sh\nexit 0\n",
        "payload/lib/client.js": b"export const client = 1;\n",
    }


class DeliveryDescriptionTest(unittest.TestCase):
    def test_a_command_naming_a_payload_file_is_reported(self) -> None:
        finding = describe_delivery("mcp", _payload(_descriptor("node", "payload/index.js")))
        assert finding is not None
        self.assertEqual(finding.referenced, ("payload/index.js",))
        self.assertEqual(finding.withheld, 3)

    def test_a_payload_relative_path_counts_too(self) -> None:
        """`node index.js` names the same file as `node payload/index.js` and works no better."""

        finding = describe_delivery("mcp", _payload(_descriptor("node", "./index.js")))
        assert finding is not None
        self.assertEqual(finding.referenced, ("./index.js",))

    def test_a_command_the_consumer_resolves_is_not_a_finding(self) -> None:
        finding = describe_delivery("mcp", _payload(_descriptor("npx", "-y", "@example/srv")))
        assert finding is not None
        self.assertEqual(finding.referenced, ())
        self.assertIn("copies nothing", finding.note)

    def test_a_path_that_is_not_in_the_payload_is_not_a_finding(self) -> None:
        """Narrow by construction: refusing anything path-shaped would refuse for a guess."""

        finding = describe_delivery("mcp", _payload(_descriptor("./scripts/run.sh")))
        assert finding is not None
        self.assertEqual(finding.referenced, ())

    def test_types_that_deliver_their_whole_payload_have_no_finding(self) -> None:
        for kind in ("skill", "guideline", "memory", "hook"):
            with self.subTest(kind=kind):
                self.assertIsNone(describe_delivery(kind, _payload(_descriptor("node"))))

    def test_a_descriptor_shaped_like_the_harness_file_starts_nothing(self) -> None:
        """`{"mcpServers": …}` parses, loads, installs, and merges an empty entry.

        It is the shape of the file the entry is merged *into*, which is why it is the mistake
        everyone makes — this repository's own vendoring fixtures made it, and so does the `2.3.0`
        tutorial.
        """

        document = json.dumps({"mcpServers": {"atlassian": {"command": "npx"}}}).encode() + b"\n"
        finding = describe_delivery("mcp", _payload(document))
        assert finding is not None
        self.assertTrue(finding.starts_nothing)
        message = mcp_descriptor_message(ArtifactIdentity("mcp", "atlassian"))
        self.assertIn('"server"', message)

    def test_a_declared_server_is_not_reported_as_starting_nothing(self) -> None:
        finding = describe_delivery("mcp", _payload(_descriptor("npx", "-y", "@example/srv")))
        assert finding is not None
        self.assertFalse(finding.starts_nothing)

    def test_an_empty_server_object_starts_nothing_too(self) -> None:
        document = json.dumps({"name": "atlassian", "server": {}}).encode() + b"\n"
        finding = describe_delivery("mcp", _payload(document))
        assert finding is not None
        self.assertTrue(finding.starts_nothing)

    def test_the_message_names_the_command_and_what_is_actually_installed(self) -> None:
        finding = describe_delivery("mcp", _payload(_descriptor("node", "payload/index.js")))
        assert finding is not None
        message = delivery_reference_message(ArtifactIdentity("mcp", "atlassian"), finding)
        self.assertIn("payload/index.js", message)
        self.assertIn("only the server entry from payload/mcp.json", message)


if __name__ == "__main__":
    unittest.main()
