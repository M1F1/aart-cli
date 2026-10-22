"""Publishing a wheel describes the wheel, and a refusal is quoted rather than summarised.

The upload is one HTTP POST written against the standard library, because `twine` would be the
fourth program this project assumed was installed and was not -- after Make, `gh` and `curl`.
What the POST carries has to be right, and "right" here means two things: every field is read out
of the wheel rather than restated, and every digest describes the bytes that actually travelled.
"""

from __future__ import annotations

import base64
import email
import hashlib
import io
import json
import unittest
import urllib.error
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.script_fixtures import load_script as _load_script

publish_to_index = _load_script("publish_to_index")

_METADATA = """Metadata-Version: 2.1
Name: aart-cli
Version: 9.9.9
Summary: A summary only the wheel knows.

"""


def _wheel(directory: Path, name: str = "aart_cli-9.9.9-py3-none-any.whl") -> Path:
    """A wheel is a zip with a `.dist-info/`, and that is all this needs to be one."""

    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("aart_cli/__init__.py", "# nothing\n")
        archive.writestr("aart_cli-9.9.9.dist-info/METADATA", _METADATA)
    return path


def _parts(payload: bytes, boundary: str) -> dict[str, tuple[str | None, bytes]]:
    """The multipart body, parsed the way a server parses it: field -> (filename, bytes)."""

    message = email.message_from_bytes(
        f'Content-Type: multipart/form-data; boundary="{boundary}"\r\n\r\n'.encode() + payload
    )
    found: dict[str, tuple[str | None, bytes]] = {}
    for part in message.get_payload():
        name = part.get_param("name", header="content-disposition")
        found[str(name)] = (part.get_filename(), part.get_payload(decode=True))
    return found


class FieldsComeFromTheWheelTest(unittest.TestCase):
    def test_what_is_claimed_about_the_file_is_read_out_of_the_file(self) -> None:
        """A field restated here could disagree with the wheel, and nothing would notice."""

        with TemporaryDirectory() as held:
            fields = dict(publish_to_index.form(_wheel(Path(held))))

        self.assertEqual(fields["name"], "aart-cli")
        self.assertEqual(fields["version"], "9.9.9")
        self.assertEqual(fields["summary"], "A summary only the wheel knows.")
        self.assertEqual(fields["metadata_version"], "2.1")
        # The interpreter tag is a property of the filename, not of the metadata.
        self.assertEqual(fields["pyversion"], "py3")
        self.assertEqual(fields[":action"], "file_upload")
        self.assertEqual(fields["protocol_version"], "1")
        self.assertEqual(fields["filetype"], "bdist_wheel")

    def test_a_wheel_missing_its_metadata_is_refused_by_name(self) -> None:
        with TemporaryDirectory() as held:
            directory = Path(held)
            path = directory / "aart_cli-9.9.9-py3-none-any.whl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("aart_cli/__init__.py", "")
            with self.assertRaises(publish_to_index.PublishError) as refusal:
                publish_to_index.form(path)
        self.assertIn("METADATA", str(refusal.exception))

    def test_a_dist_holding_two_wheels_is_refused_rather_than_guessed(self) -> None:
        """Picking one of two would publish the wrong version quietly, which is the worst kind."""

        with TemporaryDirectory() as held:
            directory = Path(held)
            (directory / "dist").mkdir()
            _wheel(directory / "dist")
            _wheel(directory / "dist", "aart_cli-9.9.8-py3-none-any.whl")
            with self.assertRaises(publish_to_index.PublishError) as refusal:
                publish_to_index.wheel(directory)
        message = str(refusal.exception)
        self.assertIn("9.9.8", message)
        self.assertIn("9.9.9", message)


class TheBodyDescribesTheBytesSentTest(unittest.TestCase):
    def test_every_digest_is_of_the_file_in_the_same_request(self) -> None:
        with TemporaryDirectory() as held:
            path = _wheel(Path(held))
            on_disk = path.read_bytes()
            payload = publish_to_index.body(publish_to_index.form(path), path, "aboundary")

        parts = _parts(payload, "aboundary")
        filename, content = parts["content"]
        self.assertEqual(filename, "aart_cli-9.9.9-py3-none-any.whl")
        # The file that travelled is the file on disk, byte for byte -- not merely one of its size.
        self.assertEqual(content, on_disk)
        self.assertEqual(parts["sha256_digest"][1].decode(), hashlib.sha256(content).hexdigest())
        self.assertEqual(parts["md5_digest"][1].decode(), hashlib.md5(content).hexdigest())  # noqa: S324
        self.assertEqual(
            parts["blake2_256_digest"][1].decode(),
            hashlib.blake2b(content, digest_size=32).hexdigest(),
        )


