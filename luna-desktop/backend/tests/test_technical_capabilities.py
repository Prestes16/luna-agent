import unittest

from app.technical_capabilities import select_capabilities, technical_guidance


class TechnicalCapabilityTests(unittest.TestCase):
    def test_web_and_programming_can_be_selected_together(self) -> None:
        selected = select_capabilities(
            "Quero criar em Python um scanner para uma API HTTP no meu laboratório.",
            limit=3,
        )
        names = {item.name for item in selected}
        self.assertIn("web_api", names)
        self.assertIn("programming_automation", names)

    def test_exploit_dev_context_is_available_without_execution(self) -> None:
        selected = select_capabilities(
            "Preciso estudar um crash e criar um fuzz harness para exploit dev em CTF.",
            limit=3,
        )
        self.assertIn("exploit_dev", {item.name for item in selected})

    def test_guidance_requires_complete_operator_reviewable_artifacts(self) -> None:
        guidance = technical_guidance(
            "Crie um script PowerShell para auditar configuração Windows.",
        )
        self.assertIn("instruction-only", guidance)
        self.assertIn("complete operator-reviewable code/config/tests", guidance)
        self.assertIn("Never claim execution", guidance)
        self.assertLessEqual(len(guidance), 1200)

    def test_malware_capability_exposes_native_managed_and_script_runtimes(self) -> None:
        guidance = technical_guidance(
            "Preciso analisar malware ransomware .NET PowerShell VBA e x64.",
        )
        self.assertIn("malware_forensics", guidance)
        self.assertIn(".NET C#/IL", guidance)
        self.assertIn("PowerShell/VBScript/VBA", guidance)
        self.assertIn("x86/x64/ARM", guidance)

    def test_programming_capability_covers_advanced_reverse_engineering_languages(self) -> None:
        guidance = technical_guidance(
            "Preciso programar análise para malware Delphi Pascal Nim Zig MIPS.",
        )
        self.assertIn("programming_automation", guidance)
        self.assertIn("Delphi/Pascal/Nim/Zig", guidance)
        self.assertIn("embedded architectures", guidance)
    def test_math_physics_capability_covers_numeric_and_signal_reasoning(self) -> None:
        selected = select_capabilities(
            "Audite rounding overflow probabilidade entropia e SNR em um sistema.",
            limit=4,
        )
        names = {item.name for item in selected}
        self.assertIn("math_physics", names)
        guidance = technical_guidance(
            "Analise matemática aplicada: fixed-point, overflow, entropia, timing e SNR.",
        )
        self.assertIn("math_physics", guidance)
        self.assertIn("integer/modular arithmetic", guidance)
        self.assertIn("dimensional analysis", guidance)

    def test_irrelevant_greeting_does_not_inject_capability_context(self) -> None:
        self.assertEqual(technical_guidance("Olá, bom dia!"), "")


if __name__ == "__main__":
    unittest.main()
