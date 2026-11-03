"""CP-61: where and how an event happened, and the revision a server holds (§213, D-518).

Revision 7 of the contract lets an event say its harness, scope, Registry alias, an MCP's tool and
more, and a request what it was sent from. Each field is held only by the event types that can say
it, exactly as the server takes it; nothing of it reaches a server that did not say it holds
revision 7, so an older one never refuses an event for it.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import fields, replace
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    project_installation_receipt,
    receipt_detail_from_data,
    receipt_detail_to_data,
)
from aart_cli.application.execution import execute_installation
from aart_cli.application.installation_proposal import propose_installation
from aart_cli.application.telemetry_events import lifecycle_events
from aart_cli.domain.artifact_usage import InstalledName, UsageKind
from aart_cli.domain.harness import Scope
from aart_cli.domain.inspection import EnvironmentFacts
from aart_cli.domain.installation_owner import InstallationOwner
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.python_runtime import ArtifactEnvironment
from aart_cli.domain.result import Ok
from aart_cli.domain.telemetry import (
    CONTEXT_REVISION,
    AnswerKind,
    Environment,
    EventContext,
    TelemetryEvent,
    batch_document,
    environment_of,
    lifecycle_event,
    read_contract,
    use_event,
)
from tests.installation_proposal_test import (
    _launcher,
    _nothing_installed,
    _planned,
    _resolved,
    _selection,
)
from tests.installation_transaction_receipt_test import MOMENT as RECEIPT_MOMENT
from tests.installation_transaction_test import _Interpreter, _Lock, _matched

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "contract" / "telemetry-api-v1.examples.json"
CONTEXT_FIELDS = tuple(item.name for item in fields(EventContext))
ID = "7515ec68-1e98-46ca-bd90-9f6a70c84d11"
CLIENT = "0b6f4d1e-8f8a-4a43-9a52-2f0f5d0f6a11"
MOMENT = "2026-11-03T10:00:00.000000Z"
DIGEST = "sha256:" + "0f" * 32
SESSION = "5a1f0c2e-1b2c-4d3e-8f40-516273849a5b"

#: One value the contract takes for each field.
VALUES: dict[str, object] = {
    "harness": "opencode",
    "scope": "user",
    "registry": "company",
    "interface": "tui",
    "previous_version": "6.1.0",
    "via": "plugin",
    "collection": "starter-kit",
    "collection_version": "3.0.0",
    "package_digest": DIGEST,
    "duration_ms": 1500,
    "configuration_inputs": 2,
    "credential_inputs": 1,
    "tool": "create_issue",
    "session": SESSION,
}
LIFECYCLE = {"artifact.installed", "artifact.updated", "artifact.removed"}
PLACED = {"artifact.installed", "artifact.updated"}
USES = {"artifact.used", "unmanaged.used"}
#: The contract's table "Where and how (revision 7)", written out rather than read from the code.
HELD_IN = {
    "harness": LIFECYCLE | USES,
    "scope": LIFECYCLE | {"artifact.used"},
    "registry": LIFECYCLE | {"artifact.used"},
    "interface": LIFECYCLE,
    "previous_version": {"artifact.updated"},
    "via": LIFECYCLE,
    "collection": LIFECYCLE,
    "collection_version": LIFECYCLE,
    "package_digest": PLACED,
    "duration_ms": LIFECYCLE,
    "configuration_inputs": PLACED,
    "credential_inputs": PLACED,
    "tool": USES,
    "session": USES,
}


def _event(event_type: str, context: EventContext, **fields: object) -> TelemetryEvent:
    source = "opencode_plugin" if event_type in USES else "aart_cli"
    version = None if event_type == "unmanaged.used" else "6.2.0"
    document: dict = {
        "event_id": ID,
        "occurred_at": MOMENT,
        "event_type": event_type,
        "source": source,
        "artifact_id": "github",
        "artifact_type": "mcp",
        "artifact_version": version,
    }
    return TelemetryEvent(**(document | fields), context=context)


def _split(document: dict) -> tuple[dict, EventContext]:
    """An example event's own fields and its revision 7 context."""

    own = {key: value for key, value in document.items() if key not in CONTEXT_FIELDS}
    said = {key: value for key, value in document.items() if key in CONTEXT_FIELDS}
    return own, EventContext.from_document(said)


