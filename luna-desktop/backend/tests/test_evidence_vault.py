import hashlib
import tempfile
import unittest
from pathlib import Path

from app.evidence_vault import EvidenceVault


class EvidenceVaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = EvidenceVault(Path(self.temp_dir.name) / "evidence")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_store_preserves_exact_bytes_and_sha256(self) -> None:
        raw = b"\x89PNG\r\n\x1a\nexact-screen-bytes"
        record = self.vault.store(
            project_id=1,
            data=raw,
            kind="screenshot",
            media_type="image/png",
            source="chat-upload",
            original_name="proof.png",
            sensitivity="classified",
        )
        self.assertEqual(record.byte_length, len(raw))
        self.assertEqual(record.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(record.sensitivity, "classified")
        self.assertEqual(self.vault.read_bytes(record.id, project_id=1), raw)
        self.assertTrue(self.vault.verify(record.id, project_id=1))

    def test_identical_bytes_share_blob_but_keep_separate_observations(self) -> None:
        raw = b"same-evidence"
        first = self.vault.store(
            project_id=1,
            data=raw,
            kind="stdout",
            media_type="text/plain",
            source="run-1",
        )
        second = self.vault.store(
            project_id=1,
            data=raw,
            kind="stdout",
            media_type="text/plain",
            source="run-2",
        )
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.sha256, second.sha256)
        blob = self.vault._blob_path(first.sha256)
        self.assertTrue(blob.exists())
        self.assertEqual(len(list(blob.parent.glob("*.blob"))), 1)

    def test_tamper_is_detected(self) -> None:
        record = self.vault.store(
            project_id=1,
            data=b"original",
            kind="log",
            media_type="text/plain",
            source="test",
        )
        self.vault._blob_path(record.sha256).write_bytes(b"tampered")
        self.assertFalse(self.vault.verify(record.id, project_id=1))
        with self.assertRaises(IOError):
            self.vault.read_bytes(record.id, project_id=1)

    def test_delete_project_garbage_collects_only_unreferenced_blob(self) -> None:
        shared = b"shared"
        first = self.vault.store(
            project_id=1,
            data=shared,
            kind="log",
            media_type="text/plain",
            source="p1",
        )
        self.vault.store(
            project_id=2,
            data=shared,
            kind="log",
            media_type="text/plain",
            source="p2",
        )
        unique = self.vault.store(
            project_id=1,
            data=b"unique",
            kind="log",
            media_type="text/plain",
            source="p1",
        )
        shared_blob = self.vault._blob_path(first.sha256)
        unique_blob = self.vault._blob_path(unique.sha256)

        self.assertEqual(self.vault.delete_project(1), 2)
        self.assertTrue(shared_blob.exists())
        self.assertFalse(unique_blob.exists())
        self.assertEqual(self.vault.stats(1)["records"], 0)
        self.assertEqual(self.vault.stats(2)["records"], 1)

    def test_project_scope_prevents_cross_project_read(self) -> None:
        record = self.vault.store(
            project_id=1,
            data=b"secret-proof",
            kind="artifact",
            media_type="application/octet-stream",
            source="test",
        )
        with self.assertRaises(FileNotFoundError):
            self.vault.read_bytes(record.id, project_id=2)


if __name__ == "__main__":
    unittest.main()