class TheCredentialStaysOutOfSightTest(unittest.TestCase):
    def test_it_is_read_from_the_environment_and_never_taken_as_an_argument(self) -> None:
        """An argument is visible in a process list and kept in shell history."""

        source = Path(publish_to_index.__file__).read_text(encoding="utf-8")
        self.assertNotIn('add_argument("--credentials"', source)
        self.assertNotIn('add_argument("--password"', source)

        with mock.patch.dict("os.environ", {"AART_CLI_INDEX_PUBLISH_CREDENTIALS": "who:what"}):
            header = publish_to_index.credentials()
        self.assertEqual(base64.b64decode(header.removeprefix("Basic ")).decode(), "who:what")

    def test_a_missing_credential_names_the_variable_and_what_it_holds(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(publish_to_index.PublishError) as refusal:
                publish_to_index.credentials()
        message = str(refusal.exception)
        self.assertIn("AART_CLI_INDEX_PUBLISH_CREDENTIALS", message)
        self.assertIn("colon", message)


class ARefusalIsQuotedTest(unittest.TestCase):
    """An index refuses for reasons worth reading, and `HTTP Error 400` throws all of them away."""

    def test_the_index_own_words_reach_the_log(self) -> None:
        said = "Repository does not allow updating assets: pypi-internal"
        error = urllib.error.HTTPError(
            "https://nexus.example.org/repository/pypi-internal/",
            400,
            "Bad Request",
            {},  # type: ignore[arg-type]
            io.BytesIO(said.encode()),
        )
        with TemporaryDirectory() as held:
            directory = Path(held)
            path = _wheel(directory)
            with mock.patch.dict("os.environ", {"AART_CLI_INDEX_PUBLISH_CREDENTIALS": "who:what"}):
                with mock.patch.object(
                    publish_to_index.urllib.request, "urlopen", side_effect=error
                ):
                    with self.assertRaises(publish_to_index.PublishError) as refusal:
                        publish_to_index.publish("https://nexus.example.org/repository/x/", path)

        message = str(refusal.exception)
        self.assertIn(said, message)
        self.assertIn("400", message)

    def test_an_index_that_cannot_be_reached_says_so_rather_than_tracing(self) -> None:
        with TemporaryDirectory() as held:
            directory = Path(held)
            path = _wheel(directory)
            with mock.patch.dict("os.environ", {"AART_CLI_INDEX_PUBLISH_CREDENTIALS": "who:what"}):
                with mock.patch.object(
                    publish_to_index.urllib.request,
                    "urlopen",
                    side_effect=urllib.error.URLError("certificate verify failed"),
                ):
                    with self.assertRaises(publish_to_index.PublishError) as refusal:
                        publish_to_index.publish("https://nexus.example.org/repository/x/", path)
        self.assertIn("certificate verify failed", str(refusal.exception))


class _Index:
    """A stand-in for `urlopen` that answers by URL and records every request it was handed."""

    def __init__(self, answers: dict[str, bytes | int]) -> None:
        self.answers = answers
        self.seen: list[urllib.request.Request] = []

    def __call__(self, request, *_args, **_kwargs):  # noqa: ANN001 - urllib's own shape
        self.seen.append(request)
        answer = self.answers.get(request.full_url, b"")
        if isinstance(answer, int):
            raise urllib.error.HTTPError(
                request.full_url,
                answer,
                "refused",
                {},  # type: ignore[arg-type]
                io.BytesIO(b"no such project"),
            )
        return io.BytesIO(answer)

    def posts(self) -> list[str]:
        return [request.full_url for request in self.seen if request.get_method() == "POST"]


_UPLOAD = "https://nexus.example.org/repository/pypi-internal/"
_GROUP = "https://nexus.example.org/repository/pypi-group/simple"
_PAGE = _GROUP + "/aart-cli/"


def _listing(name: str, digest: str) -> bytes:
    return (
        "<html><body>"
        f'<a href="../../packages/aart-cli/9.9.8/aart_cli-9.9.8-py3-none-any.whl#sha256={"0" * 64}">'
        "aart_cli-9.9.8-py3-none-any.whl</a>"
        f'<a href="../../packages/aart-cli/9.9.9/{name}#sha256={digest}">{name}</a>'
        "</body></html>"
    ).encode()


class AWheelTheIndexHoldsIsNotUploadedAgainTest(unittest.TestCase):
    """A retried publish must be safe, and an index refuses a second upload of the same version.

    So the index is asked first. The same file already there is success; a different file under the
    same name is the one outcome nobody should paper over (§192, INV-293).
    """

    def _run(self, answers: dict[str, bytes | int]) -> tuple[_Index, str]:
        index = _Index(answers)
        with TemporaryDirectory() as held:
            path = _wheel(Path(held))
            self.digest = hashlib.sha256(path.read_bytes()).hexdigest()
            for url, answer in list(answers.items()):
                if answer == b"SAME":
                    answers[url] = _listing(path.name, self.digest)
            environment = {
                "AART_CLI_INDEX_PUBLISH_CREDENTIALS": "deploy:written",
                "AART_CLI_INDEX_CREDENTIALS": "reader:read",
            }
            with mock.patch.dict("os.environ", environment):
                with mock.patch.object(publish_to_index.urllib.request, "urlopen", index):
                    said = publish_to_index.publish_once(_UPLOAD, path, _GROUP)
        return index, said

    def test_the_same_file_already_in_the_index_is_success_without_an_upload(self) -> None:
        index, said = self._run({_PAGE: b"SAME"})

        self.assertEqual(index.posts(), [])
        self.assertIn("already", said)
        self.assertIn(self.digest, said)

    def test_a_different_file_under_the_same_name_is_refused_without_an_upload(self) -> None:
        index = _Index({_PAGE: _listing("aart_cli-9.9.9-py3-none-any.whl", "f" * 64)})
        with TemporaryDirectory() as held:
            path = _wheel(Path(held))
            with mock.patch.dict("os.environ", {"AART_CLI_INDEX_PUBLISH_CREDENTIALS": "d:w"}):
                with mock.patch.object(publish_to_index.urllib.request, "urlopen", index):
                    with self.assertRaises(publish_to_index.PublishError) as refusal:
                        publish_to_index.publish_once(_UPLOAD, path, _GROUP)

        self.assertEqual(index.posts(), [])
        self.assertIn("f" * 64, str(refusal.exception))

    def test_a_project_the_index_does_not_know_is_uploaded(self) -> None:
        index, said = self._run({_PAGE: 404})

        self.assertEqual(index.posts(), [_UPLOAD])
        self.assertIn("published", said)

    def test_another_version_listed_does_not_count_as_this_one(self) -> None:
        index, _ = self._run({_PAGE: _listing("aart_cli-9.9.7-py3-none-any.whl", "1" * 64)})

        self.assertEqual(index.posts(), [_UPLOAD])

    def test_the_check_reads_with_the_install_credential_and_the_upload_writes_with_its_own(
        self,
    ) -> None:
        index, _ = self._run({_PAGE: 404})

        (check,) = [request for request in index.seen if request.get_method() == "GET"]
        (upload,) = [request for request in index.seen if request.get_method() == "POST"]
        read = base64.b64decode(check.get_header("Authorization").removeprefix("Basic "))
        write = base64.b64decode(upload.get_header("Authorization").removeprefix("Basic "))
        self.assertEqual(read.decode(), "reader:read")
        self.assertEqual(write.decode(), "deploy:written")

    def test_without_an_index_to_ask_it_uploads(self) -> None:
        index = _Index({})
        with TemporaryDirectory() as held:
            path = _wheel(Path(held))
            with mock.patch.dict("os.environ", {"AART_CLI_INDEX_PUBLISH_CREDENTIALS": "d:w"}):
                with mock.patch.object(publish_to_index.urllib.request, "urlopen", index):
                    publish_to_index.publish_once(_UPLOAD, path, None)

        self.assertEqual([request.get_method() for request in index.seen], ["POST"])


_API = "https://ghe.example/api/v3"
_RELEASE = _API + "/repos/org/aart-cli/releases/tags/v9.9.9"
_ASSET = _API + "/repos/org/aart-cli/releases/assets/11"


def _release(*names: str) -> bytes:
    return json.dumps(
        {
            "assets": [
                {"name": name, "url": f"{_API}/repos/org/aart-cli/releases/assets/{11 + number}"}
                for number, name in enumerate(names)
            ]
        }
    ).encode()


class TheWheelComesFromTheReleaseTest(unittest.TestCase):
    """The index gets the bytes the Release carries, not a second build of the same tag (§192)."""

    ENVIRONMENT = {
        "GITHUB_API_URL": _API,
        "GITHUB_REPOSITORY": "org/aart-cli",
        "GITHUB_TOKEN": "unused-by-the-fake",
    }

    def test_the_one_wheel_attached_to_the_release_is_downloaded_byte_for_byte(self) -> None:
        index = _Index(
            {
                _RELEASE: _release("aart_cli-9.9.9-py3-none-any.whl", "notes.txt"),
                _ASSET: b"the attached bytes",
            }
        )
        with TemporaryDirectory() as held, mock.patch.dict("os.environ", self.ENVIRONMENT):
            with mock.patch.object(publish_to_index.github_api.urllib.request, "urlopen", index):
                path = publish_to_index.released_wheel("v9.9.9", Path(held))
            content = path.read_bytes()

        self.assertEqual(path.name, "aart_cli-9.9.9-py3-none-any.whl")
        self.assertEqual(content, b"the attached bytes")
        download = index.seen[-1]
        self.assertEqual(download.get_header("Accept"), "application/octet-stream")
        # The asset API redirects to storage that refuses a second credential, so the token must
        # not follow the redirect.
        self.assertNotIn("Authorization", download.headers)
        self.assertIn("Authorization", download.unredirected_hdrs)

    def test_a_release_without_exactly_one_wheel_is_refused_by_name(self) -> None:
        for names in ((), ("aart_cli-9.9.9-py3-none-any.whl", "aart_cli-9.9.8-py3-none-any.whl")):
            index = _Index({_RELEASE: _release(*names)})
            with TemporaryDirectory() as held, mock.patch.dict("os.environ", self.ENVIRONMENT):
                with mock.patch.object(
                    publish_to_index.github_api.urllib.request, "urlopen", index
                ):
                    with self.subTest(names=names):
                        with self.assertRaises(publish_to_index.PublishError) as refusal:
                            publish_to_index.released_wheel("v9.9.9", Path(held))
                        self.assertIn("v9.9.9", str(refusal.exception))


if __name__ == "__main__":
    unittest.main()