class TheExamplesTest(unittest.TestCase):
    def test_every_valid_example_is_a_request_this_client_could_send(self) -> None:
        for example in json.loads(EXAMPLES.read_text(encoding="utf-8"))["valid"]:
            request = example["request"]
            if any("failure" in event for event in request["events"]):
                continue
            with self.subTest(example["name"]):
                events = []
                for document in request["events"]:
                    own, context = _split(document)
                    events.append(TelemetryEvent(**own, context=context))
                environment = request.get("environment")
                self.assertEqual(
                    batch_document(
                        request["client_id"],
                        request["client_version"],
                        tuple(events),
                        automated=request.get("automated", False),
                        revision=CONTEXT_REVISION,
                        environment=None if environment is None else Environment(**environment),
                    ),
                    request,
                )

    def test_no_invalid_example_can_be_built(self) -> None:
        for example in json.loads(EXAMPLES.read_text(encoding="utf-8"))["invalid"]:
            with self.subTest(example["name"]), self.assertRaises((ValueError, TypeError)):
                own, context = _split(example["event"])
                TelemetryEvent(**own, context=context)


class WhereEachFieldIsHeldTest(unittest.TestCase):
    def test_a_field_is_held_exactly_by_the_event_types_that_can_say_it(self) -> None:
        self.assertEqual(set(HELD_IN), set(CONTEXT_FIELDS))
        for name in CONTEXT_FIELDS:
            for event_type in LIFECYCLE | USES:
                said = {name: VALUES[name]}
                if name in ("collection", "collection_version"):
                    said |= {"via": "collection", "collection": "starter-kit"}
                held = event_type in HELD_IN[name] and (
                    name not in ("collection", "collection_version") or event_type in HELD_IN["via"]
                )
                with self.subTest(name=name, event_type=event_type):
                    if held:
                        _event(event_type, EventContext.from_document(said))
                    else:
                        with self.assertRaises(ValueError):
                            _event(event_type, EventContext.from_document(said))

    def test_a_collection_a_tool_and_a_use_s_harness_follow_the_contract(self) -> None:
        for event_type, said, fields_ in (
            ("artifact.installed", {"collection": "starter-kit"}, {}),
            ("artifact.installed", {"via": "collection", "collection_version": "1.0.0"}, {}),
            ("artifact.used", {"tool": "search"}, {"artifact_type": "skill"}),
            ("artifact.used", {"harness": "claude"}, {}),
        ):
            with self.subTest(said), self.assertRaises(ValueError):
                _event(event_type, EventContext.from_document(said), **fields_)

    def test_a_value_out_of_its_shape_is_refused(self) -> None:
        for said in (
            {"scope": "global"},
            {"registry": "Company"},
            {"registry": "https://registry.example.invalid"},
            {"harness": "a" * 65},
            {"duration_ms": -1},
            {"duration_ms": 86_400_001},
            {"duration_ms": True},
            {"configuration_inputs": 1001},
            {"package_digest": "md5:abc"},
            {"previous_version": "6 1"},
        ):
            with self.subTest(said), self.assertRaises((ValueError, TypeError)):
                _event("artifact.updated", EventContext.from_document(said))

    @given(
        st.fixed_dictionaries(
            {},
            optional={
                "harness": st.sampled_from(("claude", "opencode", "codex", "a-b1")),
                "scope": st.sampled_from(("user", "project")),
                "registry": st.sampled_from(("company", "local-1", "c")),
                "interface": st.sampled_from(("tui", "cli")),
                "previous_version": st.sampled_from(("1.0.0", "2.0.0-rc.1")),
                "package_digest": st.just(DIGEST),
                "duration_ms": st.integers(0, 86_400_000),
                "configuration_inputs": st.integers(0, 1000),
                "credential_inputs": st.integers(0, 1000),
            },
        )
    )
    def test_a_context_is_read_back_from_its_document_as_it_was(self, said: dict) -> None:
        context = EventContext.from_document(said)
        event = _event("artifact.updated", context)

        self.assertEqual(EventContext.from_document(context.document()), context)
        self.assertEqual(context.document(), said)
        sent = batch_document(CLIENT, "0.29.0", (event,), revision=7)["events"]
        self.assertEqual({key: sent[0][key] for key in said}, said)


