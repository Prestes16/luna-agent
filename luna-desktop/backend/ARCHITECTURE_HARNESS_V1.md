# Luna Agent Harness V1

## Source-derived architecture

The reference diagrams organize the agent as `LLM + Harness`: a bounded agent loop,
input/output guardrails, human approval for sensitive actions, retries, tool/action
discipline, cache, durable memory, traces/evals and CI gates.

This implementation adapts that architecture to Luna's **local-first supervised-copilot**
contract. The model-facing tool loop remains instruction-only, while a separate
operator-gated executor can be enabled independently. It does not add autonomous auditing.

## Runtime / Harness

- `AgentHarness` owns the bounded model-attempt policy.
- Current limit: one initial generation plus at most one replan (`max_model_attempts=2`).
- Model tool-call budget remains zero.
- A separate `SupervisedExecutor` is disabled by default and is not callable by the LLM tool loop.
- Operator-gated L0/L1 execution and exact approval-bound L2/L3 execution are separate policies.
- Guardrail provenance is emitted in turn telemetry.
- Sensitive state-changing actions remain human-in-the-loop through the existing
  command lifecycle / host-safety policies.
- Future write actions, if ever enabled by a deliberate redesign, must use
  idempotency keys before retrying side effects.
- Retry policy contract is exponential backoff + jitter for model transport.
  Side-effecting executor retries are not implicit; a state-changing action must be
  re-evaluated against its intent/approval lifecycle.

## Cache

- Static runtime rules now precede dynamic runtime context, preserving a stable
  prompt prefix for backends that can exploit prefix caching.
- Procedural retrieval excerpts use a process-local exact TTL cache (300 s default).
- Cache keys include the procedural source content and current retrieval context.
- Namespace invalidation is supported.
- **Model-answer semantic cache is disabled** because security state can become stale
  and a similarity hit must not silently replace current evidence.
- Dynamic project state is not cached in the harness in V1.

## Memory planes

1. **Ephemeral** — current evidence delta + `ScenarioContext`.
2. **Procedural** — local mentor/module instructions (`module_mentor_kali_devtools.md`).
3. **Semantic durable** — typed facts/evidence from local SQLite/FTS5.
4. **Episodic** — typed recent/relevant project messages and compressed conversation history.
5. **Binary evidence** — immutable content-addressed report artifacts (screenshots/logs/PCAP/etc.).

`ProjectStore.retrieval_context()` uses the typed local memory plane. FTS5 provides
deterministic lexical retrieval with a recency fallback; `vector_backend=not_enabled`
remains explicit. Raw binary evidence is stored separately so retrieval text cannot mutate
or replace exact report artifacts.

## Guardrails

Input-side runtime invariants include current-turn factual precedence, exact
authorized evidence retention, telemetry-only secret redaction where appropriate,
and the instruction-only tool lock. Output-side validation continues
through the existing validator chain (construction grounding, quantitative integrity,
exact arithmetic, command policy and host safety) before operator-visible output.

## LLMOps / evals

- `turn_metadata` and `response_meta` carry route, attempts, validation, cache and
  harness provenance.
- Backend unittest suites are the current eval gate.
- External tracing services, embedding stores, SQL episodic storage and GitHub CI
  are intentionally separate follow-on integrations; V1 does not claim they exist.

## Migration rule

New capabilities should attach to the harness as explicit planes/policies rather
than growing another implicit loop inside the LLM. Deterministic facts belong in
code-side solvers; the LLM interprets, correlates and explains them.
