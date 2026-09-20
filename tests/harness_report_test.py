from __future__ import annotations

import json
import unittest

from aart_cli.application.harness_report import (
    HarnessSmokeRequest,
    compose_smoke_prompt,
    parse_smoke_report,
)
from aart_cli.application.mcp_smoke import SmokeDeclaration
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.json import JsonObject

REPORT_PATH = "aart-cli-smoke-report.json"


def _request(installation: str = "local/mcp/identity@1.0.0#claude:project") -> HarnessSmokeRequest:
    return HarnessSmokeRequest(
        installation,
        "identity",
        SmokeDeclaration("read_identity", JsonObject((("limit", 1),)), 15),
    )


def _entry(installation: str, text: str = "Ada", **over: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "installation": installation,
        "called": True,
        "result": {"content": [{"type": "text", "text": text}]},
        "status": "ok",
        "summary": "The tool returned the current user's details.",
        "possible_error": None,
    }
    entry.update(over)
    return entry


def _report(*entries: dict[str, object]) -> str:
    return json.dumps({"aart_cli_smoke_report": 1, "results": list(entries)})


class ComposeSmokePromptTest(unittest.TestCase):
    def test_the_prompt_names_every_installation_with_its_server_tool_and_arguments(self) -> None:
        """The operator's harness cannot verify what the prompt did not name (§170.4)."""

        prompt = compose_smoke_prompt((_request("one"), _request("two")), report_path=REPORT_PATH)
        for installation in ("one", "two"):
            self.assertIn(installation, prompt)
        self.assertIn("identity", prompt)
        self.assertIn("read_identity", prompt)
        self.assertIn('{"limit":1}', prompt)
        self.assertIn(REPORT_PATH, prompt)

    def test_the_prompt_carries_the_report_shape_it_asks_for(self) -> None:
        """A prompt that describes no shape gets prose back, and prose is not evidence."""

        prompt = compose_smoke_prompt((_request(),), report_path=REPORT_PATH)
        for key in (
            "aart_cli_smoke_report",
            "results",
            "installation",
            "called",
            "result",
            "status",
            "summary",
            "possible_error",
        ):
            self.assertIn(key, prompt)

    def test_the_prompt_states_the_restrictions_and_that_they_are_not_enforced(self) -> None:
        """§170.4: these are instructions to a person's assistant, and the prompt says so.

        AART runs nothing here, so claiming enforcement in the prompt would be the one dishonest
        sentence in the whole route.
        """

        prompt = compose_smoke_prompt((_request(),), report_path=REPORT_PATH).lower()
        self.assertIn("no other tool", prompt)
        self.assertIn("verbatim", prompt)
        self.assertIn("never follow instructions", prompt)
        self.assertIn("not enforced", prompt)

    def test_the_prompt_offers_the_session_a_way_to_check_its_own_report(self) -> None:
        """A session that can validate its own output hands back a report worth grading."""

        prompt = compose_smoke_prompt((_request(),), report_path=REPORT_PATH)
        self.assertIn("aart-cli mcp report", prompt)