class TheRevisionTest(unittest.TestCase):
    def test_a_server_s_answer_is_its_revision_none_or_a_failure(self) -> None:
        for status, body, expected in (
            (200, {"schema_version": 1, "revision": 7}, 7),
            (200, {"schema_version": 1, "revision": 6, "other": True}, 6),
            (200, {"schema_version": 1, "revision": 9}, 9),
            (200, {"schema_version": 1}, None),
            (200, {"schema_version": 1, "revision": "7"}, None),
            (200, {"schema_version": 1, "revision": True}, None),
            (200, {"schema_version": 1, "revision": 5}, None),
            (200, {"schema_version": 2, "revision": 7}, None),
            (200, None, None),
            (404, {"detail": "Not Found"}, None),
            (405, None, None),
            (401, None, AnswerKind.UNAUTHORISED),
            (403, None, AnswerKind.UNAUTHORISED),
            (429, None, AnswerKind.UNAVAILABLE),
            (500, None, AnswerKind.UNAVAILABLE),
            (503, None, AnswerKind.UNAVAILABLE),
            (None, None, AnswerKind.UNAVAILABLE),
        ):
            with self.subTest(status=status, body=body):
                self.assertEqual(read_contract(status, body), expected)

    def test_below_revision_7_no_event_and_no_request_says_where_or_how(self) -> None:
        event = _event(
            "artifact.installed",
            EventContext(
                harness="opencode",
                scope="user",
                registry="company",
                interface="tui",
                via="collection",
                collection="starter-kit",
                package_digest=DIGEST,
                duration_ms=900,
            ),
        )
        environment = Environment("darwin", "arm64", "3.11.9")
        for revision in (None, 6):
            with self.subTest(revision=revision):
                document = batch_document(
                    CLIENT, "0.29.0", (event,), revision=revision, environment=environment
                )
                self.assertNotIn("environment", document)
                self.assertFalse(set(document["events"][0]) & set(CONTEXT_FIELDS))
        for revision in (7, 8):
            with self.subTest(revision=revision):
                document = batch_document(
                    CLIENT, "0.29.0", (event,), revision=revision, environment=environment
                )
                self.assertEqual(
                    document["environment"], {"os": "darwin", "arch": "arm64", "python": "3.11.9"}
                )
                self.assertEqual(document["events"][0]["registry"], "company")


class TheEnvironmentTest(unittest.TestCase):
    def test_a_platform_is_said_in_the_contract_s_words_or_not_at_all(self) -> None:
        for system, machine, python, expected in (
            ("Darwin", "arm64", "3.11.9", Environment("darwin", "arm64", "3.11.9")),
            ("Linux", "x86_64", "3.12.4", Environment("linux", "x86_64", "3.12.4")),
            ("Windows", "AMD64", "3.13.0", Environment("windows", "amd64", "3.13.0")),
            ("FreeBSD", "amd64", "3.11.9", Environment("other", "amd64", "3.11.9")),
            ("Linux", "", "3.11.9", None),
            ("Linux", "i686 (32-bit)", "3.11.9", None),
            ("Linux", "x86_64", "3.11.9 (main)", None),
        ):
            with self.subTest(system=system, machine=machine, python=python):
                self.assertEqual(environment_of(system, machine, python), expected)

    def test_an_environment_holds_nothing_else(self) -> None:
        for os_, arch, python in (
            ("plan9", "arm64", "3.11.9"),
            ("darwin", "ARM64", "3.11.9"),
            ("darwin", "a" * 17, "3.11.9"),
            ("darwin", "arm64", ""),
        ):
            with self.subTest(os=os_, arch=arch, python=python), self.assertRaises(ValueError):
                Environment(os_, arch, python)


