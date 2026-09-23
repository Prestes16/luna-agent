import unittest

from app.agent_harness import AgentHarness, ExactTTLCache, HarnessPolicy


class AgentHarnessTests(unittest.TestCase):
    def test_policy_is_bounded_and_instruction_only(self) -> None:
        harness = AgentHarness()
        policy = harness.public_policy()
        self.assertEqual(policy["max_model_attempts"], 2)
        self.assertEqual(policy["max_tool_calls"], 0)
        self.assertTrue(policy["human_approval_for_sensitive_actions"])
        self.assertFalse(policy["semantic_response_cache_enabled"])
        self.assertTrue(policy["write_actions_require_idempotency_key"])
        self.assertEqual(policy["retry_strategy"], "exponential_backoff+jitter")

    def test_replan_is_bounded_to_one_extra_attempt(self) -> None:
        harness = AgentHarness(HarnessPolicy(max_model_attempts=2))
        trace = harness.begin_turn(session_id="x", route="ANALYZE")
        harness.record_model_attempt(trace)
        self.assertTrue(harness.should_replan(trace, validation_valid=False))
        harness.record_replan(trace)
        harness.record_model_attempt(trace)
        self.assertFalse(harness.should_replan(trace, validation_valid=False))
        self.assertEqual(trace.model_attempts, 2)
        self.assertEqual(trace.replans, 1)

    def test_memory_plane_tracks_all_four_provenance_classes(self) -> None:
        harness = AgentHarness()
        snapshot = harness.memory_snapshot(
            evidence_delta="new fact",
            scenario_context="target",
            active_modules={"mentor": "procedural"},
            project_context="durable fact",
            context_summary="older episode",
            history_count=2,
        )
        self.assertTrue(snapshot.ephemeral_present)
        self.assertEqual(snapshot.procedural_sources, ("mentor",))
        self.assertTrue(snapshot.semantic_present)
        self.assertTrue(snapshot.episodic_present)
        self.assertIn("ephemeral:scenario+current-evidence", snapshot.provenance)
        self.assertIn("procedural:mentor", snapshot.provenance)
        self.assertIn("semantic:project-facts/context", snapshot.provenance)
        self.assertIn("episodic:recent-history/summary", snapshot.provenance)

    def test_exact_retrieval_cache_supports_ttl_namespace_invalidation(self) -> None:
        cache = ExactTTLCache(max_entries=4)
        key = cache.key("procedural:mentor", "same context", "v1")
        self.assertIsNone(cache.get(key))
        cache.put(key, "excerpt", ttl_seconds=60)
        self.assertEqual(cache.get(key), "excerpt")
        self.assertEqual(cache.invalidate_namespace("procedural:mentor"), 1)
        self.assertIsNone(cache.get(key))

    def test_output_guardrail_trace_records_termination(self) -> None:
        harness = AgentHarness()
        trace = harness.begin_turn(session_id="x", route="FAST")
        harness.record_output_guardrails(
            trace, validator_passed=False, validation_reasons=("bad",)
        )
        self.assertEqual(trace.termination_reason, "guardrail_rejection")
        self.assertIn("exact_arithmetic", trace.guardrails_out)


if __name__ == "__main__":
    unittest.main()