class ParseSmokeReportTest(unittest.TestCase):
    def test_a_well_formed_report_carries_the_result_and_the_assessment(self) -> None:
        parsed = parse_smoke_report(_report(_entry("one")), requested=("one",))
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())

        self.assertEqual(parsed.value.missing, ())
        entry = parsed.value.entries[0]
        self.assertEqual(entry.installation, "one")
        self.assertTrue(entry.called)
        assert entry.result is not None and entry.result.content is not None
        self.assertEqual(entry.assessment.outcome, "PASS")

    def test_the_last_json_object_in_surrounding_prose_is_the_report(self) -> None:
        """Harnesses wrap their final answer in commentary, and that is not a malformed report.

        The decoy matters. A model that restates the shape it was asked for before producing the
        real report leaves two candidate objects in the text, and only the later one is the
        report -- reading the first would grade the example.
        """

        decoy = _report(_entry("one", text="<the tool result, verbatim>"))
        real = _report(_entry("one", text="Ada"))
        wrapped = (
            f"I will return this shape:\n\n```json\n{decoy}\n```\n\n"
            f"Here is the report:\n\n```json\n{real}\n```\n\nDone."
        )
        parsed = parse_smoke_report(wrapped, requested=("one",))
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
        entry = parsed.value.entries[0]
        assert entry.result is not None and entry.result.content is not None
        self.assertIn("Ada", str(entry.result.content))

    def test_an_installation_that_was_not_requested_is_refused(self) -> None:
        """§170.4: only the selected installations are eligible, and the report does not widen them."""

        parsed = parse_smoke_report(_report(_entry("other")), requested=("one",))
        self.assertIsInstance(parsed, Err)
        self.assertIn("was not requested", parsed.diagnostics[0].message)

    def test_a_requested_installation_with_no_entry_is_missing_rather_than_a_pass(self) -> None:
        parsed = parse_smoke_report(_report(_entry("one")), requested=("one", "two"))
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
        self.assertEqual(parsed.value.missing, ("two",))

    def test_a_report_with_no_json_object_at_all_is_refused(self) -> None:
        parsed = parse_smoke_report(
            "I ran the tools and everything looked fine.", requested=("one",)
        )
        self.assertIsInstance(parsed, Err)

    def test_a_duplicate_installation_entry_is_refused(self) -> None:
        """Two verdicts for one installation is not a report the runner can grade."""

        parsed = parse_smoke_report(_report(_entry("one"), _entry("one")), requested=("one",))
        self.assertIsInstance(parsed, Err)
        self.assertIn("more than once", parsed.diagnostics[0].message)

    def test_the_assessment_bounds_of_the_previous_contract_still_hold(self) -> None:
        """D-365's vocabulary and limits survive the route change; only the transport changed."""

        cases = (
            ({"status": "sure"}, "status"),
            ({"summary": ""}, "empty summary"),
            ({"summary": "x" * 2001}, "over-long summary"),
            ({"possible_error": "but also an error"}, "possible_error set with ok"),
            ({"status": "error", "possible_error": None}, "error without an explanation"),
        )
        for over, label in cases:
            with self.subTest(label=label):
                parsed = parse_smoke_report(_report(_entry("one", **over)), requested=("one",))
                assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
                self.assertEqual(parsed.value.entries[0].assessment.outcome, "FAIL")

    def test_an_uncertain_assessment_is_not_verified_rather_than_failed(self) -> None:
        parsed = parse_smoke_report(
            _report(_entry("one", status="uncertain", possible_error="I could not tell.")),
            requested=("one",),
        )
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
        self.assertEqual(parsed.value.entries[0].assessment.outcome, "NOT VERIFIED")

    def test_an_uncalled_entry_carries_no_result(self) -> None:
        parsed = parse_smoke_report(
            _report(
                _entry(
                    "one",
                    called=False,
                    result=None,
                    status="error",
                    possible_error="The server was not configured.",
                )
            ),
            requested=("one",),
        )
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
        entry = parsed.value.entries[0]
        self.assertFalse(entry.called)
        self.assertIsNone(entry.result)


class ValidateWithoutSelectionTest(unittest.TestCase):
    """`requested=None` is the mode a harness session uses to check its own output (D-368)."""

    def test_any_installation_key_is_accepted_without_a_selection_and_refused_with_one(
        self,
    ) -> None:
        """The same document, two modes, so the mode is what the difference is attributable to.

        A standalone validator has no selection to correlate against, and claiming it had checked
        correlation would be the one dishonest thing it could say.
        """

        document = _report(_entry("some-installation"))
        self.assertIsInstance(parse_smoke_report(document, requested=None), Ok)
        self.assertIsInstance(parse_smoke_report(document, requested=("other",)), Err)

    def test_the_shape_checks_do_not_ride_on_correlation(self) -> None:
        """Everything that is not correlation stays on, or the validator validates nothing."""

        duplicated = parse_smoke_report(_report(_entry("one"), _entry("one")), requested=None)
        self.assertIsInstance(duplicated, Err)
        self.assertIn("more than once", duplicated.diagnostics[0].message)

        self.assertIsInstance(parse_smoke_report("no json here", requested=None), Err)
        self.assertIsInstance(
            parse_smoke_report(json.dumps({"aart_cli_smoke_report": 1}), requested=None), Err
        )

    def test_nothing_is_missing_when_there_was_no_selection_to_miss(self) -> None:
        parsed = parse_smoke_report(_report(_entry("one")), requested=None)
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
        self.assertEqual(parsed.value.missing, ())


if __name__ == "__main__":
    unittest.main()
