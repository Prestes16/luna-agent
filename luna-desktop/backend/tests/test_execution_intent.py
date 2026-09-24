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
    operator_requested_execution,
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

    def test_explicit_local_poc_artifact_is_l3_not_unknown_block(self) -> None:
        intent = build_execution_intent(
            "./poc --check",
            context="Kali VM laboratório autorizado; validar achado com PoC reproduzível",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            verification_ready=True,
        )
        self.assertEqual(intent.authority_level, L3_HIGH_IMPACT)
        self.assertEqual(intent.authority, APPROVAL_REQUIRED)
        self.assertIn("explicit_poc_artifact_execution", intent.reasons)
        self.assertNotIn("unknown_tool_semantics_fail_closed", intent.reasons)

    def test_arbitrary_unknown_local_binary_without_poc_context_stays_blocked(self) -> None:
        intent = build_execution_intent(
            "./mystery",
            context="Kali VM laboratório autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertEqual(intent.authority, BLOCKED)
        self.assertIn("unknown_tool_semantics_fail_closed", intent.reasons)

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

    def test_operator_execution_request_detection_is_current_turn_explicit(self) -> None:
        self.assertTrue(operator_requested_execution("Luna, rode nmap -sV no alvo autorizado."))
        self.assertTrue(operator_requested_execution("vamos executar esse teste"))
        self.assertTrue(operator_requested_execution("valide este achado no alvo autorizado"))
        self.assertTrue(operator_requested_execution("comprovar a vulnerabilidade com PoC"))
        self.assertFalse(operator_requested_execution("Explique como o nmap funciona."))

    def test_operator_requested_probe_without_scope_is_blocked(self) -> None:
        intent = build_execution_intent(
            "nmap -sV 10.10.10.5",
            operator_requested_execution=True,
            scope_confirmed=False,
        )
        self.assertEqual(intent.authority, BLOCKED)
        self.assertIn("scope_not_confirmed", intent.reasons)

    def test_operator_requested_target_mismatch_is_blocked(self) -> None:
        intent = build_execution_intent(
            "nmap -sV 10.10.10.6",
            context="CTF autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        self.assertEqual(intent.authority, BLOCKED)
        self.assertIn("target_scope_mismatch", intent.reasons)

    def test_unknown_tool_semantics_fail_closed(self) -> None:
        intent = build_execution_intent(
            "customtool --do-something",
            context="Kali VM laboratório autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
        )
        self.assertEqual(intent.authority, BLOCKED)
        self.assertEqual(intent.authority_level, L3_HIGH_IMPACT)
        self.assertIn("unknown_tool_semantics_fail_closed", intent.reasons)

    def test_generic_interpreter_execution_is_high_impact(self) -> None:
        intent = build_execution_intent(
            "python3 -c 'print(1)'",
            context="Kali VM laboratório autorizado",
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


    def test_kali_registry_makes_common_tools_known_without_weakening_authority(self) -> None:
        nuclei = build_execution_intent(
            "nuclei -u https://10.10.10.5",
            context="CTF autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        self.assertEqual(nuclei.authority_level, L1_PROBE)
        self.assertEqual(nuclei.authority, ON_DEMAND)
        self.assertIn("kali_registry_baseline=L1_PROBE", nuclei.reasons)

        hydra = build_execution_intent(
            "hydra -l test -p test ssh://10.10.10.5",
            context="CTF autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        self.assertEqual(hydra.authority_level, L3_HIGH_IMPACT)
        self.assertEqual(hydra.authority, APPROVAL_REQUIRED)

    def test_kali_privacy_mutation_baseline_requires_approval(self) -> None:
        intent = build_execution_intent(
            "openvpn --config lab.ovpn",
            context="ambiente autorizado; perfil VPN fornecido pelo operador",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            verification_ready=True,
        )
        self.assertEqual(intent.authority_level, L2_MUTATE)
        self.assertEqual(intent.authority, APPROVAL_REQUIRED)
        self.assertTrue(intent.mutates_state)
        self.assertTrue(intent.rollback_required)
        self.assertGreater(intent.risk_index, 0.3)


if __name__ == "__main__":
    unittest.main()
