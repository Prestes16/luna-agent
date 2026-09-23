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
SENSITIVE/CREDENTIAL      -> PRESERVE EXACT + CLASSIFY + HASH
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
- sensitivity classification;
- exact-content SHA-256 and byte length.

### Sensitive evidence policy

Luna Cyber is a personal, local, operator-supervised system. Authorized credentials,
cookies, tokens, investigation artifacts and classified evidence are preserved exactly
when they are part of the technical record. The memory plane classifies them as
`credential`, `sensitive` or `classified` and records SHA-256/byte-length integrity
metadata instead of silently redacting them.

Redaction remains appropriate only for explicitly non-evidentiary telemetry/fingerprint
copies or when the operator requests a sanitized export. Evidence used for reproduction,
reporting, correlation or validation retains its exact value.

### Binary/report evidence vault

Textual truth/memory and raw report artifacts are separate concerns. Raw screenshots,
logs, protocol transcripts, debugger output and other attachments are stored byte-for-byte
in a local content-addressed evidence vault with SHA-256, byte length, provenance metadata
and project scope. Project chat images are captured before visual interpretation.

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

## Operator-controlled tool execution plane

The model-facing tool loop remains hard-locked, while a separate supervised executor is
implemented behind an explicit operator gate and is disabled by default. Luna is not an
autonomous auditor: it may execute selected tools on demand inside operator-defined scope,
while the operator retains control over target, objective and escalation of authority.

Execution freedom is granted per capability/policy rather than globally.

Target policy:

```text
READ-ONLY / LOCAL DISCOVERY
  -> automatic when explicitly inside the configured scope

BOUNDED ACTIVE TEST
  -> policy-dependent and scope-bound

MUTATION / PRIVESC / PERSISTENCE / DESTRUCTIVE ACTION
  -> explicit operator approval + verification + rollback model
```

Tool execution must not weaken the evidence, provenance, math, host-safety or human-approval invariants.


## Local dependency profile

The local/Ollama baseline uses `requirements-local.txt`. Cloud SDKs are optional and must
not be import-time requirements for the local agent. In particular, absence of the Anthropic
SDK cannot prevent local reasoning, memory, tests or Ollama operation.


## Supervised copilot execution baseline

The detailed L0-L3 authority model, nonlinear execution-risk math, exploit/PoC
proof contract, visual-evidence integrity contract and future Kali knowledge
ingestion design are frozen in `docs/LUNA_SUPERVISED_COPILOT_V1.md`.

The execution-intent model and supervised executor are implemented and testable.
The executor is disabled by default; L0/L1 and L2/L3 are independently gated, and
the legacy/model tool loop remains disabled. This separation keeps model generation,
authority, execution and evidence capture independently testable.
