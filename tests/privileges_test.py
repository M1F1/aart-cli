"""`QA-086`: a test whose subject is a permission stands down where permissions do not apply.

The guard itself is worth holding, because the failure it prevents is invisible: a test that
silently never skips looks exactly like a test that never needed to, right up to the container run
where it fails for a reason that has nothing to do with the code.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from tests.privileges import running_as_root, skip_if_root


class RootAwareSkipTest(unittest.TestCase):
    def test_root_is_the_effective_user_this_process_actually_has(self) -> None:
        with mock.patch.object(os, "geteuid", return_value=0, create=True):
            self.assertTrue(running_as_root())
        with mock.patch.object(os, "geteuid", return_value=501, create=True):
            self.assertFalse(running_as_root())

    def test_a_machine_with_no_such_notion_is_not_root(self) -> None:
        """Windows has no `geteuid`, and absence is not privilege."""

        with mock.patch.object(os, "geteuid", side_effect=AttributeError, create=True):
            with mock.patch("tests.privileges.hasattr", return_value=False, create=True):
                self.assertFalse(running_as_root())

    def test_a_guarded_test_stands_down_under_root_and_runs_otherwise(self) -> None:
        for euid, expected in ((0, 1), (501, 0)):
            with self.subTest(euid=euid):
                with mock.patch.object(os, "geteuid", return_value=euid, create=True):

                    class Guarded(unittest.TestCase):
                        @skip_if_root("the mode bits on a sealed directory")
                        def test_it(self) -> None:
                            pass

                    result = unittest.TestResult()
                    unittest.defaultTestLoader.loadTestsFromTestCase(Guarded).run(result)

                self.assertEqual(len(result.skipped), expected)
                self.assertEqual(result.errors + result.failures, [])

    def test_the_skip_reason_names_what_the_test_needed(self) -> None:
        with mock.patch.object(os, "geteuid", return_value=0, create=True):

            class Guarded(unittest.TestCase):
                @skip_if_root("the mode bits on a sealed directory")
                def test_it(self) -> None:
                    pass

            result = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromTestCase(Guarded).run(result)

        ((_, reason),) = result.skipped
        self.assertEqual(reason, "root ignores the mode bits on a sealed directory")


if __name__ == "__main__":
    unittest.main()
