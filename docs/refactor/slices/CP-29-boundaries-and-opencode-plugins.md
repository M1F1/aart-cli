# CP-29 — module boundaries as data, and OpenCode plugins as an artifact kind

Status: **in flight**. Step 1 is on `feat/cp-29-tach-and-opencode-plugins`.

Date opened: 2026-10-15. Authority: the product owner, after the 0.7.0 release: *"zajmij sie teraz
kolejnym CP w ktorym wdrozysz Tach i ogarniesz pluginy do opencode jako nowy rodzaj artefaktu
sprawdzajac go na superpowers ponadto sprawdzisz setup superpowers uzywajac skilli i memory i
przetestujesz go"*. The goal behind it: an enterprise fork of
[obra/superpowers](https://github.com/obra/superpowers) that a company installs into opencode
through aart-cli.

## Goal and scope

Two things, in order.

1. **#32: module boundaries as data.** tach goes into the dev group, `tach.toml` records the import
   graph the package has, and a `tach` gate refuses any edge the file does not declare.
2. **superpowers in opencode, two ways.**
   - First with what aart-cli already installs: the skills as Skill artifacts, and the bootstrap as
     Memory.
   - Then as a new artifact kind, an OpenCode plugin. The fork's plugin is installed as reviewed,
     vendored bytes. opencode does not fetch it from git at startup.

Out of scope: deleting the hand-written boundary tests in favour of tach rules (#32 step 3); the
import cycles tach found (B-186); plugins for harnesses other than opencode.

## Steps

**1. tach (#32 steps 1, 2 and 4, D-404).**
- `tach==0.35.3` is pinned in the dev group.
- `tach.toml` lists every top-level module of `aart_cli`, with `depends_on` written by `tach sync`
  and read by hand.
- `python scripts/quality.py tach` and `make tach` run `tach check`. The gate is part of
  `QUALITY_GATES`, so it runs in `pr-check` on every supported interpreter.
- Evidence:
  - an `aart_cli.io` import planted in `domain` turned the gate red, with nothing else red;
  - `tests/tach_config_test.py` holds that every top-level module is declared and that `domain`
    reaches only what `architecture_boundary_test.py` allows;
  - removing a module's entry turned the coverage test red.

**2. superpowers with Skills and Memory.** An enterprise fork's skills become Skill artifacts, and
the `using-superpowers` bootstrap becomes Memory (AGENTS.md). Both are installed into opencode from
a local Registry and checked live in the owner's opencode.

**3. Specify the plugin kind.** A specification amendment covering:
- what an OpenCode plugin is to aart-cli;
- vendored and digest-pinned, registered by local path rather than a git spec;
- high-risk execution on Ready;
- no install-time dependency fetch;
- opencode V1 (`plugin`) and V2 (`plugins`) registration;
- uninstall and verify.

**4. Implement the plugin kind end to end.**

**5. superpowers as a plugin.** The fork is installed through aart-cli and checked live.

**6. Full verification** (D-317), once steps 1–5 are done.
