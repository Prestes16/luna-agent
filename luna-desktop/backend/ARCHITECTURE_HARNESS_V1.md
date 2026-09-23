# Luna Agent Harness V1

## Source-derived architecture

The reference diagrams organize the agent as `LLM + Harness`: a bounded agent loop,
input/output guardrails, human approval for sensitive actions, retries, tool/action
discipline, cache, durable memory, traces/evals and CI gates.

This implementation adapts that architecture to Luna's current **instruction-only,
local-first** contract. It does not add autonomous host execution.

## Runtime / Harness

- `AgentHarness` owns the bounded model-attempt policy.
- Current limit: one initial generation plus at most one replan (`max_model_attempts=2`).
- Current tool-call budget: zero. The operator executes commands manually.
- Guardrail provenance is emitted in turn telemetry.
- Sensitive state-changing actions remain human-in-the-loop through the existing
  command lifecycle / host-safety policies.
- Future write actions, if ever enabled by a deliberate redesign, must use
  idempotency keys before retrying side effects.
- Retry policy contract is exponential backoff + jitter; it is metadata/policy only
  for tool actions while tool execution remains hard-locked.

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
3. **Semantic durable** — project facts selected for the current query.
4. **Episodic** — recent/relevant project messages and compressed conversation history.

`ProjectStore.retrieval_context()` currently implements semantic/episodic retrieval
with deterministic lexical relevance + recency over the existing atomic JSON store.
It explicitly reports `vector_backend=not_enabled`; V1 does not pretend that JSON
retrieval is a vector database or SQL episodic store.

## Guardrails

Input-side runtime invariants include current-turn factual precedence, secret
redaction and the instruction-only tool lock. Output-side validation continues
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
