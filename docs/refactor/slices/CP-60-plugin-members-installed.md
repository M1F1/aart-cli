# CP-60 — A plugin's skills are sent as installed, updated and removed with it

Status: **done** on its branch; merged with its PR.
Authority: Product Specification §214 (amended), D-517.

## Why

The server listed superpowers' skills as used but never installed, so it could not say how many
installations hold one. The owner asked that installing a plugin or Collection raises the installs
of each artifact it brings.

## What changed

- `domain/telemetry.lifecycle_event(..., member=)`: a member's event is the skill
  `<plugin>:<member>` at the plugin's version.
- `application/telemetry_events.lifecycle_events`: the plugin's event, then one per member.
- `ReceiptArtifactView.members`, written as `members` only when non-empty and read back.
- `application/receipt_recording._with_members`: fills it from each plugin's `PlacedArtifactReceipt`.
- `application/installation_action`: the completed action carries the recorded receipt, so the flow
  and Activity agree.
- Spec §214, D-517.

## Evidence

- `tests/plugin_installation_e2e_test.py::test_installing_and_removing_it_is_sent_for_the_plugin_and_each_of_its_skills`:
  a real install and uninstall of a plugin, synchronised to a fake server, sends installed and
  removed for the plugin and for each of its two skills at its version.
- `tests/telemetry_domain_test.py::test_a_plugins_skill_is_a_skill_named_after_it_at_its_version`.
- `tests/installation_transaction_receipt_test.py::test_a_plugins_skills_round_trip_and_are_written_only_when_it_has_some`.
- A lab used the real superpowers 6.2.0 (14 skills), three installations, one uninstall, and
  PostgreSQL 16. The server showed each skill with 3 installs, 1 removal and 2 holders.
- 1119 tests across the 99 related files passed.

Targeted mutations, each killed:

- M1 a member keeps the plugin's kind;
- M2 a member named without its plugin;
- M3 no receipt's members read;
- M4 the view not given them;
- M5 `members` written when empty;
- M6 `members` not read back;
- M7 no member event;
- M8 the flow keeps the presented outcome.