class WhatAnEventSaysTest(unittest.TestCase):
    INSTALLED = (
        InstalledName("opencode", UsageKind.MCP, "jira", "corp/mcp/jira-mcp", "2.0.1"),
        InstalledName("claude", UsageKind.MCP, "jira", "corp/mcp/jira-mcp", "2.0.1"),
        InstalledName("claude", UsageKind.SKILL, "notes", "Not An Alias/skill/notes", "1.0.0"),
    )

    def test_an_install_says_its_registry_harness_and_scope(self) -> None:
        event = lifecycle_event(
            ID,
            MOMENT,
            "install",
            "corp/skill/release-notes@1.2.0",
            harness="claude",
            scope="project",
        )

        assert event is not None
        self.assertEqual(
            event.context, EventContext(harness="claude", scope="project", registry="corp")
        )

    def test_what_an_install_cannot_say_is_left_out_rather_than_losing_it(self) -> None:
        event = lifecycle_event(
            ID, MOMENT, "install", "Not An Alias/skill/notes@1.0.0", harness="Claude Code"
        )

        assert event is not None
        self.assertEqual(event.context, EventContext())

    def test_a_use_says_its_registry_and_an_mcp_s_tool_in_opencode(self) -> None:
        opencode = use_event(
            ID, MOMENT, "opencode", UsageKind.MCP, "jira_create_issue", self.INSTALLED
        )
        claude = use_event(ID, MOMENT, "claude", UsageKind.MCP, "jira", self.INSTALLED)
        unaliased = use_event(ID, MOMENT, "claude", UsageKind.SKILL, "notes", self.INSTALLED)

        assert opencode is not None and claude is not None and unaliased is not None
        self.assertEqual(opencode.context, EventContext(registry="corp", tool="create_issue"))
        self.assertEqual(claude.context, EventContext(registry="corp"))
        self.assertEqual(unaliased.context, EventContext())

    def test_a_use_nothing_installed_answers_to_says_only_an_opencode_tool_s_whole_name(
        self,
    ) -> None:
        unmanaged = use_event(
            ID, MOMENT, "opencode", UsageKind.MCP, "github_search", (), unmanaged=True
        )

        assert unmanaged is not None
        self.assertEqual(unmanaged.context, EventContext())


if __name__ == "__main__":
    unittest.main()


def _owned_outcome():
    """`_executed`'s transaction, its first member installed for Claude Code in a project."""

    first = _planned()
    owner = InstallationOwner(
        first.coordinate.source,
        first.coordinate.artifact,
        Scope.PROJECT,
        "/root",
        "claude",
    )
    owned = replace(first, owner=owner)
    second_artifact = _resolved("jira", version="2.0.0")
    environment = ArtifactEnvironment("mcp/jira", "/owned/aart/mcp/jira")
    second = _planned(
        second_artifact,
        environment=environment,
        launcher=_launcher(f"{environment.root}/launch"),
        registrations=(),
        dependencies=(f"{environment.payload}/requirements.txt", "requirements", "pip"),
    )
    proposed = propose_installation(
        (owned, second),
        _selection(owned.artifact, second.artifact),
        facts=EnvironmentFacts("darwin", ()),
        policy=EffectivePolicy(),
        observed=(
            (owned.coordinate, _nothing_installed(owned)),
            (second.coordinate, _nothing_installed(second)),
        ),
    )
    assert isinstance(proposed, Ok), getattr(proposed, "diagnostics", ())
    planned = (owned, second)
    calls = {item.coordinate: 0 for item in planned}
    before = {item.coordinate: _nothing_installed(item) for item in planned}
    after = {item.coordinate: _matched(item) for item in planned}

    def inspect(desired):
        calls[desired.artifact] += 1
        return before[desired.artifact] if calls[desired.artifact] < 3 else after[desired.artifact]

    executed = execute_installation(
        proposed.value,
        policy=EffectivePolicy(),
        interpreters=(_Interpreter(),),
        inspect=inspect,
        lock=_Lock(),
    )
    assert isinstance(executed, Ok), getattr(executed, "diagnostics", ())
    return executed.value


class WhatAReceiptSaysTest(unittest.TestCase):
    def test_a_member_s_harness_and_scope_are_kept_and_sent(self) -> None:
        receipt = project_installation_receipt(_owned_outcome(), recorded_at=RECEIPT_MOMENT)
        drawn = iter(range(10))

        events = lifecycle_events(receipt, lambda: f"00000000-0000-4000-8000-{next(drawn):012d}")

        first, second = receipt.artifacts
        self.assertEqual((first.harness, first.scope), ("claude", "project"))
        self.assertEqual((second.harness, second.scope), (None, None))
        self.assertEqual(receipt_detail_from_data(receipt_detail_to_data(receipt)), Ok(receipt))
        registry = first.coordinate.partition("/")[0]
        self.assertEqual(
            [event.context for event in events],
            [
                EventContext(harness="claude", scope="project", registry=registry),
                EventContext(registry=registry),
            ],
        )
