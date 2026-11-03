"""§215, INV-333, INV-334, INV-336: what a failure record is, and what of it is sent.

`domain/failures.py` keeps of a failure only what the contract's `failure` object carries and
computes the fingerprint the server checks; `domain/telemetry.py` puts it in `aart_cli.failed`.
"""

from __future__ import annotations

import hashlib
import json
import string
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.domain.failures import (
    MAX_CAUSES,
    MAX_DIAGNOSTICS,
    MAX_FRAMES,
    Cause,
    Failure,
    FailureKind,
    failure_of,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import (
    FAILED,
    TelemetryEvent,
    batch_document,
    failure_event,
    parse_failures_sent,
)
from tests.telemetry_domain_test import CLIENT, ID, _examples

MOMENT = "2026-11-02T09:00:00.000000Z"
FRAMES = (
    ("aart_cli.cli", "main", 362),
    ("aart_cli.commands.marketplace", "_update", 1203),
)


def _crash(**changes: object) -> Failure | None:
    values: dict[str, object] = {
        "kind": FailureKind.CRASH,
        "place": "consume.update",
        "exception": "KeyError",
        "frames": FRAMES,
        "diagnostics": (),
        "exit_code": None,
        "python": "3.11.9",
        "platform": "darwin",
    }
    values.update(changes)
    return failure_of(**values)  # type: ignore[arg-type]


def _fingerprint(
    kind: str,
    place: str,
    exception: str,
    frames: list[str],
    codes: list[str],
    causes: list[tuple[str, list[str]]] | None = None,
) -> str:
    """The contract's digest, written out here as docs/telemetry-api-v1.md says it."""

    body: list[object] = [
        kind,
        place,
        exception,
        [frame.rsplit(":", 1)[0] for frame in frames],
        codes,
    ]
    if causes:
        body.append([[name, [frame.rsplit(":", 1)[0] for frame in held]] for name, held in causes])
    return hashlib.sha256(json.dumps(body, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


class WhatIsKeptTest(unittest.TestCase):
    def test_a_crash_keeps_its_kind_place_type_frames_and_versions(self) -> None:
        crash = _crash()
        assert crash is not None

        self.assertEqual(
            crash.document(),
            {
                "fingerprint": _fingerprint(
                    "crash",
                    "consume.update",
                    "KeyError",
                    ["aart_cli.cli:main:362", "aart_cli.commands.marketplace:_update:1203"],
                    [],
                ),
                "exception": "KeyError",
                "frames": ["aart_cli.cli:main:362", "aart_cli.commands.marketplace:_update:1203"],
                "diagnostics": [],
                "python": "3.11.9",
                "platform": "darwin",
            },
        )

    def test_only_frames_of_aart_cli_are_kept_and_at_most_the_innermost_thirty(self) -> None:
        frames = (
            ("runpy", "_run_module_as_main", 198),
            *((f"aart_cli.m{n}", "f", n + 1) for n in range(40)),
            ("json.decoder", "decode", 337),
            ("aart_clix.evil", "f", 1),
        )
        crash = _crash(frames=frames)
        assert crash is not None

        self.assertEqual(len(crash.frames), MAX_FRAMES)
        self.assertEqual(crash.frames[-1], "aart_cli.m39:f:40")
        self.assertEqual(crash.frames[0], "aart_cli.m10:f:11")

    def test_codes_of_the_contracts_form_are_kept_once_and_at_most_ten(self) -> None:
        codes = ("registry-unreachable", "registry-unreachable", "QA-017", "has space", "") + tuple(
            f"code-{n}" for n in range(20)
        )
        error = _crash(kind=FailureKind.ERROR, exception=None, frames=(), diagnostics=codes)
        assert error is not None

        self.assertEqual(error.diagnostics[0], "registry-unreachable")
        self.assertEqual(len(error.diagnostics), MAX_DIAGNOSTICS)
        self.assertNotIn("QA-017", error.diagnostics)

    def test_a_crash_with_an_unnamable_type_is_named_exception(self) -> None:
        crash = _crash(exception="not a name!")
        assert crash is not None

        self.assertEqual(crash.exception, "Exception")

    def test_a_place_or_platform_the_contract_cannot_carry_is_no_failure(self) -> None:
        for changes in (
            {"place": "consume update"},
            {"place": "Consume"},
            {"place": ""},
            {"platform": "win32"},
            {"exit_code": 256},
            {"exit_code": True},
            {"python": ""},
        ):
            with self.subTest(changes):
                self.assertIsNone(_crash(**changes))


class TheFingerprintTest(unittest.TestCase):
    def test_moving_lines_keeps_it_and_another_function_changes_it(self) -> None:
        moved = _crash(frames=(("aart_cli.cli", "main", 400), FRAMES[1]))
        other = _crash(frames=(("aart_cli.cli", "main", 362), ("aart_cli.cli", "_run", 9)))

        self.assertEqual(moved.fingerprint, _crash().fingerprint)  # type: ignore[union-attr]
        self.assertNotEqual(other.fingerprint, _crash().fingerprint)  # type: ignore[union-attr]

    def test_a_document_with_another_fingerprint_is_refused(self) -> None:
        document = _crash().document()  # type: ignore[union-attr]
        document["fingerprint"] = "0" * 16

        self.assertIsInstance(Failure.from_document("crash", "consume.update", document), Err)


class TheCausesTest(unittest.TestCase):
    """B-267: what the exception was raised from, or while handling, in order."""

    CAUSES = (
        (
            "aart_cli.io.receipt_store.ReceiptUnwritable",
            (("aart_cli.io.receipt_store", "record", 301),),
        ),
        ("PermissionError", (("pathlib", "open", 1), ("aart_cli.io.receipt_store", "_write", 412))),
    )

    def test_each_cause_keeps_its_type_and_aart_clis_frames_in_order(self) -> None:
        crash = _crash(causes=self.CAUSES)
        assert crash is not None

        self.assertEqual(
            crash.causes,
            (
                Cause(
                    "aart_cli.io.receipt_store.ReceiptUnwritable",
                    ("aart_cli.io.receipt_store:record:301",),
                ),
                Cause("PermissionError", ("aart_cli.io.receipt_store:_write:412",)),
            ),
        )
        document = crash.document()
        self.assertEqual(
            document["causes"],
            [
                {
                    "exception": "aart_cli.io.receipt_store.ReceiptUnwritable",
                    "frames": ["aart_cli.io.receipt_store:record:301"],
                },
                {
                    "exception": "PermissionError",
                    "frames": ["aart_cli.io.receipt_store:_write:412"],
                },
            ],
        )
        self.assertEqual(
            crash.fingerprint,
            _fingerprint(
                "crash",
                "consume.update",
                "KeyError",
                list(crash.frames),
                [],
                [(cause.exception, list(cause.frames)) for cause in crash.causes],
            ),
        )
        self.assertEqual(Failure.from_document("crash", "consume.update", document), Ok(crash))

    def test_without_causes_the_document_and_fingerprint_are_what_they_were(self) -> None:
        crash = _crash(causes=())
        assert crash is not None

        self.assertNotIn("causes", crash.document())
        self.assertEqual(crash, _crash())

    def test_a_cause_is_part_of_the_defect_and_its_lines_are_not(self) -> None:
        crash = _crash(causes=self.CAUSES)
        moved = _crash(
            causes=(
                (self.CAUSES[0][0], (("aart_cli.io.receipt_store", "record", 999),)),
                self.CAUSES[1],
            )
        )
        swapped = _crash(causes=self.CAUSES[::-1])
        fewer = _crash(causes=self.CAUSES[:1])
        assert crash is not None and moved is not None and swapped is not None
        assert fewer is not None

        self.assertEqual(moved.fingerprint, crash.fingerprint)
        self.assertEqual(
            len({crash.fingerprint, swapped.fingerprint, fewer.fingerprint, _crash().fingerprint}),  # type: ignore[union-attr]
            4,
        )

    def test_at_most_five_are_kept_the_nearest_first_and_unnamable_ones_are_exception(self) -> None:
        many = tuple((f"E{n}", ()) for n in range(8))
        crash = _crash(causes=(("not a name!", ()), *many))
        assert crash is not None

        self.assertEqual(len(crash.causes), MAX_CAUSES)
        self.assertEqual(
            [cause.exception for cause in crash.causes], ["Exception", "E0", "E1", "E2", "E3"]
        )

    def test_only_a_failure_that_names_its_exception_has_causes(self) -> None:
        error = _crash(kind=FailureKind.ERROR, exception=None, causes=self.CAUSES)
        assert error is not None

        self.assertEqual(error.causes, ())
        with self.assertRaises(ValueError):
            Failure(
                FailureKind.ERROR,
                "tui",
                None,
                (),
                (),
                None,
                "3.11.9",
                "linux",
                (Cause("OSError", ()),),
            )

    def test_a_causes_document_the_contract_refuses_is_refused(self) -> None:
        good = _crash(causes=self.CAUSES).document()  # type: ignore[union-attr]
        for causes in (
            [],
            [{"exception": "OSError", "frames": []}] * 6,
            [{"exception": "OSError: [Errno 13]", "frames": []}],
            [{"exception": "OSError", "frames": ["pathlib:open:1"]}],
            [{"exception": "OSError"}],
            [{"exception": "OSError", "frames": [], "message": PRIVATE_TEXT}],
            ["OSError"],
            {"exception": "OSError", "frames": []},
        ):
            with self.subTest(causes=causes):
                document = {**good, "causes": causes}
                # Each with the fingerprint its causes would have, so only the rule refuses it.
                document["fingerprint"] = _fingerprint(
                    "crash",
                    "consume.update",
                    "KeyError",
                    list(good["frames"]),  # type: ignore[call-overload]
                    [],
                    [
                        (str(item.get("exception")), list(item.get("frames", [])))
                        for item in causes
                        if isinstance(item, dict)
                    ],
                )
                self.assertIsInstance(
                    Failure.from_document("crash", "consume.update", document), Err
                )


PRIVATE_TEXT = "[Errno 13] Permission denied: '/Users/someone/.aart-cli'"


_PLACES = st.from_regex(r"[a-z0-9][a-z0-9._-]{0,20}", fullmatch=True)
_FUNCTIONS = st.from_regex(r"[A-Za-z_<>][A-Za-z0-9_<>]{0,8}", fullmatch=True)
_FRAMES = st.lists(
    st.tuples(
        st.from_regex(r"aart_cli(\.[a-z_]{1,6}){0,2}", fullmatch=True),
        _FUNCTIONS,
        st.integers(1, 99999),
    ),
    max_size=5,
)
_CODES = st.lists(st.from_regex(r"[a-z0-9][a-z0-9.-]{0,10}", fullmatch=True), max_size=4)


@given(
    kind=st.sampled_from(FailureKind),
    place=_PLACES,
    frames=_FRAMES,
    codes=_CODES,
    lines=st.integers(1, 99999),
)
def test_the_fingerprint_is_the_same_exactly_when_all_but_the_lines_are(
    kind: FailureKind, place: str, frames: list, codes: list, lines: int
) -> None:
    """INV-334 over every failure: lines never change it; it is the contract's own digest."""

    failure = failure_of(kind, place, "KeyError", tuple(frames), tuple(codes), 1, "3.11.9", "linux")
    assert failure is not None
    shifted = failure_of(
        kind,
        place,
        "KeyError",
        tuple((module, function, lines) for module, function, _ in frames),
        tuple(codes),
        1,
        "3.11.9",
        "linux",
    )
    assert shifted is not None and shifted.fingerprint == failure.fingerprint
    assert failure.fingerprint == _fingerprint(
        kind.value, place, "KeyError", list(failure.frames), list(failure.diagnostics)
    )
    assert Failure.from_document(kind.value, place, failure.document()) == Ok(failure)


_TEXT = st.text(alphabet=string.printable, max_size=40)


@given(
    exception=_TEXT,
    module=_TEXT,
    function=_TEXT,
    code=_TEXT,
)
def test_whatever_it_is_given_only_the_contracts_shapes_are_kept(
    exception: str, module: str, function: str, code: str
) -> None:
    """INV-333: free text cannot ride in a kept field; what is kept is a document the server takes."""

    failure = failure_of(
        FailureKind.CRASH,
        "tui",
        exception,
        ((module, function, 1),),
        (code,),
        None,
        "3.11.9",
        "other",
    )
    assert failure is not None
    assert Failure.from_document("crash", "tui", failure.document()) == Ok(failure)
    for frame in failure.frames:
        assert frame.startswith("aart_cli")
    for kept in (failure.exception or "", *failure.diagnostics):
        assert " " not in kept and "/" not in kept


@given(
    causes=st.lists(
        st.tuples(_TEXT, st.lists(st.tuples(_TEXT, _TEXT, st.integers(-1, 10**7)), max_size=3)),
        max_size=7,
    ),
    frames=_FRAMES,
)
def test_whatever_causes_it_is_given_the_document_is_one_the_server_takes(
    causes: list, frames: list
) -> None:
    """INV-333 for causes: only type names and aart-cli's frames, at most five, each as the
    contract's digest counts it."""

    failure = failure_of(
        FailureKind.CRASH,
        "tui",
        "RuntimeError",
        tuple(frames),
        (),
        None,
        "3.11.9",
        "other",
        causes=tuple((name, tuple(held)) for name, held in causes),
    )
    assert failure is not None
    assert len(failure.causes) == min(len(causes), MAX_CAUSES)
    for cause in failure.causes:
        assert " " not in cause.exception and "/" not in cause.exception
        assert all(frame.startswith("aart_cli") for frame in cause.frames)
    assert Failure.from_document("crash", "tui", failure.document()) == Ok(failure)
    assert failure.fingerprint == _fingerprint(
        "crash",
        "tui",
        "RuntimeError",
        list(failure.frames),
        [],
        [(cause.exception, list(cause.frames)) for cause in failure.causes],
    )


class TheEventTest(unittest.TestCase):
    def test_a_failure_is_sent_as_aart_cli_failed_without_a_version(self) -> None:
        event = failure_event(ID, MOMENT, _crash())  # type: ignore[arg-type]

        document = batch_document(CLIENT, "0.24.0", (event,))["events"][0]  # type: ignore[index]
        self.assertEqual(document["event_type"], FAILED)
        self.assertEqual(document["source"], "aart_cli")
        self.assertEqual(
            (document["artifact_type"], document["artifact_id"]), ("crash", "consume.update")
        )
        self.assertNotIn("artifact_version", document)
        self.assertEqual(document["failure"]["exception"], "KeyError")

    def test_a_failure_belongs_to_aart_cli_failed_and_nothing_else_has_one(self) -> None:
        crash = _crash()
        for event_type, source, failure, version in (
            ("artifact.used", "claude_hook", crash, None),
            (FAILED, "aart_cli", None, None),
            (FAILED, "claude_hook", crash, None),
            (FAILED, "aart_cli", crash, "1.0.0"),
        ):
            with self.subTest(event_type=event_type, source=source), self.assertRaises(ValueError):
                TelemetryEvent(
                    ID, MOMENT, event_type, source, "consume.update", "crash", version, failure
                )

    def test_the_contracts_failure_examples_are_events_this_client_could_send(self) -> None:
        examples = [
            example
            for example in _examples()["valid"]
            if any(event["event_type"] == FAILED for event in example["request"]["events"])
        ]
        self.assertTrue(examples)
        for example in examples:
            request = example["request"]
            events = []
            for event in request["events"]:
                failure = Failure.from_document(
                    event["artifact_type"], event["artifact_id"], event["failure"]
                )
                assert isinstance(failure, Ok), failure
                events.append(failure_event(event["event_id"], event["occurred_at"], failure.value))
            self.assertEqual(
                batch_document(request["client_id"], request["client_version"], tuple(events)),
                request,
            )

    def test_no_invalid_failure_example_can_be_built(self) -> None:
        checked = 0
        for example in _examples()["invalid"]:
            event = example["event"]
            if "failure" not in event and event["event_type"] != FAILED:
                continue
            checked += 1
            with self.subTest(example["name"]):
                read = Failure.from_document(
                    event["artifact_type"], event["artifact_id"], event.get("failure")
                )
                if isinstance(read, Err):
                    continue
                with self.assertRaises(ValueError):
                    TelemetryEvent(
                        event["event_id"],
                        event["occurred_at"],
                        event["event_type"],
                        event["source"],
                        event["artifact_id"],
                        event["artifact_type"],
                        event.get("artifact_version"),
                        read.value,
                    )
        self.assertEqual(checked, 9)


class TheBuildsChoiceTest(unittest.TestCase):
    def test_unset_and_on_send_off_does_not_anything_else_is_refused(self) -> None:
        for raw, sent in (
            ("", True),
            (" ON ", True),
            ("true", True),
            ("off", False),
            ("FALSE", False),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(parse_failures_sent(raw), Ok(sent))
        self.assertIsInstance(parse_failures_sent("sometimes"), Err)


if __name__ == "__main__":
    unittest.main()
