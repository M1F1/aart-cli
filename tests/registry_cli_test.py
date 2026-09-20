from __future__ import annotations

import unittest
from unittest.mock import patch

from aart_cli import __version__, cli
from aart_cli.commands import registry as registry_command
from aart_cli.curation.model import CurationAction
from aart_cli.domain.result import Ok
from aart_cli.model import Request
from aart_cli.protocol.semver import VersionBounds, parse_semver

_VENDOR = (
    "registry vendor --source /tmp/registry mcp atlassian --url https://example.com/up.git "
    "--path artifacts/mcp/atlassian --artifact-version 1.2.0 --summary One. "
    "--profile claude --platform darwin"
)
_FORMAT = "registry format --source /tmp/registry"


class RegistryCliTest(unittest.TestCase):
    def test_all_registry_actions_map_to_one_command_boundary(self) -> None:
        parser = cli.build_parser()
        actions = {
            "init",
            "collection",
            "scan",
            "adopt",
            "check-upstream",
            "promote",
            "discover",
            "format",
            "publish",
            "push",
            "vendor",
            "vendor-batch",
            "revendor",
            "validate",
            "lock",
            "build",
            "audit",
            "test",
            "diff",
        }
        registry = next(
            action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
        ).choices["registry"]
        sub = next(
            action
            for action in registry._actions
            if action.__class__.__name__ == "_SubParsersAction"
        )
        self.assertEqual(set(sub.choices), actions)
        self.assertIn("registry", cli.DISPATCH)

    def test_format_check_and_json_are_preserved_in_request(self) -> None:
        captured: list[Request] = []

        def run(request: Request) -> int:
            captured.append(request)
            return 0

        with patch.dict(cli.DISPATCH, {"registry": run}):
            result = cli.main(
                ["registry", "format", "--source", "/tmp/registry", "--check", "--json"]
            )
        self.assertEqual(result, 0)
        self.assertEqual(captured[0].registry_action, "format")
        self.assertEqual(captured[0].source_dir, "/tmp/registry")
        self.assertTrue(captured[0].check)
        self.assertTrue(captured[0].json)

    def test_init_rejects_the_withdrawn_usage_reporting_option(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            cli.build_parser().parse_args(
                [
                    "registry",
                    "init",
                    "--source-id",
                    "company",
                    "--display-name",
                    "Company",
                    "--usage-reporting-repository",
                    "acme/agent-artifacts-registry",
                ]
            )
        self.assertEqual(raised.exception.code, 2)

    def test_registry_scaffold_is_withdrawn_but_publish_remains_the_canonical_aggregate(
        self,
    ) -> None:
        """CP-26 step 2 removes in-registry authoring, not the canonical publication aggregate.

        `scaffold` wrote a compiled package by hand, which no canonical package may be: each one
        carries a `provenance.json` whose origin names the revision it was compiled from, and an
        artifact authored in place has none. Authoring belongs in a source checkout, reached by
        `scan` and `promote`. `publish` remains the reviewed build/validate/audit/commit aggregate
        for that approved representation; CP-26 step 3 removes its legacy branch.
        """

        with self.assertRaises(SystemExit) as raised:
            cli.build_parser().parse_args(["registry", "scaffold", "--source", "/tmp/r"])
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(hasattr(CurationAction, "SCAFFOLD"))
        self.assertTrue(hasattr(CurationAction, "PUBLISH"))
        published = cli.build_parser().parse_args(["registry", "publish", "--source", "/tmp/r"])
        self.assertEqual(published.registry_action, "publish")

    def test_the_compatibility_ceiling_defaults_to_the_running_aart(self) -> None:
        # The upper compatibility point is whichever AART is publishing, not a version frozen in
        # the parser.  A default that never moves refuses every registry whose floor rises above
        # it, and proves nothing about today's release for the ones below it.
        request = cli._to_request(cli.build_parser().parse_args(["registry", "test"]))

        self.assertEqual(request.latest_version, __version__)

    def test_rs02_no_registry_action_declares_a_window_that_excludes_the_running_aart(self) -> None:
        # `--minimum-version` and `--maximum-version` exist on `registry init` alone, so every
        # other action reaches the command boundary with both unset and takes whatever the
        # boundary substitutes.  It substituted the literals `1.0.0` and `2.0.0`: a window that
        # stops one whole major short of the AART doing the writing.  Only `init` reads the pair
        # today, which is the sole reason nothing has broken -- a value that is wrong the moment
        # anything reads it is not worth carrying.
        running = parse_semver(__version__)
        assert isinstance(running, Ok)

        for command in (_VENDOR, _FORMAT):
            with self.subTest(command=command.split()[1]):
                request = cli._to_request(cli.build_parser().parse_args(command.split()))
                curation = registry_command._curation_request(
                    request, CurationAction(request.registry_action)
                )
                assert isinstance(curation, Ok)
                minimum = parse_semver(curation.value.minimum_version)
                maximum = parse_semver(curation.value.maximum_version)
                assert isinstance(minimum, Ok) and isinstance(maximum, Ok)

                self.assertTrue(
                    VersionBounds(minimum.value, maximum.value).allows(running.value),
                    f"{curation.value.minimum_version}..{curation.value.maximum_version} "
                    f"excludes the running {__version__}",
                )

    def test_rs02_init_still_carries_the_window_the_operator_asked_for(self) -> None:
        # The substitution is a fallback, not a rewrite: an author who really supports a wider
        # range says so on `init`, and that is what has to reach the manifest.
        request = cli._to_request(
            cli.build_parser().parse_args(
                "registry init --source /tmp/registry --source-id company --display-name Company "
                "--minimum-version 2.0.0 --maximum-version 4.0.0".split()
            )
        )
        curation = registry_command._curation_request(request, CurationAction.INIT)

        assert isinstance(curation, Ok)
        self.assertEqual(curation.value.minimum_version, "2.0.0")
        self.assertEqual(curation.value.maximum_version, "4.0.0")

    def test_laf90_init_pressed_through_names_a_window_the_running_aart_is_inside(self) -> None:
        # Every registry action that reaches the boundary with both versions unset gets the
        # running AART's window.  `init` is the one action that does not: it owns the
        # two flags, so it is the parser's defaults, not the boundary's fallback, that an operator
        # who supplies neither authors the registry from.  Left dead, those defaults author a
        # registry the executable that wrote it then refuses to read.  The assertion is the boundary's
        # own, applied to the one action its loop cannot cover.
        request = cli._to_request(
            cli.build_parser().parse_args(
                "registry init --source /tmp/registry --source-id company "
                "--display-name Company".split()
            )
        )
        curation = registry_command._curation_request(request, CurationAction.INIT)

        assert isinstance(curation, Ok)
        running = parse_semver(__version__)
        minimum = parse_semver(curation.value.minimum_version)
        maximum = parse_semver(curation.value.maximum_version)
        assert isinstance(running, Ok)
        assert isinstance(minimum, Ok) and isinstance(maximum, Ok)

        self.assertTrue(
            VersionBounds(minimum.value, maximum.value).allows(running.value),
            f"supplying neither flag offers {curation.value.minimum_version}.."
            f"{curation.value.maximum_version}, which excludes the running {__version__}",
        )


if __name__ == "__main__":
    unittest.main()
