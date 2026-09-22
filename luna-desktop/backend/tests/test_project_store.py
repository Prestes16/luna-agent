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
