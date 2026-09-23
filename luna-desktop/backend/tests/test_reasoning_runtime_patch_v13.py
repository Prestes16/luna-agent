import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class MalwareRuntimeGuardTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_direct_sample_execution_without_sandbox_is_rejected(self) -> None:
        validation = self._validate(
            "Quero analisar um malware sample.py no meu ambiente.",
            "```bash\npython3 sample.py\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("malware_direct_execution_without_isolated_sandbox", validation.reasons)

    def test_explicit_isolated_vm_removes_v13_execution_reason(self) -> None:
        validation = self._validate(
            "Na minha VM isolada e descartável, quero análise dinâmica do malware sample.py.",
            "```bash\npython3 sample.py\n```",
        )
        self.assertNotIn("malware_direct_execution_without_isolated_sandbox", validation.reasons)

    def test_wine_sample_execution_without_sandbox_is_rejected(self) -> None:
        validation = self._validate(
            "Quero analisar o malware sample.exe no host.",
            "```bash\nwine sample.exe\n```",
        )
        self.assertIn("malware_direct_execution_without_isolated_sandbox", validation.reasons)

    def test_relative_binary_execution_without_sandbox_is_rejected(self) -> None:
        validation = self._validate(
            "Quero analisar este malware sample.",
            "```bash\n./sample\n```",
        )
        self.assertIn("malware_direct_execution_without_isolated_sandbox", validation.reasons)
    def test_ransomware_decryption_guarantee_is_rejected(self) -> None:
        validation = self._validate(
            "Analise este ransomware e avalie se existe recuperação.",
            "Este procedimento garante 100% a descriptografia e recuperação dos arquivos.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("ransomware_decryption_overclaim", validation.reasons)

    def test_static_yara_analysis_is_not_blocked_as_sample_execution(self) -> None:
        validation = self._validate(
            "Analise o malware sample.exe usando a regra rules.yar.",
            "```bash\nyara rules.yar sample.exe\n```",
        )
        self.assertNotIn("malware_direct_execution_without_isolated_sandbox", validation.reasons)


if __name__ == "__main__":
    unittest.main()
