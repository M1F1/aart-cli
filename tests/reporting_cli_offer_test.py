"""The usage-report offer on the surface that reaches a person: `aart marketplace install`.

Reporting is optional and redacted, and the offer is the only place a person decides whether any
of it leaves the machine.  Three properties make that decision real rather than nominal: consent
defaults to no, the exact bytes are shown before anything opens, and a failure to report never
changes the marketplace outcome.  They were pinned on the legacy wizard's offer, which nothing
reaches any more; the CLI carries the offer now (D-117), so they are pinned here.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from agent_artifacts.commands import marketplace
from agent_artifacts.configuration.model import ReportingMode
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.reporting.application import (
    RegistryReportingRoute,
    ReportingApplicationService,
)
from agent_artifacts.reporting.model import (
    ReportingDestination,
    ReportingSubmission,
    UsageReport,
    UsageResult,
)
from agent_artifacts.reporting.projection import RegistryUsageReport


def _event() -> UsageReport:
    return UsageReport(
        "1.0.0a1",
        "cli",
        "darwin",
        "install",
        (
            UsageResult(
                "skill",
                "review",
                "codex",
                "project",
                "copy",
                ("copy",),
                "changed",
                "not-required",
            ),
        ),
    )


def _failure() -> Err:
    return Err(
        (
            Diagnostic(
                DiagnosticCode("reporting-provider-failed"),
                Severity.ERROR,
                "provider unavailable",
            ),
        )
    )


def _rendered(reporting: marketplace._CliReporting | None, answers: tuple[str, ...] = ()) -> str:
    """Render one offer with stdin interactive and a scripted answer per prompt."""

    scripted = iter(answers)

    def read(prompt: str) -> str:
        try:
            return next(scripted)
        except StopIteration:  # pragma: no cover - a prompt the test did not expect
            raise AssertionError(f"unexpected prompt: {prompt}") from None

    stream = io.StringIO()
    with patch.object(marketplace.sys.stdin, "isatty", lambda: True):
        with patch("builtins.input", read):
            with redirect_stdout(stream):
                marketplace._render_cli_reporting(reporting)
    return stream.getvalue()


class CliReportingOfferTest(unittest.TestCase):
    def test_nothing_prepared_prompts_nothing_previews_nothing_and_calls_no_provider(self) -> None:
        service = ReportingApplicationService(
            None,
            lambda _plan: self.fail("browser provider used with nothing prepared"),
            lambda _plan: self.fail("authenticated provider used with nothing prepared"),
        )

        self.assertEqual(_rendered(None), "")
        self.assertEqual(_rendered(marketplace._CliReporting(service)), "")

    def test_prompt_defaults_to_no_then_previews_exact_payload_before_the_browser(self) -> None:
        calls: list[bytes] = []
        destination = ReportingDestination(ReportingMode.PROMPT, "github.com", "org/registry")
        service = ReportingApplicationService(
            destination,
            lambda plan: calls.append(plan.payload) or Ok(ReportingSubmission("browser-opened")),
            lambda _plan: self.fail("authenticated provider used in prompt mode"),
        )
        prepared = service.prepare_routed(_event(), ())
        assert isinstance(prepared, Ok)
        offer = marketplace._CliReporting(service, prepared.value)

        # Pressing return is a refusal, not an acceptance: nothing is previewed and nothing opens.
        declined = _rendered(offer, ("",))
        self.assertEqual(calls, [])
        self.assertNotIn("Exact redacted", declined)
        self.assertIn("Usage report was not submitted.", declined)

        accepted = _rendered(offer, ("y", "y"))
        self.assertEqual(len(calls), 1)
        payload = calls[0].decode("utf-8").strip()
        self.assertIn(payload, accepted)
        self.assertLess(
            accepted.index(payload),
            accepted.index("Usage report opened in the browser."),
            "the exact payload has to be readable before anything opens",
        )

    def test_the_second_prompt_still_stops_a_report_the_first_one_accepted(self) -> None:
        # The preview exists to be acted on. Agreeing to see the bytes is not agreeing to send
        # them, so the answer after the preview has to be able to stop the submission.
        destination = ReportingDestination(ReportingMode.PROMPT, "github.com", "org/registry")
        service = ReportingApplicationService(
            destination,
            lambda _plan: self.fail("browser opened after the preview was declined"),
            lambda _plan: self.fail("authenticated provider used in prompt mode"),
        )
        prepared = service.prepare_routed(_event(), ())
        assert isinstance(prepared, Ok)

        rendered = _rendered(marketplace._CliReporting(service, prepared.value), ("y", ""))

        self.assertIn("Exact redacted usage report payload:", rendered)
        self.assertIn("Usage report was not submitted.", rendered)

    def test_a_non_interactive_stdin_is_a_refusal_rather_than_an_unanswered_prompt(self) -> None:
        destination = ReportingDestination(ReportingMode.PROMPT, "github.com", "org/registry")
        service = ReportingApplicationService(
            destination,
            lambda _plan: self.fail("browser opened without anybody to consent"),
            lambda _plan: self.fail("authenticated provider used in prompt mode"),
        )
        prepared = service.prepare_routed(_event(), ())
        assert isinstance(prepared, Ok)
        stream = io.StringIO()

        with patch.object(marketplace.sys.stdin, "isatty", lambda: False):
            with patch("builtins.input", lambda _prompt: self.fail("prompted a pipe")):
                with redirect_stdout(stream):
                    marketplace._render_cli_reporting(
                        marketplace._CliReporting(service, prepared.value)
                    )

        self.assertIn("stdin is not interactive", stream.getvalue())
        self.assertNotIn("Exact redacted", stream.getvalue())

    def test_an_automatic_failure_is_a_warning_only_and_never_prompts(self) -> None:
        destination = ReportingDestination(ReportingMode.AUTOMATIC, "github.com", "org/registry")
        service = ReportingApplicationService(
            destination,
            lambda _plan: self.fail("browser provider used in automatic mode"),
            lambda _plan: _failure(),
        )
        prepared = service.prepare_routed(_event(), ())
        assert isinstance(prepared, Ok)

        rendered = _rendered(marketplace._CliReporting(service, prepared.value))

        self.assertIn("warning: usage report submission failed", rendered)
        self.assertIn("the marketplace outcome is unchanged", rendered)
        self.assertIn('"report_type":"aart-usage-session"', rendered)

    def test_every_registry_destination_is_named_and_each_defaults_to_no(self) -> None:
        first = ReportingDestination(ReportingMode.PROMPT, "github.com", "org/one")
        second = ReportingDestination(ReportingMode.PROMPT, "github.com", "org/two")
        service = ReportingApplicationService(
            None,
            lambda _plan: self.fail("browser opened for a destination nobody accepted"),
            lambda _plan: self.fail("automatic provider used for a registry prompt"),
            (
                RegistryReportingRoute(SourceAlias("one"), first),
                RegistryReportingRoute(SourceAlias("two"), second),
            ),
        )
        event = _event()
        routed = (
            RegistryUsageReport(SourceAlias("one"), event),
            RegistryUsageReport(SourceAlias("two"), event),
        )
        prepared = service.prepare_routed(event, routed)
        assert isinstance(prepared, Ok)
        self.assertEqual(len(prepared.value), 2)

        rendered = _rendered(marketplace._CliReporting(service, prepared.value), ("", ""))

        self.assertIn("github.com/org/one", rendered)
        self.assertIn("github.com/org/two", rendered)
        self.assertNotIn("Exact redacted", rendered)

    def test_a_registry_without_an_advertisement_says_why_no_offer_appears(self) -> None:
        # Silence here reads as a registry that wants no reports; the reason is that it advertises
        # no service to send them to, which is the registry's omission and not the user's choice.
        service = ReportingApplicationService(
            None,
            lambda _plan: self.fail("browser provider called without a route"),
            lambda _plan: self.fail("automatic provider called without a route"),
        )
        notice = (
            "Usage report not offered for registry reference: it does not advertise a "
            "usage_reporting service."
        )

        rendered = _rendered(marketplace._CliReporting(service, (), (notice,)))

        self.assertEqual(rendered, f"{notice}\n")


if __name__ == "__main__":
    unittest.main()
