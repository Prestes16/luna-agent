import unittest
from types import SimpleNamespace

from app.execution_intent import BLOCKED, ON_DEMAND
from app.response_attestation import build_response_execution_actions, build_response_execution_intents


class ResponseExecutionIntentTests(unittest.TestCase):
    def _engine(self, *, target: str, scope: str | None):
        scenario = SimpleNamespace(
            target=target,
            current_goal="validar serviço",
            environment="Kali Linux",
            scope=scope,
            observed_facts=[],
        )
        return SimpleNamespace(scenario_contexts={"s": scenario})

    def test_visible_probe_is_bound_to_confirmed_scenario_target(self) -> None:
        engine = self._engine(target="10.10.10.5", scope="CTF autorizado")
        intents = build_response_execution_intents(
            engine,
            "s",
            "Luna, rode esse nmap no alvo autorizado.",
            "nmap -sV 10.10.10.5\nDepois verificar a resposta.",
        )
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["authority"], ON_DEMAND)
        self.assertEqual(intents[0]["target"], "10.10.10.5")
        self.assertGreater(intents[0]["readiness_index"], 0.8)

    def test_execution_action_preserves_exact_operator_visible_command(self) -> None:
        engine = self._engine(target="10.10.10.5", scope="CTF autorizado")
        response = "nmap -sV 10.10.10.5"
        actions = build_response_execution_actions(
            engine,
            "s",
            "Luna, rode esse nmap no alvo autorizado.",
            response,
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["command"], response)
        self.assertEqual(actions[0]["authority"], ON_DEMAND)
        self.assertEqual(actions[0]["target"], "10.10.10.5")

    def test_visible_command_with_target_mismatch_is_blocked(self) -> None:
        engine = self._engine(target="10.10.10.5", scope="CTF autorizado")
        intents = build_response_execution_intents(
            engine,
            "s",
            "Luna, rode esse nmap no alvo autorizado.",
            "nmap -sV 10.10.10.6",
        )
        self.assertEqual(intents[0]["authority"], BLOCKED)
        self.assertIn("target_scope_mismatch", intents[0]["reasons"])

    def test_execution_word_without_confirmed_scope_does_not_grant_probe(self) -> None:
        engine = self._engine(target="10.10.10.5", scope=None)
        intents = build_response_execution_intents(
            engine,
            "s",
            "rode o teste",
            "nmap -sV 10.10.10.5",
        )
        self.assertEqual(intents[0]["authority"], BLOCKED)
        self.assertIn("scope_not_confirmed", intents[0]["reasons"])


if __name__ == "__main__":
    unittest.main()
