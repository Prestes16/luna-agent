import tempfile
import time
import unittest
from pathlib import Path

from app.agent_harness import AgentHarness, ExactTTLCache, HarnessPolicy
from app.harness_checkpoints import CheckpointStore


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

    def test_transport_retry_is_bounded_classified_and_deterministic(self) -> None:
        harness = AgentHarness()
        self.assertTrue(harness.is_retryable_transport_error(TimeoutError("timed out")))
        self.assertTrue(harness.is_retryable_transport_error(RuntimeError("503 unavailable")))
        self.assertFalse(harness.is_retryable_transport_error(RuntimeError("401 unauthorized")))

        delay_a = harness.transport_retry_delay(1, turn_id="turn-a")
        delay_b = harness.transport_retry_delay(1, turn_id="turn-a")
        self.assertEqual(delay_a, delay_b)
        self.assertGreater(delay_a, 0.0)
        self.assertLessEqual(delay_a, harness.policy.retry_max_delay_seconds)

        trace = harness.begin_turn(session_id="x", route="ANALYZE")
        harness.record_transport_retry(
            trace,
            error=TimeoutError("timed out"),
            delay_seconds=delay_a,
        )
        self.assertEqual(trace.transport_retries, 1)
        self.assertEqual(len(trace.transport_retry_delays_ms), 1)
        self.assertEqual(trace.transport_retry_errors, ["TimeoutError"])

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

    def test_checkpoint_store_supports_resume_history_and_time_travel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "checkpoints.sqlite3", ttl_days=30)
            harness = AgentHarness(checkpoint_store=store)
            trace = harness.begin_turn(session_id="thread-a", route="ANALYZE")

            first = harness.checkpoint(
                trace,
                stage="context_ready",
                state={"route": "ANALYZE", "evidence_delta_count": 2},
            )
            second = harness.checkpoint(
                trace,
                stage="validation",
                state={"valid": False, "reasons": ["needs_replan"]},
            )

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(second.parent_checkpoint_id, first.checkpoint_id)
            self.assertEqual(harness.latest_checkpoint("thread-a").stage, "validation")
            history = harness.checkpoint_history("thread-a")
            self.assertEqual([item.stage for item in history], ["validation", "context_ready"])
            replay = store.get(first.checkpoint_id)
            self.assertEqual(replay.state["evidence_delta_count"], 2)

    def test_checkpoint_ttl_prunes_expired_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "checkpoints.sqlite3", ttl_days=1)
            old = time.time() - (3 * 86_400)
            store.save(
                thread_id="thread-old",
                turn_id="turn-old",
                stage="completed",
                state={"ok": True},
                now=old,
            )
            self.assertEqual(store.count(), 1)
            self.assertEqual(store.prune_expired(now=time.time()), 1)
            self.assertEqual(store.count(), 0)

    def test_output_guardrail_trace_records_termination(self) -> None:
        harness = AgentHarness()
        trace = harness.begin_turn(session_id="x", route="FAST")
        harness.record_output_guardrails(
            trace, validator_passed=False, validation_reasons=("bad",)
        )
        self.assertEqual(trace.termination_reason, "guardrail_rejection")
        self.assertIn("exact_arithmetic_v18", trace.guardrails_out)
        self.assertIn("quantitative_claim_integrity_v17", trace.guardrails_out)


if __name__ == "__main__":
    unittest.main()
