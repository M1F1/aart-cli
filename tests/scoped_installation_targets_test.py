"""§172.5, INV-260: one transaction may write both scopes, each under its own root and lease.

`McpTarget` already names the scope it belongs to. These hold that the registry an installation
writes through resolves every target against that scope's own root, and that the lease such a
transaction takes is every scope root's lease, acquired in one fixed order.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.harness import McpRegistration, Scope, mcp_target
from aart_cli.domain.result import Err, Ok
from aart_cli.io.execution import CompositeMutationLock
from aart_cli.io.harness import ScopedHarnessRegistry


class TheRegistryWritesEachScopeUnderItsOwnRootTest(unittest.TestCase):
    def test_a_project_and_a_user_target_land_under_their_own_roots(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            registry = ScopedHarnessRegistry({Scope.PROJECT: project, Scope.USER: home})
            for scope in (Scope.PROJECT, Scope.USER):
                registered = registry.register(
                    McpRegistration(mcp_target("claude", scope), f"demo-{scope.value}", "/bin/sh")
                )
                self.assertIsInstance(registered, Ok)

            project_target = mcp_target("claude", Scope.PROJECT)
            user_target = mcp_target("claude", Scope.USER)
            self.assertEqual(
                registry.path_for(project_target),
                os.path.join(project, project_target.settings_file),
            )
            self.assertEqual(
                registry.path_for(user_target), os.path.join(home, user_target.settings_file)
            )
            with open(registry.path_for(project_target), encoding="utf-8") as handle:
                project_file = json.load(handle)
            self.assertEqual(set(project_file[project_target.server_map]), {"demo-project"})
            self.assertEqual(registry.registered(user_target).value, ("demo-user",))  # type: ignore[union-attr]

    def test_a_scope_without_a_root_is_refused_rather_than_resolved_elsewhere(self) -> None:
        with tempfile.TemporaryDirectory() as project:
            registry = ScopedHarnessRegistry({Scope.PROJECT: project})
            refused = registry.register(
                McpRegistration(mcp_target("claude", Scope.USER), "demo", "/bin/sh")
            )

            self.assertIsInstance(refused, Err)
            self.assertEqual(os.listdir(project), [])


class _Lease:
    def __init__(self, key: str, journal: list[str], *, fails: bool = False) -> None:
        self.key, self.journal, self.fails = key, journal, fails

    def acquire(self):
        if self.fails:
            self.journal.append(f"refused {self.key}")
            return Err((Diagnostic(DiagnosticCode("lease-held"), Severity.ERROR, "held"),))
        self.journal.append(f"acquire {self.key}")
        return Ok(self.key)

    def release(self, token: str):
        self.journal.append(f"release {token}")
        return Ok(None)


class TheCompositeLockHoldsEveryLeaseTest(unittest.TestCase):
    @given(
        st.lists(st.text("abcdef:/", min_size=1, max_size=6), min_size=1, max_size=5, unique=True)
    )
    def test_leases_are_taken_in_one_order_and_given_back_in_reverse(self, keys) -> None:
        journal: list[str] = []
        lock = CompositeMutationLock(tuple((key, _Lease(key, journal)) for key in keys))

        token = lock.acquire()
        self.assertIsInstance(token, Ok)
        self.assertIsInstance(lock.release(token.value), Ok)  # type: ignore[union-attr]

        ordered = sorted(keys)
        self.assertEqual(
            journal,
            [f"acquire {key}" for key in ordered] + [f"release {key}" for key in reversed(ordered)],
        )

    def test_a_refused_lease_gives_back_the_ones_already_held(self) -> None:
        journal: list[str] = []
        lock = CompositeMutationLock(
            (
                ("user:/home", _Lease("user:/home", journal, fails=True)),
                ("project:/p", _Lease("project:/p", journal)),
            )
        )

        self.assertIsInstance(lock.acquire(), Err)
        self.assertEqual(
            journal, ["acquire project:/p", "refused user:/home", "release project:/p"]
        )


if __name__ == "__main__":
    unittest.main()
