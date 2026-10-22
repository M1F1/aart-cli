#!/usr/bin/env python3
"""Publish the built wheel to a PyPI-compatible package index, from the standard library alone.

`twine` is the usual answer and it is one more program a CI image has to carry. Three steps in
this repository have already been rewritten to stop assuming a tool was installed -- Make, then
`gh`, then `curl` -- each of them failing in an image that had git, an interpreter and nothing
else. Uploading a wheel is one HTTP POST, so it is one HTTP POST here.

The endpoint is the legacy upload API, which every private index in normal use speaks: Nexus's
`pypi-hosted` repositories, Artifactory's PyPI repositories, devpi, and PyPI itself. It takes a
`multipart/form-data` body with `:action=file_upload` and the distribution's own metadata as
fields, which are read out of the wheel rather than restated here -- a wheel that disagreed with
what was claimed about it would be worse than no upload at all.

A retry has to be safe, and an index refuses a second upload of a version it holds. So with
`--index` the index is asked first: the same file already listed there is success, a different
file under the same name is refused, and only a file it does not list is uploaded (§192, INV-293).
With `--release TAG` the wheel is the one attached to that GitHub Release rather than a build in
`dist/`, so the index receives exactly the bytes the Release carries.

Two things are deliberately not decided by this script:

* **where** to publish, which is `--url` (a repository variable in CI). There is no default: a
  default pointing at PyPI would make an accident out of a company's first mistake.
* **who** publishes, which is `AART_CLI_INDEX_PUBLISH_CREDENTIALS` in the environment, holding the
  two halves separated by a colon. It is never a command-line argument -- arguments are visible
  in a process list and land in shell history.
"""

from __future__ import annotations

import argparse
import base64
import email.parser
import html.parser
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from hashlib import blake2b, md5, sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import github_api  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# The fields the upload API names, and where each comes from.  Everything not listed is either
# derived (the digests) or a property of the file (`filetype`, `pyversion`).
_FROM_METADATA = (
    ("name", "Name"),
    ("version", "Version"),
    ("metadata_version", "Metadata-Version"),
    ("summary", "Summary"),
)


class PublishError(RuntimeError):
    """The index refused, carrying the index's own explanation."""


def wheel(root: Path = ROOT) -> Path:
    """The one wheel `build_wheel.py` produced."""

    built = sorted((root / "dist").glob("*.whl"))
    if len(built) != 1:
        found = ", ".join(path.name for path in built) or "nothing"
        raise PublishError(f"expected exactly one wheel under dist/, found {found}")
    return built[0]


def metadata(path: Path) -> dict[str, str]:
    """The wheel's own METADATA, parsed.  What is uploaded describes what is in the file."""

    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise PublishError(f"{path.name} carries {len(names)} METADATA files, expected one")
        raw = archive.read(names[0]).decode("utf-8")
    return dict(email.parser.Parser().parsestr(raw).items())


def form(path: Path) -> list[tuple[str, str]]:
    """The metadata fields for one wheel, in the shape the upload API asks for."""

    found = metadata(path)
    missing = [header for _, header in _FROM_METADATA if header not in found]
    if missing:
        raise PublishError(f"{path.name} METADATA has no {', '.join(missing)}")
    content = path.read_bytes()
    fields = [(field, found[header]) for field, header in _FROM_METADATA]
    fields.extend(
        (
            (":action", "file_upload"),
            ("protocol_version", "1"),
            ("filetype", "bdist_wheel"),
            # The interpreter tag out of the filename: `name-version-pyN-abi-platform.whl`.
            ("pyversion", path.stem.split("-")[2]),
            ("md5_digest", md5(content).hexdigest()),  # noqa: S324 - the API names this field
            ("sha256_digest", sha256(content).hexdigest()),
            ("blake2_256_digest", blake2b(content, digest_size=32).hexdigest()),
        )
    )
    return fields


