"""§217: an MCP's Python packages are checked, not assumed, wherever the machine is judged.

Reported twice: a Collection install stopped at pip, the person fixed pip and installed again, and
the servers still could not start because `mcp` was never installed -- the environment existed, so
its dependencies counted as installed and the second install planned no pip run. Doctor said the
same and a repair would have rebuilt an empty environment.

Every step here is the public command against a real environment and a real pip, offline: the
author's `requirements.txt` points pip at a directory holding one hand-built wheel, so the package
is really installed, really removed and really put back.
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest
import zipfile

from tests.command_line_credentials_and_variables_test import GITHUB, _PromptingStore, _run
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import MANIFEST, SERVER_SOURCE

PACKAGE = "tiny_dep"


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def build_wheel(directory: pathlib.Path) -> pathlib.Path:
    """A minimal pure-Python wheel pip installs with no index and no build backend."""

    info = f"{PACKAGE}-1.0.dist-info"
    files = {
        f"{PACKAGE}/__init__.py": b"VALUE = 1\n",
        f"{info}/METADATA": b"Metadata-Version: 2.1\nName: tiny-dep\nVersion: 1.0\n",
        f"{info}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: aart-cli-tests\nRoot-Is-Purelib: true\n"
            b"Tag: py3-none-any\n"
        ),
    }
    record = "\n".join(
        [*(_record_line(name, data) for name, data in files.items()), f"{info}/RECORD,,"]
    )
    wheel = directory / f"{PACKAGE}-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr(f"{info}/RECORD", record + "\n")
    return wheel


def _authored(links: pathlib.Path) -> tuple[tuple[str, str], ...]:
    return (
        ("github/aart-cli.json", json.dumps(MANIFEST)),
        ("github/server.py", SERVER_SOURCE),
        ("github/requirements.txt", f"--no-index\n--find-links {links}\ntiny-dep==1.0\n"),
    )


def _installed(env) -> list[pathlib.Path]:
    return sorted(env.project.rglob(f"{PACKAGE}-1.0.dist-info"))


def _attention(payload: dict) -> list[str]:
    return [
        drift["component"] for repair in payload["repairs"] for drift in repair.get("drift", ())
    ]


def _version(env, store) -> str:
    """The exact installed coordinate a repair names."""

    _, out, _ = _run(env, store, "doctor")
    [item] = json.loads(out)["items"]
    return item["coordinate"]


class RuntimeDependenciesVerifiedE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.links = pathlib.Path(temporary.name).resolve()
        self.store = _PromptingStore()

    def _install(self, env) -> tuple[int, str]:
        code, out, _ = _run(
            env,
            self.store,
            "consume",
            "install",
            GITHUB,
            "--profile",
            "claude",
            "--set-later",
            "--yes",
        )
        return code, out

    def test_installing_again_after_pip_failed_runs_pip_again(self) -> None:
        with _environment(authored=_authored(self.links)) as env:
            failed, out = self._install(env)
            self.assertNotEqual(failed, 0, out)
            self.assertEqual(_installed(env), [], "pip found nothing to install the first time")

            build_wheel(self.links)
            code, out = self._install(env)

            self.assertEqual(code, 0, out)
            self.assertEqual(len(_installed(env)), 1, "the second install ran pip")

    def test_doctor_sees_a_missing_package_and_its_repair_puts_it_back(self) -> None:
        build_wheel(self.links)
        with _environment(authored=_authored(self.links)) as env:
            code, out = self._install(env)
            self.assertEqual(code, 0, out)
            [installed] = _installed(env)

            code, out, _ = _run(env, self.store, "doctor")
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)["summary"]["needs_attention"], 0)

            shutil.rmtree(installed)
            shutil.rmtree(installed.parent / PACKAGE)

            code, out, _ = _run(env, self.store, "doctor")
            payload = json.loads(out)
            self.assertNotEqual(code, 0, out)
            self.assertEqual(payload["summary"]["needs_attention"], 1)
            self.assertIn("runtime-dependencies", _attention(payload))

            code, out, _ = _run(env, self.store, "doctor", "--repair", _version(env, self.store))
            self.assertEqual(code, 0, out)
            review = json.loads(out)
            code, out, _ = _run(
                env,
                self.store,
                "doctor",
                "--repair",
                _version(env, self.store),
                "--yes",
                "--expect",
                review["review_digest"],
            )
            self.assertEqual(code, 0, out)
            self.assertEqual(len(_installed(env)), 1, "the repair ran pip")

    def test_a_repair_that_rebuilds_the_environment_installs_the_packages_too(self) -> None:
        build_wheel(self.links)
        with _environment(authored=_authored(self.links)) as env:
            code, out = self._install(env)
            self.assertEqual(code, 0, out)
            [installed] = _installed(env)
            environment = next(
                parent for parent in installed.parents if (parent / "pyvenv.cfg").exists()
            )
            shutil.rmtree(environment)

            code, out, _ = _run(env, self.store, "doctor", "--repair", _version(env, self.store))
            self.assertEqual(code, 0, out)
            review = json.loads(out)
            code, out, _ = _run(
                env,
                self.store,
                "doctor",
                "--repair",
                _version(env, self.store),
                "--yes",
                "--expect",
                review["review_digest"],
            )

            self.assertEqual(code, 0, out)
            self.assertEqual(len(_installed(env)), 1, "the rebuilt environment has its packages")


if __name__ == "__main__":
    unittest.main()
