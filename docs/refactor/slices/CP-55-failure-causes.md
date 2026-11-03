# CP-55 — A crash keeps what its exception was raised from

Status: **in progress**; the server's side (aart-cli-telemetry-server, branch `feat/failure-causes`)
merges first, then this PR.
Authority: Product Specification §215 (amended), INV-333, INV-334, INV-338, D-512. Resolves B-267.

## Why

Only the traceback of the exception that reached the boundary was read. When a handler raised a new
exception from another (`raise … from error`, or during `except`), the original's frames, often
where the defect is, were lost.

## What changed

- `docs/telemetry-api-v1.md`, `contract/telemetry-api-v1.examples.json`: the `failure` object's
  optional `causes`, 1–5 objects of `exception` and `frames`, only with `exception`; the fingerprint
  gains a sixth element only when there are causes, so every earlier fingerprint is unchanged; a
  valid example and two invalid ones; the versioning paragraph. Byte-identical with the server's,
  digests updated on both sides.
- `domain/failures.py`: `Cause`, `MAX_CAUSES`; `Failure.causes`, its fingerprint, document and
  `from_document`; `failure_of(..., causes=)` names each type as the failure's and keeps its frames
  the same way, the nearest five, only for a failure that names its exception.
- `io/failure_journal.py`: `_causes(error)` walks the chain as Python's traceback does: the explicit
  cause, else the context unless suppressed; an exception met again ends it. The journal keeps the
  document, so its schema is unchanged.
- `commands/report.py`: each cause after the frames, as "raised from <type>", with its frames.

## Evidence

- `failure_domain_test.TheCausesTest`: type and aart-cli frames in order; no causes means the same
  document and fingerprint as before; causes are part of the defect, their lines are not; the
  nearest five, an unnamable type is `Exception`; only a failure with an exception has causes; each
  causes document the contract refuses is refused with its own fingerprint.
- Hypothesis `test_whatever_causes_it_is_given_the_document_is_one_the_server_takes`.
- `failure_journal_test`: a real `raise … from` and an implicit context keep `ValueError` and its
  aart-cli frame, never the message; `from None` keeps none and a cycle ends; a chain of eight keeps
  five; `consume report` prints them.
- The contract's new valid example is one this client builds exactly, and both invalid ones are
  refused.
- Server e2e (`tests/test_e2e_aart_cli.py`) with this branch installed: the crash, raised from
  one in aart-cli, arrives with its cause. The same test with 0.25.0 fails, as it should.
- Targeted mutations, each killed by the test that names it:
  - A1 causes left out of the fingerprint;
  - A2 causes left out of the document;
  - A3 an empty `causes` list accepted;
  - A4 the context no longer followed;
  - A5 `from None` ignored;
  - A6 the cycle guard removed (the test never ends);
  - A7 more than five kept;
  - A9 causes kept without an exception;
  - A10 a cause with a field the contract does not have accepted;
  - A11 a cause's frames left out of the report;
  - A12 a cause's frames not read;
  - A13 the five-cause bound removed from `Failure`.
  - A8, `_causes` walking at most five, was equivalent, because `failure_of` keeps five, so the walk
    has no bound of its own.
- Server side:
  - the full quality gate in python:3.13;
  - the repository and failure tests on PostgreSQL 16;
  - mutations M1–M10 of the fingerprint, contract, stats, SQL and API, all killed. M1 and M8 first
    survived, and their tests were strengthened.
