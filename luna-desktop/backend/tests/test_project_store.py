import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.project_store import ProjectStore, ProjectValidationError


class ProjectStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ProjectStore(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_utf8_crud_and_atomic_files(self) -> None:
        project = self.store.create_project({
            "name": "Auditoria São Paulo",
            "path": r"D:\LunaCyber\alvo",
            "project_type": "bounty",
            "description": "Revisão local",
            "color": "purple",
        })
        self.assertEqual(project["id"], 1)
        self.assertEqual(self.store.list_projects()[0]["name"], "Auditoria São Paulo")

        message = self.store.add_message(1, {
            "role": "user",
            "content": "Verifique validação de PDA.",
            "model": "luna-cyber-fast",
        })
        self.assertEqual(message["project_id"], 1)
        self.assertEqual(self.store.add_fact(1, "Escopo autorizado"), ["Escopo autorizado"])
        self.assertIn("Escopo autorizado", self.store.context(1))

        updated = self.store.update_project(1, {"pinned": True})
        self.assertTrue(updated["pinned"])
        self.assertFalse(list(Path(self.temp_dir.name).rglob("*.tmp")))

        self.store.delete_project(1)
        self.assertEqual(self.store.list_projects(), [])
        self.assertFalse((Path(self.temp_dir.name) / "1").exists())

    def test_rejects_unsafe_names_paths_and_fields(self) -> None:
        with self.assertRaises(ProjectValidationError):
            self.store.create_project({"name": "../escape", "project_type": "other", "color": "cyan"})
        with self.assertRaises(ProjectValidationError):
            self.store.create_project({"name": "Seguro", "path": "../escape", "project_type": "other", "color": "cyan"})

        self.store.create_project({"name": "Seguro", "project_type": "other", "color": "cyan"})
        with self.assertRaises(ProjectValidationError):
            self.store.update_project(1, {"unexpected": True})

    def test_retrieval_context_separates_semantic_and_episodic_memory(self) -> None:
        self.store.create_project({
            "name": "Anchor Audit",
            "project_type": "solana",
            "color": "green",
        })
        self.store.add_fact(1, "O settlement usa USDC SPL com 6 decimais.")
        self.store.add_fact(1, "A interface possui tema escuro.")
        self.store.add_message(1, {
            "role": "user",
            "content": "Auditar cálculo de fee e overflow em amount u64.",
            "model": "luna-cyber-fast",
        })
        self.store.add_message(1, {
            "role": "luna",
            "content": "Precisamos verificar os limites reais de amount.",
            "model": "luna-cyber-fast",
        })

        context = self.store.retrieval_context(1, "fee overflow USDC amount")
        self.assertIn("SEMANTIC DURABLE FACTS:", context)
        self.assertIn("USDC SPL", context)
        self.assertIn("EPISODIC RECENT/RELEVANT:", context)
        self.assertIn("amount u64", context)
        self.assertIn("backend=local-sqlite", context)
        self.assertIn("vector_backend=not_enabled", context)
        self.assertIn("semantic_response_cache=off", context)
        self.assertIn("project_store:facts.json", context)

    def test_memory_plane_keeps_llm_output_out_of_facts_and_preserves_credentials(self) -> None:
        self.store.create_project({
            "name": "Memory Integrity",
            "project_type": "bounty",
            "color": "red",
        })
        self.store.add_fact(1, "GET /admin retornou 403.")
        self.store.add_message(1, {
            "role": "luna",
            "content": "Authorization: Bearer TEST_TOKEN_123\nRCE confirmada em /admin.",
            "model": "luna-cyber-fast",
        })

        persisted = self.store.list_messages(1)[0]["content"]
        self.assertIn("TEST_TOKEN_123", persisted)

        records = self.store.memory_plane.list_records(1, limit=20)
        fact_records = [item for item in records if item.kind == "operator_fact"]
        model_records = [item for item in records if item.evidence_level == "model_output"]
        self.assertEqual(len(fact_records), 1)
        self.assertEqual(len(model_records), 1)
        self.assertEqual(model_records[0].kind, "episode")
        self.assertFalse(model_records[0].secret_redacted)
        self.assertEqual(model_records[0].sensitivity, "credential")

        context = self.store.retrieval_context(1, "admin RCE")
        semantic = context.split("EPISODIC RECENT/RELEVANT:", 1)[0]
        self.assertIn("GET /admin retornou 403.", semantic)
        self.assertNotIn("RCE confirmada", semantic)
        self.assertIn("RCE confirmada", context)
        self.assertIn("TEST_TOKEN_123", context)

    def test_project_store_persists_report_grade_evidence(self) -> None:
        self.store.create_project({
            "name": "Evidence",
            "project_type": "bounty",
            "color": "orange",
        })
        raw = b"HTTP/1.1 200 OK\r\nX-Proof: yes\r\n"
        record = self.store.add_evidence_artifact(
            1,
            data=raw,
            kind="http-response",
            media_type="message/http",
            source="curl",
            original_name="response.txt",
            sensitivity="sensitive",
        )
        self.assertEqual(record["byte_length"], len(raw))
        self.assertTrue(self.store.verify_evidence_artifact(1, record["id"]))

        listed = self.store.list_evidence_artifacts(1)
        self.assertEqual(len(listed), 1)
        metadata, restored = self.store.read_evidence_artifact(1, record["id"])
        self.assertEqual(metadata["sha256"], record["sha256"])
        self.assertEqual(restored, raw)

        self.store.delete_project(1)
        self.assertEqual(self.store.evidence_vault.stats(1)["records"], 0)

    def test_compression_preserves_recent_messages(self) -> None:
        self.store.create_project({"name": "Contexto", "project_type": "research", "color": "green"})
        for index in range(24):
            self.store.add_message(1, {
                "role": "user" if index % 2 == 0 else "luna",
                "content": f"Mensagem {index}",
                "model": "luna-cyber-fast",
            })
        result = self.store.compress(1)
        messages = self.store.list_messages(1)
        self.assertEqual(result, {"before": 24, "after": 11, "compressed": 14})
        self.assertTrue(messages[0]["is_compressed"])
        self.assertEqual(messages[-1]["content"], "Mensagem 23")


class ProjectApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_store = main.project_store
        main.project_store = ProjectStore(self.temp_dir.name)
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.project_store = self.previous_store
        self.temp_dir.cleanup()

    def test_endpoints_used_by_projects_page(self) -> None:
        created = self.client.post("/api/projects", json={
            "name": "API Local",
            "path": r"D:\LunaCyber\workspace",
            "project_type": "app",
            "description": "Somente local",
            "color": "cyan",
        })
        self.assertEqual(created.status_code, 201)
        project_id = created.json()["id"]
        self.assertEqual(self.client.get("/api/projects").status_code, 200)

        saved = self.client.post(f"/api/projects/{project_id}/messages", json={
            "role": "user", "content": "Olá Luna", "model": "luna-cyber-fast",
        })
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(self.client.get(f"/api/projects/{project_id}/messages").json()["messages"][0]["content"], "Olá Luna")
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/facts", json={"fact": "Teste local"}).status_code, 201)
        self.assertIn("Teste local", self.client.get(f"/api/projects/{project_id}/context").json()["context"])
        self.assertEqual(self.client.put(f"/api/projects/{project_id}", json={"pinned": True}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/compress").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/projects/{project_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{project_id}/messages").status_code, 404)

    def test_project_evidence_api_preserves_exact_attachment(self) -> None:
        created = self.client.post("/api/projects", json={
            "name": "Evidence API",
            "project_type": "bounty",
            "color": "red",
        })
        self.assertEqual(created.status_code, 201)
        project_id = created.json()["id"]

        raw = b"\x89PNG\r\n\x1a\nreport-proof"
        uploaded = self.client.post(
            f"/api/projects/{project_id}/evidence",
            params={
                "kind": "screenshot",
                "sensitivity": "classified",
                "description": "proof screen",
            },
            files={"file": ("proof.png", raw, "image/png")},
        )
        self.assertEqual(uploaded.status_code, 201)
        metadata = uploaded.json()
        self.assertEqual(metadata["byte_length"], len(raw))
        self.assertEqual(metadata["kind"], "screenshot")
        self.assertEqual(metadata["sensitivity"], "classified")

        listed = self.client.get(f"/api/projects/{project_id}/evidence")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["evidence"]), 1)

        downloaded = self.client.get(
            f"/api/projects/{project_id}/evidence/{metadata['id']}"
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, raw)
        self.assertEqual(
            downloaded.headers["x-evidence-sha256"],
            metadata["sha256"],
        )

        verified = self.client.get(
            f"/api/projects/{project_id}/evidence/{metadata['id']}/verify"
        )
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.json()["valid"])

    def test_api_rejects_traversal_and_extra_fields(self) -> None:
        traversal = self.client.post("/api/projects", json={
            "name": "../escape", "project_type": "other", "color": "cyan",
        })
        self.assertEqual(traversal.status_code, 422)
        extra = self.client.post("/api/projects", json={
            "name": "Seguro", "project_type": "other", "color": "cyan", "admin": True,
        })
        self.assertEqual(extra.status_code, 422)


if __name__ == "__main__":
    unittest.main()
