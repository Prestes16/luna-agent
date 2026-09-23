import unittest

from app.execution_intent import (
    APPROVAL_REQUIRED,
    AUTO,
    BLOCKED,
    L0_OBSERVE,
    L1_PROBE,
    L2_MUTATE,
    L3_HIGH_IMPACT,
    ON_DEMAND,
    build_execution_intent,
)


class ExecutionIntentTests(unittest.TestCase):
    def test_local_read_only_observation_is_l0_auto(self) -> None:
        intent = build_execution_intent("cat /etc/hosts")
        self.assertEqual(intent.authority_level, L0_OBSERVE)
        self.assertEqual(intent.authority, AUTO)
        self.assertEqual(intent.capability, "local_observation")
        self.assertFalse(intent.mutates_state)

    def test_bound_network_probe_is_l1_on_demand(self) -> None:
        intent = build_execution_intent(
            "nmap -sV 10.10.10.5",
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertEqual(intent.authority_level, L1_PROBE)
        self.assertEqual(intent.authority, ON_DEMAND)
        self.assertEqual(intent.target, "10.10.10.5")
        self.assertTrue(intent.verification_required)

    def test_privileged_probe_stays_l1_but_requires_approval(self) -> None:
        intent = build_execution_intent(
            "sudo nmap -sS 10.10.10.5",
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertEqual(intent.authority_level, L1_PROBE)
        self.assertEqual(intent.authority, APPROVAL_REQUIRED)
        self.assertTrue(intent.privilege_required)

    def test_state_change_is_l2(self) -> None:
        intent = build_execution_intent(
            "sudo systemctl restart tor",
            context="Kali VM laboratório autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
        )
        self.assertEqual(intent.authority_level, L2_MUTATE)
        self.assertEqual(intent.authority, APPROVAL_REQUIRED)
        self.assertTrue(intent.mutates_state)
        self.assertTrue(intent.rollback_required)

    def test_destructive_bounded_action_is_l3(self) -> None:
        intent = build_execution_intent(
            "rm -rf /tmp/luna-proof",
            context="Kali VM laboratório autorizado; alvo destrutivo exato /tmp/luna-proof",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
        )
        self.assertEqual(intent.authority_level, L3_HIGH_IMPACT)
        self.assertEqual(intent.authority, APPROVAL_REQUIRED)
        self.assertTrue(intent.destructive)

    def test_system_tree_recursive_delete_is_blocked(self) -> None:
        intent = build_execution_intent(
            "sudo rm -rf /etc",
            context="Kali VM laboratório autorizado; /etc",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertEqual(intent.authority_level, L3_HIGH_IMPACT)
        self.assertEqual(intent.authority, BLOCKED)

    def test_curl_post_is_classified_by_semantics_not_tool_name(self) -> None:
        intent = build_execution_intent(
            "curl -X POST -d 'enabled=true' https://target.test/api/config",
            context="CTF autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertEqual(intent.authority_level, L2_MUTATE)
        self.assertEqual(intent.authority, APPROVAL_REQUIRED)
        self.assertTrue(intent.mutates_state)
        self.assertIn("semantic_remote_mutation", intent.reasons)

    def test_nmap_exploit_script_is_high_impact_semantic(self) -> None:
        intent = build_execution_intent(
            "nmap --script exploit 10.10.10.5",
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertEqual(intent.authority_level, L3_HIGH_IMPACT)
        self.assertEqual(intent.authority, APPROVAL_REQUIRED)
        self.assertIn("high_impact_semantic", intent.reasons)

    def test_readiness_improves_when_scope_and_operator_are_bound(self) -> None:
        pending = build_execution_intent("nmap -sV 10.10.10.5")
        bound = build_execution_intent(
            "nmap -sV 10.10.10.5",
            context="CTF autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertGreater(bound.readiness_index, pending.readiness_index)

    def test_risk_increases_with_mutation_and_high_impact(self) -> None:
        observe = build_execution_intent("cat /etc/hosts")
        probe = build_execution_intent("nmap -sV 10.10.10.5")
        mutate = build_execution_intent(
            "sudo systemctl restart tor",
            context="Kali VM laboratório autorizado",
        )
        self.assertLess(observe.risk_index, probe.risk_index)
        self.assertLess(probe.risk_index, mutate.risk_index)


if __name__ == "__main__":
    unittest.main()
