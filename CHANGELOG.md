# Changelog

## [0.7.0](https://github.com/M1F1/aart-cli/compare/v0.6.0...v0.7.0) (2026-10-15)


### Added

* **maintainer:** remove an authoring Source from Maintainer Sources behind its own review, and add it again from Add Source ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** fold Remediation into Ready, the one final review, which lists the material changes AART will make ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** rename Maintainer Mode and Maintainer Dashboard to Registry Maintainer Mode and Registry Maintainer Dashboard, and screen 46 to Registry Workspace ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** show on each Marketplace row which harnesses already have that artifact installed ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** show only what the reader acts on in Fast, and name [v] More info / Less info ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** test one or several installed MCPs from Installed and Installed Artifact Details ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** tick several installations on Installed and uninstall them in one reviewed removal ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))


### Fixed

* **maintainer:** promote a new version into a Registry connected by its local path instead of refusing it as not configured ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **maintainer:** run Source Sync against the only connected Registry when none is the default instead of refusing it ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **maintainer:** say why a registry's approved state did not read instead of calling it not synchronized yet ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **mcp:** say whether an installed MCP declares no smoke_test or one with a key this version no longer accepts ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **registry:** list, read and disconnect a local Registry on Registries and Registry Maintainer like a Git one ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **registry:** make registry promote run and state each Candidate's validation and policy evidence instead of taking digests on the command line ([#62](https://github.com/M1F1/aart-cli/issues/62)) ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** after the configuration form, go on to Ready instead of asking for the harness again ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** give each list item one dash, and leave a heading over its list unmarked ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** name each change AART will make once, without impact lines repeating the list ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** open Doctor when one artifact is installed into two harnesses ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** report a defect in a running screen instead of restarting in the text terminal ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** return to Installed after an uninstall's receipt instead of reopening the same receipt ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** separate each configuration field with a blank line and drop the credential and storage text under the form ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** separate the credential briefing's sentences with blank lines when the TUI hands the terminal to the provider ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** show a Marketplace row as the offer alone, with its description under Verbose instead of cut off on the row ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** show why the text terminal took over, and where in the package a defect was raised ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** start each list item lower-case, separate items with a blank line, and wrap long lines instead of cutting them ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))
* **tui:** stop restating the ticked harnesses on the harness choice, and part statements on Installing, the MCP test and the Dashboard with blank lines ([4c970c3](https://github.com/M1F1/aart-cli/commit/4c970c31b149da0f5b6058bcdf06dc85d3ef0e95))

## [0.6.0](https://github.com/M1F1/aart-cli/compare/v0.5.0...v0.6.0) (2026-10-14)


### Added

* **mcp:** verify an installed MCP in two stages, installation configuration and MCP startup and protocol; a smoke_test block takes exactly tool, read_only, arguments and timeout_seconds ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))
* **tui:** offer "Test installed MCPs" on Success after an install that made MCP installations; the test runs only when confirmed and never changes the installation ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))


### Fixed

* **mcp:** accept JSON Schema annotations such as description and default in a server's tool schema ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))
* **mcp:** start an installed launcher with the harness it belongs to ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))
* **tui:** choose the harness before any installation input is asked ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))
* **tui:** show one row per installation in User Variables and Credentials ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))
* **tui:** treat a local Registry checkout as a Registry on the maintainer screens ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))


### Changed

* **mcp:** remove the harness route, which was mcp test --prompt, mcp test --report and mcp report, together with the expect and reaches_service smoke_test keys ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))


### Documentation

