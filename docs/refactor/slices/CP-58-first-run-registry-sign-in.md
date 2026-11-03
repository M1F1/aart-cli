# CP-58 — A default Registry the first run could not connect is named, with how to sign Git in

Status: **done**; merged in aart-cli #126, released in 0.27.1.
Authority: D-515. Resolves B-268.

## Why

A build may bake one Registry for a first run to connect. On a machine whose Git held no credential
for that Registry's host, the first run warned with Git's error, `fetch … origin: fatal: unable to
get password from user`, and "open Registries and choose Add Registry". It named neither the
Registry (the mirror's remote is `origin`) nor the cause, and since Git may not prompt, every later
run failed the same way.

## What changed

- `application/first_run_seed.unconnected_seed(source, reasons)`: the warning names
  `<alias> (<URL>)`, and offers the `ls-remote` check, the `consume registry add … --default`
  command and Registries. When the URL is HTTPS and Git's error says it has no credential or was
  refused one, it adds `gh auth login` and `gh auth setup-git` for the URL's host. A refused SSH key
  gets its own line instead, and any other refusal no sign-in.
- `commands/first_run.connect_baked_default_registry` uses it on a refused add.
- `docs/ci/github-enterprise-rollout.md`: Part 5 says each person's Git must be signed in to the
  host before the first run, with the two commands. Troubleshooting has a row for the warning.

## Evidence

`tests/first_run_connect_test.py`, `TheWarningSaysWhichRegistryAndHowToReachIt`:

- for a policy refusal and for a missing sign-in, the message names `company (<URL>)`, and the
  remediation holds the `ls-remote` check and the add command, exactly;
- five shapes of Git's error for a missing or refused credential each give the two `gh auth`
  commands for `example.invalid`;
- a policy refusal, an unresolved host and a missing repository give no `gh auth`;
- an SSH URL with a refused key gets the SSH line and no `gh auth`. An SSH URL with an
  `Authentication failed` error gets no `gh auth` either;
- Hypothesis: for any alias, any host and any of the sign-in errors, the alias and URL are named
  and the `gh auth` commands and the add command use that host, alias and URL.

Targeted mutations on `first_run_seed.py`, each killed:

- M1 the alias and URL dropped from the message;
- M2 401/403 not read as a sign-in;
- M3 a sign-in offered for every refusal;
- M4 the SSH line dropped;
- M5 a sign-in offered for SSH too;
- M6 `--default` dropped from the add command;
- M7 `unable to get password` not read as a sign-in;
- M8 a fixed host instead of the URL's.
