"""Local editable-to-wheel lifecycle proof from outside the source checkout."""

from __future__ import annotations

import unittest

from tests.packaging_test import REPO_ROOT, _load_script


class DistributionE2ETest(unittest.TestCase):
    def test_editable_and_wheel_environment_recreation_preserves_a_registry_installation(
        self,
    ) -> None:
        """A consumer's installation outlives the Python environment that made it.

        The smoke installs from an approved local Registry (INV-269) through the editable
        environment, deletes it, and resumes from a wheel environment; the placed tree must still
        match the digest its installation record attests, and must live outside both environments.
        """

        smoke = _load_script("distribution_smoke")

        receipt = smoke.run_smoke(REPO_ROOT)

        self.assertEqual(receipt["schema_version"], 1)
        self.assertEqual(receipt["registry_sync"], "published")
        self.assertEqual(receipt["initial_install"], 1)
        self.assertEqual(receipt["second_profile_install"], 1)
        self.assertEqual(receipt["resumed_current"], 2)
        self.assertEqual(receipt["removed"], 2)
        self.assertEqual(receipt["reinstalled"], 1)
        self.assertTrue(receipt["survived_editable_removal"])
        self.assertTrue(receipt["survived_wheel_removal"])
        self.assertEqual(receipt["runtime_dependencies"], 0)
        self.assertTrue(receipt["upgrade_dry_run"])
        self.assertTrue(receipt["placed_digest"].startswith("sha256:"))
        self.assertNotIn(receipt["editable_environment"], receipt["placed_destination"])
        self.assertNotIn(receipt["wheel_environment"], receipt["placed_destination"])


if __name__ == "__main__":
    unittest.main()
