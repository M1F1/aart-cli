# Changelog

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
