import base64
import hashlib
import unittest

from app.luna_engine import LunaEngine
from app.visual_evidence import (
    build_visual_evidence_manifest,
    model_supports_visual_reasoning,
    visual_evidence_guidance,
)


class VisualEvidenceTests(unittest.TestCase):
    def test_manifest_preserves_exact_image_hash_and_size(self) -> None:
        raw = b"not-a-real-png-but-exact-evidence-bytes"
        encoded = base64.b64encode(raw).decode("ascii")
        manifest = build_visual_evidence_manifest([
            {"data": encoded, "mime": "image/png"},
        ])
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0].byte_length, len(raw))
        self.assertEqual(manifest[0].sha256, hashlib.sha256(raw).hexdigest())

    def test_engine_transports_image_to_openai_compatible_ollama_content(self) -> None:
        encoded = base64.b64encode(b"screen").decode("ascii")
        content = LunaEngine._build_vision_content(
            "Leia esta captura.",
            [{"data": encoded, "mime": "image/png"}],
            "ollama",
        )
        self.assertEqual(content[0]["type"], "image_url")
        self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(content[-1], {"type": "text", "text": "Leia esta captura."})

    def test_visual_reasoning_requires_explicit_vision_capability(self) -> None:
        self.assertTrue(model_supports_visual_reasoning(["completion", "vision", "tools"]))
        self.assertTrue(model_supports_visual_reasoning(["VISION"]))
        self.assertFalse(model_supports_visual_reasoning(["completion", "tools"]))
        self.assertFalse(model_supports_visual_reasoning([]))
        self.assertFalse(model_supports_visual_reasoning(None))

    def test_invalid_base64_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_visual_evidence_manifest([
                {"data": "%%%", "mime": "image/png"},
            ])

    def test_unsupported_mime_is_rejected(self) -> None:
        encoded = base64.b64encode(b"x").decode("ascii")
        with self.assertRaises(ValueError):
            build_visual_evidence_manifest([
                {"data": encoded, "mime": "application/octet-stream"},
            ])

    def test_guidance_separates_observation_from_inference(self) -> None:
        encoded = base64.b64encode(b"screen").decode("ascii")
        manifest = build_visual_evidence_manifest([
            {"data": encoded, "mime": "image/jpeg"},
        ])
        guidance = visual_evidence_guidance(manifest)
        self.assertIn("OBSERVED visual facts", guidance)
        self.assertIn("INFERENCE", guidance)
        self.assertIn("Never invent obscured/cropped text", guidance)
        self.assertIn("sha256=", guidance)


if __name__ == "__main__":
    unittest.main()
