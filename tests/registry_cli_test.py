from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

from aart_cli import __version__, cli
from aart_cli.commands import registry as registry_command
from aart_cli.curation.model import CurationAction
from aart_cli.domain.result import Ok
from aart_cli.model import Request
from aart_cli.protocol.semver import VersionBounds, parse_semver

_DIFF = "maintain registry diff --source /tmp/registry"
_FORMAT = "maintain registry format --source /tmp/registry"


class RegistryCliTest(unittest.TestCase):
    def test_all_registry_actions_map_to_one_command_boundary(self) -> None:
        """§175.2: Registry maintenance is split by what it acts on, behind one handler."""

        parser = cli.build_parser()

        def choices(container, name):
            sub = next(
                action
                for action in container._actions
                if action.__class__.__name__ == "_SubParsersAction"
            )
            return sub.choices[name] if name else set(sub.choices)

        maintain = choices(parser, "maintain")
        self.assertEqual(
            choices(choices(maintain, "registry"), None),
            {
                "init",
                "collection",
                "format",
                "publish",
                "push",
                "validate",
                "lock",
                "build",
                "audit",
                "test",
                "diff",
            },
        )
        self.assertEqual(choices(choices(maintain, "candidate"), None), {"promote"})
        self.assertLessEqual(
            {"scan", "adopt", "check"}, choices(choices(maintain, "upstream"), None)
        )
        routed = {
            ("upstream", "scan"): "scan",
            ("upstream", "adopt"): "adopt",
            ("upstream", "check"): "check-upstream",
            ("candidate", "promote"): "promote",
            ("registry", "validate"): "validate",
        }
        for (family, action), handler_action in routed.items():
            with self.subTest(family=family, action=action):
                command, fields = cli._route(
                    argparse.Namespace(
                        command="maintain",
                        maintain_action=family,
                        source_action=action,
                        candidate_action=action,
                        registry_action=action,
                    )
                )
                self.assertEqual(command, "registry")
                self.assertEqual(fields.get("registry_action", action), handler_action)
        self.assertIn("registry", cli.DISPATCH)

    def test_no_route_writes_content_without_a_source_manifest(self) -> None:
        """§173.9 (D-375): adoption by manifest is the only way content enters a Registry."""

        for argv in (
            ["maintain", "registry", "vendor", "--source", "/tmp/r", "skill", "x"],
            ["maintain", "registry", "vendor-batch", "--source", "/tmp/r", "--manifest", "m.json"],
            ["maintain", "registry", "revendor", "--source", "/tmp/r", "skill", "x"],
            ["maintain", "registry", "discover", "--source", "/tmp/r"],
            ["maintain", "registry", "audit", "--source", "/tmp/r", "--check-upstream"],
        ):
            with self.subTest(argv=argv[2:4]), self.assertRaises(SystemExit):
                cli.build_parser().parse_args(argv)
        self.assertEqual(
            {item.value for item in CurationAction} & {"vendor", "vendor-batch", "revendor"},
            set(),
        )

    def test_format_check_and_json_are_preserved_in_request(self) -> None:
        captured: list[Request] = []

        def run(request: Request) -> int:
            captured.append(request)
            return 0

        with patch.dict(cli.DISPATCH, {"registry": run}):
            result = cli.main(
                ["maintain", "registry", "format", "--source", "/tmp/registry", "--check", "--json"]
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
                    "maintain",
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
            cli.build_parser().parse_args(
                ["maintain", "registry", "scaffold", "--source", "/tmp/r"]
            )
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(hasattr(CurationAction, "SCAFFOLD"))
        self.assertTrue(hasattr(CurationAction, "PUBLISH"))
        published = cli.build_parser().parse_args(
            ["maintain", "registry", "publish", "--source", "/tmp/r"]
        )
        self.assertEqual(published.registry_action, "publish")

    def test_the_compatibility_ceiling_defaults_to_the_running_aart(self) -> None:
        # The upper compatibility point is whichever AART is publishing, not a version frozen in
        # the parser.  A default that never moves refuses every registry whose floor rises above
        # it, and proves nothing about today's release for the ones below it.
        request = cli._to_request(cli.build_parser().parse_args(["maintain", "registry", "test"]))

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

        for command in (_DIFF, _FORMAT):
            with self.subTest(command=command.split()[2]):
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
                "maintain registry init --source /tmp/registry --source-id company --display-name Company "
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
                "maintain registry init --source /tmp/registry --source-id company "
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
