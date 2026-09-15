"""CP-15: the three offline capabilities are separate, and refuse separately (INV-223).

Product Specification 165.11 decomposes offline installability into three capabilities -- metadata
cached, canonical payload cached, runtime dependencies cached -- and says in as many words that a
locally available artifact payload does not imply that package-manager dependencies can be
installed offline. INV-223 turns that into a prohibition: the three "must not be conflated".

All three are implemented and none of them was tested as a *decomposition*. The failure this guards
against is not that one layer is missing; it is a machine that answers every offline question with
one sentence, so an operator who cannot install cannot tell whether to run a sync, warm an object
store, or vendor a wheel. Each layer therefore has to refuse in its own words, and this file's last
test says they are three words rather than one.

`--offline` reaching the dependency installer at all is the third capability's whole content, and
it had no test: `python_environment_integration_test` proves offline pip and uv work against a real
locally built wheel, but nothing said the flag is what makes them index-free, so removing it would
have left that file green and every `--offline` install quietly reaching the network for
dependencies.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from agent_artifacts.domain.effects import InstallPythonDependencies
from agent_artifacts.domain.identifiers import ArtifactIdentity, SourceAlias
from agent_artifacts.domain.python_runtime import ArtifactEnvironment, PythonInstaller
from agent_artifacts.domain.result import Err
from agent_artifacts.installation.application import prepare_install
from agent_artifacts.installation.model import InstallLocation, InstallRequest
from agent_artifacts.io.python_runtime import LocalPythonRuntime
from agent_artifacts.profiles.builtin import builtin
from agent_artifacts.sources.model import source_instance_id, source_store_paths
from agent_artifacts.store.model import object_store_paths
from tests.canonical_install_planning_test import _candidate, _catalog, _MemoryReads
from tests.marketplace_lifecycle_e2e_test import _COORDINATE
from tests.source_sync_command_e2e_test import _environment_over_a_writable_source

_ENVIRONMENT = ArtifactEnvironment("probe", "/data/aart/artifacts/mcp/probe")


def _effect(installer: PythonInstaller) -> InstallPythonDependencies:
    return InstallPythonDependencies(
        _ENVIRONMENT.environment,
        f"{_ENVIRONMENT.root}/payload/requirements.txt",
        "requirements",
        installer.value,
    )


def _uncached_object_refusal() -> Err:
    """Plan an install whose metadata is cached and whose object is not."""

    catalog, effective = _catalog("skill", _candidate("skill"))
    refused = prepare_install(
        InstallRequest(
            ArtifactIdentity("skill", "review"),
            source=SourceAlias("direct"),
            profile="claude",
            platform="darwin",
            offline=True,
        ),
        catalog,
        effective,
        builtin()["claude"],
        InstallLocation("/project", "/home/alice", "/data/aart"),
        object_store_paths("/data/aart"),
        _MemoryReads(None),
    )
    assert isinstance(refused, Err), refused
    return refused


class OfflineCapabilityTest(unittest.TestCase):
    def test_an_uncached_source_names_the_cache_rather_than_the_artifact(self) -> None:
        """Capability one: metadata. The name in the request is the part that was not wrong."""

        with _environment_over_a_writable_source() as (env, _location):
            shutil.rmtree(
                Path(source_store_paths(env.paths.data_root, source_instance_id(env.source)).root)
            )

            code, refused = env.run(
                "marketplace", "install", _COORDINATE, "--profile", "claude", "--offline", "--yes"
            )

            self.assertEqual(code, 1, refused)
            diagnostic = refused["diagnostics"][0]
            self.assertEqual(diagnostic["code"], "source-not-synchronized")
            self.assertIn("--offline forbids fetching it", diagnostic["message"])
            self.assertIn(
                "aart source sync --alias reference, while connected",
                diagnostic["remediation"],
            )

            # The same command without the flag installs, so the refusal is about the capability
            # rather than about the artifact, the source or the machine.
            code, installed = env.run(
                "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(code, 0, installed)

    def test_an_uncached_object_is_a_different_refusal_from_an_uncached_source(self) -> None:
        """Capability two: payload. Metadata resolved the coordinate; the bytes are still absent."""

        refused = _uncached_object_refusal()

        self.assertEqual(refused.diagnostics[0].code.value, "install-object-unavailable")
        self.assertIn("while offline", refused.diagnostics[0].message)

    def test_dependency_installation_is_index_free_only_when_offline_is_asked_for(self) -> None:
        """Capability three: dependencies, for both backends, in both directions.

        Both directions on purpose. Asserting only that `--offline` adds the flag would pass on an
        implementation that always adds it, which is a different product: an installer that can
        never reach an index cannot install anything that is not already vendored.
        """

        for installer, flag in (
            (PythonInstaller.PIP, "--no-index"),
            (PythonInstaller.UV, "--offline"),
        ):
            with self.subTest(installer=installer.value):
                effect = _effect(installer)
                offline = LocalPythonRuntime(_ENVIRONMENT, offline=True)._install_argv(effect)
                connected = LocalPythonRuntime(_ENVIRONMENT)._install_argv(effect)

                assert offline is not None and connected is not None
                self.assertIn(flag, offline)
                self.assertNotIn(flag, connected)
                # The flag is the only difference: an offline run must install the same thing.
                self.assertEqual(
                    tuple(item for item in offline if item != flag),
                    connected,
                )

    def test_the_three_capabilities_refuse_under_three_distinct_codes(self) -> None:
        """INV-223 stated directly: not conflated.

        A cached payload does not imply cached dependencies, and neither implies cached metadata.
        The dependency layer has no diagnostic code of its own because it does not refuse -- it
        runs the installer with the network denied and reports whatever that installer says -- so
        what is compared here is the flag that denies it, which is the third distinct answer.
        """

        with _environment_over_a_writable_source() as (env, _location):
            shutil.rmtree(
                Path(source_store_paths(env.paths.data_root, source_instance_id(env.source)).root)
            )
            _, metadata = env.run(
                "marketplace", "install", _COORDINATE, "--profile", "claude", "--offline", "--yes"
            )

        payload = _uncached_object_refusal()
        dependencies = LocalPythonRuntime(_ENVIRONMENT, offline=True)._install_argv(
            _effect(PythonInstaller.PIP)
        )
        assert dependencies is not None

        self.assertNotEqual(
            metadata["diagnostics"][0]["code"],
            payload.diagnostics[0].code.value,
        )
        self.assertIn("--no-index", dependencies)


if __name__ == "__main__":
    unittest.main()
