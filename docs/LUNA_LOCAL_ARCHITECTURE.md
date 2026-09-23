# Luna Cyber — Local-First Architecture

This document is the durable architectural reference for the personal Luna Cyber agent.

## Core equation

**Luna Cyber = LLM + deterministic/supervised harness**

The agent is optimized for one local operator. It is not designed as a multi-tenant SaaS platform.

## Operating philosophy

The primary offensive reasoning chain is:

```text
BUILD
  -> MODEL
  -> MATH / PHYSICS
  -> INVARIANTS
  -> ATTACK SURFACE
  -> PRIMITIVE
  -> PRECONDITIONS
  -> HYPOTHESIS
  -> MINIMUM DISCRIMINATING TEST
  -> EVIDENCE
  -> EXPLOITABILITY
  -> IMPACT
  -> FINDING
```

The model must understand how a target is constructed before promoting a break/exploit hypothesis.

## Plane 1 — Execution / Reasoning

```text
CURRENT INPUT + EVIDENCE
  -> EPHEMERAL / SCENARIO CONTEXT
  -> ROUTER (FAST / ANALYZE / DEEP)
  -> BUILD-TO-BREAK MODEL
  -> DETERMINISTIC HARNESS
  -> MEMORY RETRIEVAL
  -> EFFECTIVE CONTEXT
  -> LLM
  -> RETRY / REPLAN
  -> OUTPUT GUARDRAILS (V1 ... V18+)
  -> ATTESTATION / RESPONSE
  -> OPERATOR
```

Critical arithmetic is computed by deterministic helpers before generation whenever possible.
The LLM interprets the result; it is not the authority for exact integer bounds, overflow thresholds,
rounding remainders, probability formulas or physical measurement claims when deterministic checks exist.

## Plane 2 — Knowledge / Memory

Memory classes:

- **Ephemeral:** current evidence and ScenarioContext.
- **Procedural:** local Markdown modules/playbooks/methods.
- **Semantic:** durable facts/evidence with explicit provenance.
- **Episodic:** events, decisions and results with recency.
- **Hypotheses:** stored separately and never promoted to facts without validation.

Durable local storage uses SQLite/FTS5. Embeddings are optional and, if added later, are retrieval
mechanisms only; they never determine truth.

### Memory promotion rules

```text
REAL OBSERVATION          -> EVIDENCE
OPERATOR DECLARED FACT    -> OPERATOR_FACT
DETERMINISTIC DERIVATION  -> DERIVED_FACT
LLM PROPOSAL              -> HYPOTHESIS
CONFIRMED TEST            -> VALIDATED_FINDING
CONTRADICTING EVIDENCE    -> SUPERSEDED
SECRET                    -> REDACT / NEVER STORE RAW
```

Each durable memory record carries at least:

- project id;
- kind;
- content;
- provenance;
- source;
- source hash;
- observed timestamp;
- evidence level;
- optional validity/TTL;
- optional superseded-record link;
- redaction metadata.

### Cache policy

Semantic response cache remains **OFF**.

Allowed cache classes are deterministic prompt/context fragments, procedural retrieval,
immutable/static lookups and future tool results only when state/version identity makes caching safe.

Cache identity should use content hashes, module versions, Git/file hashes, query + immutable dataset
version, or tool + args + explicit state/version. New evidence or state mutation invalidates related data.

## Plane 3 — Quality / Control

Local observability should keep:

- turn/session id;
- route/model;
- first-token and total latency;
- retries/replans;
- guardrail outcomes;
- memory provenance;
- checkpoint lineage;
- response attestation/quality metrics.

No external telemetry platform is required.

The local release gate is:

```text
syntax
  -> unit tests
  -> golden scenarios
  -> offensive regression
  -> memory contamination tests
  -> exact-math tests
  -> host/tool safety
  -> E2E Ollama
  -> PASS / BLOCK
```

## Explicit non-goals for the current local build

Do not add these without a measured need:

- LangGraph;
- LangSmith;
- Langfuse;
- Datadog;
- remote vector databases;
- generic/semantic response caching;
- distributed worker infrastructure;
- multi-agent orchestration;
- Kubernetes;
- production canary/rollout machinery;
- cloud-cost accounting.

## Future tool execution plane

The current build remains instruction-only until a separate supervised execution gate is introduced.

Future policy:

```text
READ-ONLY / LOCAL DISCOVERY
  -> automatic when explicitly inside the configured scope

BOUNDED ACTIVE TEST
  -> policy-dependent and scope-bound

MUTATION / PRIVESC / PERSISTENCE / DESTRUCTIVE ACTION
  -> explicit operator approval + verification + rollback model
```

Tool execution must not weaken the evidence, provenance, math, host-safety or human-approval invariants.
