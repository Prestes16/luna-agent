import unittest

# Importing the app activates all runtime reasoning patches.
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.reasoning_quality import build_operator_contract, score_response_quality
from app.scenario_context import ScenarioContext


PROMPT = (
    "Luna, estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
    "https://wifhoodie.com. Me dê o comando bash para eu executar no meu Kali Linux."
)


class ReasoningQualityTests(unittest.TestCase):
    def test_contract_recognizes_yara_before_sentence_punctuation(self) -> None:
        contract = build_operator_contract("Quero usar yara. Me dê o comando para eu executar.")
        self.assertEqual(contract.requested_tool, "yara")
        self.assertTrue(contract.wants_command)
        self.assertTrue(contract.operator_executes)

    def test_contract_extracts_tool_target_and_delivery(self) -> None:
        contract = build_operator_contract(PROMPT)
        self.assertEqual(contract.requested_tool, "nmap")
        self.assertEqual(contract.target_hosts, ("wifhoodie.com",))
        self.assertTrue(contract.wants_command)
        self.assertTrue(contract.wants_bash)
        self.assertTrue(contract.operator_executes)

    def test_contract_recognizes_exactly_one_command_wording(self) -> None:
        contract = build_operator_contract(
            "Target http://127.0.0.1:8080. Forneça EXATAMENTE UM comando, sem executá-lo."
        )
        self.assertTrue(contract.wants_command)
        self.assertTrue(contract.one_command)
        self.assertEqual(contract.target_hosts, ("127.0.0.1",))

    def test_correct_nmap_command_scores_high(self) -> None:
        response = "```bash\nnmap -sV -sC wifhoodie.com -oN wifhoodie_initial.txt\n```"
        score = score_response_quality(PROMPT, response)
        self.assertGreaterEqual(score.total, 0.85)

    def test_wrong_tool_scores_low(self) -> None:
        response = "```bash\ncurl -I https://wifhoodie.com\n```"
        score = score_response_quality(PROMPT, response)
        self.assertLess(score.total, 0.62)

    def test_missing_command_scores_low(self) -> None:
        response = "Use o Nmap para verificar o alvo e depois analise os resultados."
        score = score_response_quality(PROMPT, response)
        self.assertLess(score.total, 0.62)

    def test_active_validator_rejects_low_quality_command_response(self) -> None:
        scenario = ScenarioContext()
        delta = scenario.update(PROMPT)
        validation = validate_model_response(
            message=PROMPT,
            response="Use Nmap, mas sem comando por enquanto.",
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertFalse(validation.valid)
        self.assertIn("quality_gate_below_threshold", validation.reasons)


if __name__ == "__main__":
    unittest.main()