* describe the two smoke stages and the test after installation in the authoring and consumer guides ([5c9416d](https://github.com/M1F1/aart-cli/commit/5c9416dcbefaddb761433545fb791b7db0822dc2))

## [0.5.0](https://github.com/M1F1/aart-cli/compare/v0.4.1...v0.5.0) (2026-09-21)


### Added

* **config:** a release may bake one default Registry, so a first run starts connected ([38ed446](https://github.com/M1F1/aart-cli/commit/38ed4469ff68dae0a307e27792f87daf8056093b))


### Fixed

* **config:** a Git location carrying surrounding whitespace is refused on every interpreter ([38ed446](https://github.com/M1F1/aart-cli/commit/38ed4469ff68dae0a307e27792f87daf8056093b))

## [0.4.1](https://github.com/M1F1/aart-cli/compare/v0.4.0...v0.4.1) (2026-09-20)


### Fixed

* **docs:** the documented download names the repository it downloads from ([6e9f466](https://github.com/M1F1/aart-cli/commit/6e9f4660605ad552f2fb5f2ad9db162fc7f8f7df))
* **release:** run the console script by the name the wheel installs ([6e9f466](https://github.com/M1F1/aart-cli/commit/6e9f4660605ad552f2fb5f2ad9db162fc7f8f7df))


### Documentation

* **readme:** lead with the authenticated install and the TUI, say what you need as a list, and describe Marketplace as the view across one or several registries ([6e9f466](https://github.com/M1F1/aart-cli/commit/6e9f4660605ad552f2fb5f2ad9db162fc7f8f7df))

## [0.4.0](https://github.com/M1F1/aart-cli/compare/v0.3.0...v0.4.0) (2026-09-20)


### Added

* **authoring:** `aart-cli author check` answers with the parser and the compile rather than a lint ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **authoring:** `aart-cli author init` writes a full-surface workspace for guideline, hook, mcp, memory and skill ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **identity:** each installation owns its harness-visible name, credential address, configuration and runtime, and a collision is refused before anything is written ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **inputs:** every target collects its own configuration and credentials; nothing is shared or prefilled across installations ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **installed:** one row, one focus and one lookup address exactly one installation ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **mcp:** verify installed MCPs from the CLI over configuration, protocol, expectation and external-service stages, with an operator-run harness prompt and an attested report ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **paths:** one portable application home under `~/.aart-cli` or `AART_CLI_HOME` ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **protocol:** a deterministic AART YAML emitter, written as the parser's inverse ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **registry:** Registry Maintainer shows publication readiness and can push its validated local snapshot, never the default branch ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **registry:** review branches are named after the action that produced the commit ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **sources:** a Registry repository on this disk is a Registry, read one committed branch at a time ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))


### Fixed

* **authoring:** the smoke hint names a command the parser accepts ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **registry:** refuse to mix the two registry representations ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **registry:** stop shipping the maintainer's repository as a default ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))


### Changed

* **mcp:** the harness leg is operator-run -- AART composes a prompt and grades a report instead of driving a CLI ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **naming:** one command and one import package, with no second name anywhere the filesystem can see ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))
* **registry:** remove `registry scaffold` and the retired representation's schema, fixtures and branches ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))


### Documentation

* **readme:** open with the route a new user runs, say what AART is, and link the detail rather than inlining it ([12c83e8](https://github.com/M1F1/aart-cli/commit/12c83e8ffe86f8dee4796b7fa10b6c99f8d38201))

## [0.3.0](https://github.com/M1F1/aart-cli/compare/v0.2.0...v0.3.0) (2026-09-18)


### Added

* **registry:** let the git arm authenticate to a private AART copy ([3fa5ebb](https://github.com/M1F1/aart-cli/commit/3fa5ebbd903b818440cb1243082618bb461fe32e))


### Fixed

* **registry:** refuse to mix the two registry representations ([3fa5ebb](https://github.com/M1F1/aart-cli/commit/3fa5ebbd903b818440cb1243082618bb461fe32e))
* **registry:** run the registry's AART step under a POSIX shell ([3fa5ebb](https://github.com/M1F1/aart-cli/commit/3fa5ebbd903b818440cb1243082618bb461fe32e))
* **registry:** trust the workspace before the gates read it ([3fa5ebb](https://github.com/M1F1/aart-cli/commit/3fa5ebbd903b818440cb1243082618bb461fe32e))

## [0.2.0](https://github.com/M1F1/aart-cli/compare/v0.1.2...v0.2.0) (2026-09-17)


### Added

* **details:** name the exact paths an installation owns ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **install:** let one installation choose its scope without changing the preference ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **install:** let one installation choose pip or uv without changing the preference ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **install:** let the review screen choose where an installation lands ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **reporting:** withdraw GitHub-issue usage reports and the registry dashboard ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))


### Fixed

* **ci:** validate PR titles early and assemble fake tokens at runtime ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **inputs:** draw screen 22a's two sections as two ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **inputs:** part one artifact's inputs from the next on screen 22 ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **maintainer:** count Candidates by whether anyone can still act on them ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))
* **marketplace:** lead a row with installation state and harnesses, not prose ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))


### Documentation

* **install:** install a release wheel by copying its link ([04241e8](https://github.com/M1F1/aart-cli/commit/04241e8917d534aab6b3c2f2357edbadf56df908))

## [0.1.2](https://github.com/M1F1/aart-cli/compare/v0.1.1...v0.1.2) (2026-09-17)


### Fixed

* **install:** name one Python backend per dependency contract in a review ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))
* **install:** say which step of an installation is running ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))
* **maintainer:** keep the local state loadable when one Source's history is stale ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))
* **maintainer:** name the repair for a stale Candidate history and let Sync perform it ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))
* **maintainer:** pin a Source revision only once its Candidates are reconciled ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))
* **requirements:** let an executable requirement name the file it really is ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))
* **review:** count what each change is, not which effect kind carries it ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))


### Documentation

* **cp-24:** record the field reports, the decisions and the manual checks ([ba443a6](https://github.com/M1F1/aart-cli/commit/ba443a6596e0cc8b5e909ddf3683176b7ffc2dda))

## [0.1.1](https://github.com/M1F1/aart-cli/compare/v0.1.0...v0.1.1) (2026-09-15)


### Fixed

* **release:** install the build tools before the release run builds ([#5](https://github.com/M1F1/aart-cli/issues/5)) ([7545869](https://github.com/M1F1/aart-cli/commit/75458691ca05ca4d135a23c8bbe2b868006690d8))

## [0.1.0](https://github.com/M1F1/aart-cli/compare/v0.0.1...v0.1.0) (2026-09-15)


### Added

* **authoring:** compile explicit aart.yaml and aart.json manifests that declare an artifact's payload, inputs, dependencies and setup ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **ci:** give generated registries an aggregate quality gate ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **credentials:** keep credential references apart from values, explain each credential where it is asked for, and set absent ones from the TUI ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **doctor:** report offline readiness, ignored configuration, credential health and the audit trail, and apply one reviewed repair ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **install:** deliver Skills, memory files, hooks and MCP servers where Claude, Codex and OpenCode read them ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **install:** install, update and remove artifacts through canonical transactions whose receipts record what was installed, why, and from which object ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **install:** keep configuration per harness beside the artifact and edit it after installation ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **marketplace:** resolve selections and plan an installation from immutable environment facts into one reviewed plan ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **registry:** adopt artifacts from repositories that are not a Source and check them against their upstream ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **registry:** promote Candidates into an approved Registry snapshot, singly or in bulk, as one reviewed transaction ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **runtime:** give each Python artifact an environment it owns and start installed artifacts without AART ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **setup:** run an artifact's declared setup and keep the effects of a failed or stopped run inspectable ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **sources:** admit registry and authoring repositories as Sources and keep the last-known-good snapshot installable when a sync is refused ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **tui:** add maintainer mode for Sources, Candidates, validation, policy, promotion, registry initialization, rebuild and publication to a review branch ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **tui:** add the consumer application for the Marketplace, install review, installed artifacts, Registries and settings ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))


### Fixed

* **registry:** rebind approved versions to each promotion snapshot and maintain the registry a promotion writes ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))
* **release:** tag as vX.Y.Z and stop rewriting versions into the README ([#3](https://github.com/M1F1/aart-cli/issues/3)) ([8e3bd1b](https://github.com/M1F1/aart-cli/commit/8e3bd1bbe6dfa36200eb071b4147c5630816c0e4))
* **tui:** draw every screen on one frame with cursor rows, a contextual key legend and detail behind Verbose ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))


### Changed

* **tui:** remove the legacy curses and text wizard shells ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))


### Documentation

* **ci:** add a walkthrough for rolling AART and a company registry out on GitHub Enterprise Server ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))


### Packaging

* adopt Release Please so versions and the CHANGELOG come from Conventional Commit titles ([5d21a26](https://github.com/M1F1/aart-cli/commit/5d21a26c65ba09139a4c2bd2227b8189a5749ea9))

## Changelog

All notable AART changes are documented here. The project follows semantic versioning for the
executable; protocol, schema, artifact, importer, profile, and registry versions remain independent.

Release Please writes this file from the Conventional Commit titles that reach `main`, and inserts
each new release below this paragraph.
