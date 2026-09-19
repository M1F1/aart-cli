from __future__ import annotations

import tempfile
import unittest

from aart_cli.application.store import (
    ReferenceUpdatePorts,
    ReferenceUpdateRequest,
    StoreGcPorts,
    collect_garbage,
    object_status,
    replace_references,
)
from aart_cli.domain.result import Ok
from aart_cli.io.object_store import (
    delete_object,
    inventory_objects,
    publish_object,
    read_object,
)
from aart_cli.io.reference_store import read_references, write_references
from aart_cli.io.store_lock import acquire_store_lock, release_store_lock
from aart_cli.protocol.native_tree import SnapshotEntry, SnapshotEntryKind
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.store.model import (
    GcRequest,
    ObjectPublishCommand,
    ObjectReadRequest,
    ObjectStatusKind,
    ReferenceKind,
    make_object_candidate,
    object_store_paths,
)


def _candidate(content: bytes):
    path = parse_relative_path("artifact.json")
    assert isinstance(path, Ok)
    result = make_object_candidate((SnapshotEntry(path.value, SnapshotEntryKind.FILE, content),))
    assert isinstance(result, Ok)
    return result.value


class StoreE2ETest(unittest.TestCase):
    def test_reference_protects_one_object_while_execute_gc_collects_only_the_other(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = object_store_paths(root)
            retained = _candidate(b"retained")
            collectable = _candidate(b"collectable")
            self.assertIsInstance(publish_object(ObjectPublishCommand(paths, retained)), Ok)
            self.assertIsInstance(publish_object(ObjectPublishCommand(paths, collectable)), Ok)
            reference_ports = ReferenceUpdatePorts(
                acquire_store_lock,
                release_store_lock,
                read_references,
                write_references,
            )
            self.assertIsInstance(
                replace_references(
                    ReferenceUpdateRequest(
                        paths,
                        ReferenceKind.SOURCE_CURRENT,
                        "source/reference",
                        (retained.digest,),
                    ),
                    reference_ports,
                ),
                Ok,
            )
            gc_ports = StoreGcPorts(
                acquire_store_lock,
                release_store_lock,
                read_references,
                inventory_objects,
                delete_object,
            )

            dry_run = collect_garbage(GcRequest(paths), gc_ports)
            executed = collect_garbage(GcRequest(paths, execute=True), gc_ports)

            self.assertIsInstance(dry_run, Ok)
            self.assertIsInstance(executed, Ok)
            assert isinstance(dry_run, Ok)
            assert isinstance(executed, Ok)
            self.assertEqual(dry_run.value.plan.candidates, (collectable.digest,))
            self.assertEqual(executed.value.deleted, (collectable.digest,))
            self.assertIsInstance(read_object(ObjectReadRequest(paths, retained.digest)), Ok)
            self.assertIs(
                object_status(ObjectReadRequest(paths, retained.digest), read_object).kind,
                ObjectStatusKind.VERIFIED,
            )
            self.assertEqual(read_object(ObjectReadRequest(paths, collectable.digest)), Ok(None))


if __name__ == "__main__":
    unittest.main()
