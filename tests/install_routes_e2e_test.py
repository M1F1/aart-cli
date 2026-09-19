"""Every install line the documents publish, executed rather than read.

`adoption_first_contact_test` holds the install document to a shape: no hardcoded host, one
`<repository>` placeholder, three installers, the Enterprise narrowing written down. Shape is not
the claim worth holding. A line can have the right shape and the wrong flag, and the reader finds
out at their own shell -- which is the one place a documentation defect costs somebody an afternoon
rather than a test run.

So the gate builds this checkout's wheel, puts it on disk where an authenticated download would
have left it, and runs the lines. Nothing is paraphrased: the commands come out of the document,
with `X.Y.Z` replaced by the version that was just built, and go to a shell exactly as written --
`$(pbpaste)` and all, against a stand-in clipboard, because the substitution is part of the line
and a line that only works without it is not the line on the page.
"""

from __future__ import annotations

import io
import unittest

from tests.packaging_test import REPO_ROOT, _load_script


class DocumentedInstallRouteTest(unittest.TestCase):
    def test_every_documented_install_line_is_classified_and_the_runnable_ones_run(self) -> None:
        smoke = _load_script("distribution_smoke")

        receipt = smoke.run_install_routes(REPO_ROOT)

        self.assertEqual(receipt["schema_version"], 1)
        # Every fenced command is accounted for. A new line nobody classified fails here, which is
        # the only reason this bucket exists: silence would let an unrunnable line join the page.
        self.assertEqual(receipt["unclassified"], ())
        self.assertEqual(
            receipt["documented"],
            len(receipt["executed"]) + len(receipt["declined"]) + len(receipt["unavailable"]),
        )
        # The two routes a reader on a private instance is actually told to take: fetch the asset
        # with something that authenticates, then install the file that arrived.
        self.assertIn("disk", {item["route"] for item in receipt["executed"]})
        self.assertIn("authenticated-download", {item["route"] for item in receipt["executed"]})
        # `python -m pip` is the one installer every environment has, so it is the one the gate
        # requires. `uv` and `pipx` widen the proof where they exist and are reported when absent.
        self.assertIn("python -m pip", {item["installer"] for item in receipt["executed"]})
        for item in receipt["executed"]:
            with self.subTest(command=item["command"]):
                self.assertEqual(item["version"], receipt["version"])
        # Declining is a decision, not a gap: each one names why it cannot run here.
        for item in receipt["declined"]:
            with self.subTest(command=item["command"]):
                self.assertIn(item["route"], ("network", "consumer-example", "generator"))

    def test_the_generated_lines_are_the_ones_the_release_body_will_carry(self) -> None:
        """D-277: the page names no address, so the address comes from `install_commands.py`.

        Running it proves the generator still runs; comparing its wheel name with the wheel this
        checkout builds proves the two have not drifted apart, which is the drift that would put a
        filename on a release body that the release does not contain.
        """

        smoke = _load_script("distribution_smoke")

        receipt = smoke.run_install_routes(REPO_ROOT)

        self.assertTrue(receipt["generator_ran"])
        self.assertIn(receipt["wheel"], receipt["generated_lines"])

    def test_the_structural_promises_are_part_of_this_gate(self) -> None:
        """Step 16 is one gate over both halves, so it runs both halves.

        The section order, the bounded explanation, the reachability of every documented link and
        the licence last are held by `adoption_first_contact_test`, which the unit gate runs. That
        leaves the integration gate proving the lines work on a page whose shape it never checked,
        and a structural regression reaching a release through the half nobody ran. Loading those
        cases here costs a second and closes it.
        """

        from tests import adoption_first_contact_test as adoption

        loader, suite = unittest.TestLoader(), unittest.TestSuite()
        for name in (
            "QuickStartRouteTest",
            "OrientationTest",
            "DocumentationIndexTest",
            "DocumentedCommandSurfaceTest",
            "InstallDocumentTest",
        ):
            suite.addTests(loader.loadTestsFromTestCase(getattr(adoption, name)))
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)

        self.assertEqual(([], []), (result.failures, result.errors))
        # A class renamed out from under this list would otherwise leave it passing over nothing.
        self.assertGreater(result.testsRun, 15)


if __name__ == "__main__":
    unittest.main()