def body(fields: list[tuple[str, str]], path: Path, boundary: str) -> bytes:
    """One `multipart/form-data` payload: the fields, then the file."""

    marker = f"--{boundary}".encode()
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(
            marker
            + b"\r\n"
            + f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            + value.encode("utf-8")
            + b"\r\n"
        )
    parts.append(
        marker
        + b"\r\n"
        + f'Content-Disposition: form-data; name="content"; filename="{path.name}"\r\n'.encode()
        + b"Content-Type: application/octet-stream\r\n\r\n"
        + path.read_bytes()
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def credentials() -> str:
    """The two halves, from the environment, assembled into one header value.

    Never an argument: arguments are visible in a process list and kept in shell history.
    """

    held = os.environ.get("AART_CLI_INDEX_PUBLISH_CREDENTIALS", "")
    separator = ":"
    if separator not in held:
        raise PublishError(
            "AART_CLI_INDEX_PUBLISH_CREDENTIALS is unset or malformed.\n"
            "It holds the publishing account and its password or token, separated by a colon, "
            "and is read from the environment so it never reaches a command line."
        )
    return "Basic " + base64.b64encode(held.encode("utf-8")).decode("ascii")


def released_wheel(tag: str, directory: Path) -> Path:
    """Download the one wheel attached to the Release at `tag` into `directory`."""

    api, repository = github_api.origin()
    try:
        release = github_api.json_request(f"{api}/repos/{repository}/releases/tags/{tag}")
        wheels = [item for item in release.get("assets", ()) if item["name"].endswith(".whl")]
        if len(wheels) != 1:
            found = ", ".join(item["name"] for item in wheels) or "none"
            raise PublishError(f"the Release at {tag} must carry exactly one wheel; found {found}")
        (asset,) = wheels
        content = github_api.request(asset["url"], accept="application/octet-stream")
    except github_api.GitHubError as error:
        raise PublishError(str(error)) from None
    path = directory / asset["name"]
    path.write_bytes(content)
    return path


class _Links(html.parser.HTMLParser):
    """The `href` of every anchor on a PEP 503 project page."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(value for name, value in attrs if name == "href" and value)


def indexed_digest(index: str, path: Path) -> str | None:
    """The sha256 the index lists for this wheel's filename, or None when it does not list it.

    Read with `AART_CLI_INDEX_CREDENTIALS`, the install login, when that is set: the hosted
    repository a release uploads to is normally read through the group everything installs from.
    """

    project = re.sub(r"[-_.]+", "-", metadata(path)["Name"]).lower()
    page = f"{index.rstrip('/')}/{project}/"
    request = urllib.request.Request(page, headers={"Accept": "text/html"})
    held = os.environ.get("AART_CLI_INDEX_CREDENTIALS", "")
    if ":" in held:
        login = base64.b64encode(held.encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {login}")
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 - operator-supplied index
            listing = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        detail = error.read().decode("utf-8", "replace").strip() or "(no response body)"
        raise PublishError(f"GET {page} refused ({error.code})\n{detail}") from None
    except urllib.error.URLError as error:
        raise PublishError(f"GET {page} could not be reached: {error.reason}") from None
    links = _Links()
    links.feed(listing)
    for href in links.hrefs:
        address = urllib.parse.urlsplit(href)
        if urllib.parse.unquote(address.path.rsplit("/", 1)[-1]) != path.name:
            continue
        fragment = dict(urllib.parse.parse_qsl(address.fragment))
        if "sha256" not in fragment:
            raise PublishError(f"{page} lists {path.name} without a sha256 to compare it by")
        return fragment["sha256"]
    return None


def publish_once(url: str, path: Path, index: str | None) -> str:
    """Upload unless `index` already lists this exact file; refuse if it lists another one."""

    if index:
        listed = indexed_digest(index, path)
        local = sha256(path.read_bytes()).hexdigest()
        if listed == local:
            return f"already published: {index} lists {path.name} with sha256 {local}"
        if listed is not None:
            raise PublishError(
                f"{index} already lists {path.name} with sha256 {listed}, but the wheel to "
                f"publish has sha256 {local}. An index keeps one file per name; find out which "
                "one is right before replacing anything."
            )
    return publish(url, path)


def publish(url: str, path: Path) -> str:
    boundary = uuid.uuid4().hex
    payload = body(form(path), path, boundary)
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(payload)),
            "Authorization": credentials(),
        },
    )
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 - operator-supplied index
            response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace").strip() or "(no response body)"
        # An index refuses for reasons worth reading: a version that already exists, an account
        # without deploy rights, a repository that is a proxy rather than a hosted one.  Raising
        # the status alone throws all three away and leaves a log saying `HTTP Error 400`.
        raise PublishError(f"POST {url} refused ({error.code})\n{detail}") from None
    except urllib.error.URLError as error:
        raise PublishError(f"POST {url} could not be reached: {error.reason}") from None
    return f"published {path.name} ({path.stat().st_size} bytes) to {url}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="the index's upload endpoint")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--wheel", type=Path, help="the file to publish; found under dist/ if not")
    source.add_argument(
        "--release", metavar="TAG", help="publish the wheel attached to this Release"
    )
    parser.add_argument(
        "--index", help="simple index to ask first; a file it already lists is not uploaded again"
    )
    parsed = parser.parse_args(argv)

    try:
        with tempfile.TemporaryDirectory() as held:
            if parsed.release:
                path = released_wheel(parsed.release, Path(held))
            else:
                path = parsed.wheel or wheel()
            print(publish_once(parsed.url, path, parsed.index))
    except PublishError as error:
        print(f"publish refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
