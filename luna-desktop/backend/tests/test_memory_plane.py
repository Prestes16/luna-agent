import tempfile
import unittest
from pathlib import Path

from app.memory_plane import MemoryPlane


class MemoryPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plane = MemoryPlane(Path(self.temp_dir.name) / "memory.sqlite3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_typed_records_redact_secrets_and_preserve_provenance(self) -> None:
        record = self.plane.add_record(
            project_id=1,
            kind="evidence",
            content="Authorization: Bearer super-secret-token\nHTTP/1.1 200 OK",
            provenance="operator:terminal",
            source="curl-output",
            evidence_level="observed",
        )
        self.assertEqual(record.kind, "evidence")
        self.assertEqual(record.provenance, "operator:terminal")
        self.assertTrue(record.secret_redacted)
        self.assertNotIn("super-secret-token", record.content)
        self.assertIn("[REDACTED]", record.content)

    def test_model_output_stays_episode_not_durable_fact(self) -> None:
        self.plane.add_record(
            project_id=1,
            kind="operator_fact",
            content="O endpoint /admin retornou 403.",
            provenance="project_store:facts.json",
            source="project_fact",
            evidence_level="declared",
        )
        self.plane.add_record(
            project_id=1,
            kind="episode",
            content="RCE confirmada no endpoint /admin.",
            provenance="project_store:messages.json",
            source="conversation:luna",
            evidence_level="model_output",
        )
        context = self.plane.retrieval_context(1, "admin RCE")
        semantic = context.split("HYPOTHESES", 1)[0].split("EPISODIC", 1)[0]
        self.assertIn("O endpoint /admin retornou 403.", semantic)
        self.assertNotIn("RCE confirmada", semantic)
        self.assertIn("EPISODIC RECENT/RELEVANT:", context)
        self.assertIn("model_output", context)

    def test_hypothesis_is_explicitly_non_factual(self) -> None:
        self.plane.add_record(
            project_id=1,
            kind="hypothesis",
            content="Pode existir bypass de autorização em /admin.",
            provenance="llm:hypothesis",
            source="reasoning",
            evidence_level="hypothesis",
        )
        context = self.plane.retrieval_context(1, "bypass admin")
        self.assertIn("HYPOTHESES — NOT FACTS:", context)
        self.assertIn("Pode existir bypass", context)

    def test_source_hash_deduplicates_same_memory_identity(self) -> None:
        first = self.plane.add_record(
            project_id=1,
            kind="operator_fact",
            content="Settlement em USDC.",
            provenance="operator",
            source="project_fact",
            evidence_level="declared",
            dedupe_key="fact:settlement-usdc",
        )
        second = self.plane.add_record(
            project_id=1,
            kind="operator_fact",
            content="Settlement em USDC.",
            provenance="operator",
            source="project_fact",
            evidence_level="declared",
            dedupe_key="fact:settlement-usdc",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.plane.stats(1)["records"], 1)

    def test_superseded_memory_is_not_retrieved_as_active(self) -> None:
        old = self.plane.add_record(
            project_id=1,
            kind="evidence",
            content="GET /admin retornou 403.",
            provenance="operator:test-1",
            source="http",
            evidence_level="observed",
        )
        new = self.plane.add_record(
            project_id=1,
            kind="evidence",
            content="GET /admin retornou 200 após mudança de estado.",
            provenance="operator:test-2",
            source="http",
            evidence_level="observed",
            supersedes=old.id,
            dedupe_key="admin-state-2",
        )
        self.assertEqual(self.plane.get(old.id).status, "superseded")
        self.assertEqual(new.status, "active")
        active = self.plane.search(1, "admin", kinds=("evidence",), limit=10)
        self.assertEqual([item.id for item in active], [new.id])

    def test_local_status_keeps_response_cache_and_vectors_disabled(self) -> None:
        status = self.plane.stats()
        self.assertFalse(status["semantic_response_cache_enabled"])
        self.assertFalse(status["vector_backend_enabled"])


if __name__ == "__main__":
    unittest.main()
