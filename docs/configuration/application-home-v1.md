# Where AART keeps what it owns

AART writes to exactly one directory on your machine, and nothing outside it except the harness
files an installation is placed into. That directory is the **application home**:

```text
AART_CLI_HOME   if it is set, used exactly as given
~/.aart-cli     otherwise
```

macOS and Linux resolve it identically. There is no `Library/Application Support`, no XDG root and
no per-platform cache directory — those were three answers to one question, and a machine could get
two of them right and one of them wrong.

## What is inside it

```text
~/.aart-cli/
├── config.json                  # the Registries and Sources you connected, and AART's own settings
├── objects/
│   ├── sha256/                  # immutable canonical package content, addressed by digest
│   └── quarantine/              # objects that failed verification, kept as evidence
├── sources/                     # snapshots acquired from each connected Registry or Source
├── state/
│   ├── installations/           # one receipt per installation
│   ├── activity/                # what was done, including bulk transactions
│   ├── setup/                   # per-installation setup metadata
│   ├── object-references.json   # which objects are still referenced
│   └── consumer-settings.json   # interface preferences
├── cache/                       # derived data, safe to delete
├── locks/                       # concurrency control
└── tmp/                         # staging for operations in progress
```

`config.json` is configuration **of AART**. The configuration an *artifact* needs — a server's URL,
an organization name, a token — is not here and never has a copy here. Each installation collects
its own, stores ordinary values beside that installation in its harness, and stores secret values
in the platform credential store. No file in this directory contains a secret value.

Deleting `cache/` costs you re-derived data and nothing else. Deleting `state/` loses the record of
what is installed, which is not the same as uninstalling it: the files an installation wrote are in
the harness, and AART would no longer know they are its own.

## Pointing it somewhere else

Set `AART_CLI_HOME` to a normalized absolute path — no trailing slash, no `..`, no relative path.
An unusable value is refused with a diagnostic rather than silently corrected, because correcting it
would mean writing one job's state into a directory another job also resolved to.

```sh
AART_CLI_HOME=/runner/work/aart-state aart-cli marketplace status --profile claude
```

That is the mechanism CI and isolated agent jobs use: a private home, without changing `HOME` and
without touching whatever the harness has in the real one. Two jobs with two homes share nothing.

## What the variable cannot move

**Machine policy.** An administrator writes it, and its point is that the person running the command
cannot overrule it, so it does not live in a directory that person names:

| Platform | Machine policy file |
|---|---|
| macOS | `/Library/Application Support/aart-cli/policy.json` |
| Linux | `/etc/aart-cli/policy.json` |

Setting `AART_CLI_HOME` does not move that file and does not make AART stop reading it.

**Installed files.** What an installation actually delivers — its payload, its runtime, its launcher
and its configuration file — belongs to the harness it was installed into, under that harness's own
directory. The application home holds the canonical content and the record; it is not where an
installed thing runs from.

## Forgetting all of it

```sh
aart-cli reset
```

`reset` removes the entries listed above from the application home, after two exact confirmations
and a review that names every path first. It never removes the home directory itself, and it never
touches a project, a harness file or a credential item — so anything you put in that directory that
AART did not write is still there afterwards.
