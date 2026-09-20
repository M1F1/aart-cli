# Installing AART

Python 3.10 or later is required.

**The exact commands are on this repository's [Releases page](../../../../releases).** Every release
carries them, filled in with the address of the repository you are reading them in -- so a fork on
a company instance shows its own host, and nobody has to guess or substitute anything. That link is
relative on purpose: it resolves inside whatever repository this file lives in, which is why this
page can point at a release without naming an address that would be wrong in a fork, and would
conflict on every merge from upstream.

From a checkout, the same commands print here:

```sh
python scripts/install_commands.py
```

The shapes are below, if you want them before you look. `<repository>` is the address of the
repository you are reading this in, and `X.Y.Z` is the release you want; the command above prints
both filled in.

| Source | `pip` (inside your environment) | `pipx` | `uv` |
|---|---|---|---|
| Tagged Git repository, no clone | `python -m pip install --no-deps "git+<repository>.git@vX.Y.Z"` | `pipx install "git+<repository>.git@vX.Y.Z"` | `uv tool install "git+<repository>.git@vX.Y.Z"` |
| Downloaded wheel | `python -m pip install --no-deps ./aart_cli-X.Y.Z-py3-none-any.whl` | `pipx install ./aart_cli-X.Y.Z-py3-none-any.whl` | `uv tool install ./aart_cli-X.Y.Z-py3-none-any.whl` |
| Release wheel by URL | `python -m pip install --no-deps <the wheel's address on the release>` | `pipx install <the wheel's address on the release>` | `uv tool install <the wheel's address on the release>` |

## The short way: copy the wheel's link, paste one line

The full shape of a wheel install names the version three times, which is three chances to mistype
it. With `uv`, where `<repository>` is the address you are reading this in and `X.Y.Z` is the
release you want:

```sh
uv tool install --force "<repository>/releases/download/vX.Y.Z/aart_cli-X.Y.Z-py3-none-any.whl"
```

Nobody should type that. **Copy the link instead, and let the shell read your clipboard.** On the
release page, under **Assets**, right-click `aart_cli-X.Y.Z-py3-none-any.whl` and choose *Copy link
address*. Then paste whichever of these you use -- each one is complete as written, with no
placeholder left to fill in:

```sh
uv tool install --force "$(pbpaste)"
```

```sh
pipx install --python "$(command -v python3)" --force "$(pbpaste)"
```

```sh
python -m pip install --no-deps --force-reinstall "$(pbpaste)"
```

The version never appears, because the address you copied already carries it. `uv tool` and `pipx`
build an isolated tool environment; the `pip` line installs into **whatever environment is active
right now**, so use it deliberately.

`pbpaste` is macOS. The same line works elsewhere by swapping it for your clipboard reader --
`wl-paste` on Wayland, `xclip -o -selection clipboard` on X11, `powershell.exe Get-Clipboard` under
WSL.

Two things that make this fail, both worth recognising:

- **The clipboard holds something else.** Copying a shell command from a page and then running one
  of these makes the installer try to install that command as a package name. Check with
  `pbpaste` alone before you paste.
- **The release is private.** `pip`, `pipx` and `uv` send no token when fetching a URL, so a
  private asset returns a sign-in page and the installer fails on a corrupt archive. Use the
  download-first blocks below instead.

## When the wheel has to be downloaded first

A private release cannot be installed from its URL at all, for the reason above. Download the file
with something that does authenticate -- the instance's own web UI, or a CLI you are already signed
in to. `gh` is already signed in to the instance you set it up for:

```sh
gh release download vX.Y.Z --pattern 'aart_cli-*-py3-none-any.whl' --dir .
```

Then install the path:

```sh
python -m pip install --no-deps --force-reinstall ./aart_cli-X.Y.Z-py3-none-any.whl
```

This installs into the active Python environment. For an isolated tool environment, use either
of the following installers if available:

```sh
uv tool install --force ./aart_cli-X.Y.Z-py3-none-any.whl
```

```sh
pipx install --python "$(command -v python3)" --force ./aart_cli-X.Y.Z-py3-none-any.whl
```

`pipx` is handed `python3` explicitly because the interpreter it cached as its own default may be a
different or a broken one; whichever it is must be 3.10 or newer. If an install fails complaining
about a corrupt archive, the downloaded file is probably a saved sign-in page rather than a wheel --
`python3 -m zipfile -t aart_cli-X.Y.Z-py3-none-any.whl` says so in one line.

The Git row needs no pre-downloaded wheel: `git+https://` uses your Git credentials. It does build
from source, however, so its environment must be able to obtain the pinned `poetry-core` build
backend. The downloaded-wheel route avoids that build requirement.

`pipx` and `uv tool` create an isolated tool environment. AART has no runtime dependencies. The
release wheel is byte-reproducible from its tag; see
[wheel reproducibility](../release/wheel-reproducibility-v1.md) to check one.

## On a private Enterprise instance

A fork on a GitHub Enterprise Server instance is normally private, and that changes which of those
sources work at all.

| Source | Works on a private instance |
|---|---|
| Tagged Git repository, no clone | Yes, if git authenticates **and** the build environment can obtain `poetry-core==2.4.0` |
| Downloaded wheel | Yes, once the file is on disk -- see below for getting it there |
| Internal index, once the wheel is published to it | Yes. Add `--index-url <your index>` (`--default-index` for `uv`) and ask for `"aart-cli==X.Y.Z"` |
| Release wheel by URL | **No.** See below |

The last row is the one that surprises people. `pip`, `pipx` and `uv` send no token when they fetch
a URL, so a release asset on a private repository answers with a sign-in page. The installer then
fails on a corrupt archive rather than on a refusal, and the message names neither cause nor fix.
Use that row only where the address answers without a login.

To get the wheel onto disk instead, download it with something that does authenticate -- your
instance's own UI, or a CLI you already have signed in -- and install from the file.

Keep a reviewed tag rather than following a moving branch. Where `pipx` is unavailable, an unzipped
wheel is a working installation on its own -- AART has no runtime dependencies, so a directory on
`PYTHONPATH` is enough.

The editable install is for working on AART itself, not for a colleague adopting it:

```sh
git clone <repository>.git
cd aart-cli
python -m pip install --no-index --no-deps --no-build-isolation -e .
```

Then, in a consumer project:

```sh
cd /path/to/consumer-project
aart-cli source add \
  --alias company \
  --kind registry-git \
  --location https://github.example.com/company/agent-registry.git \
  --ref main \
  --default \
  --json
aart-cli marketplace list --json
```

`source add` acquires, compiles, and validates the exact snapshot before it saves configuration.
With automatic synchronization (the default), source-bearing marketplace and TUI entry points
compare with the origin and publish a validated changed snapshot first. Manual mode reports
`not-synchronized` or `could-not-check` without moving the local pointer.
