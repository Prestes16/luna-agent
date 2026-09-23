# Luna Cyber — Supervised Copilot Execution V1

This document freezes the operator-control model before real tool execution is enabled.

## Role

Luna is a **copilot**, not an autonomous auditor. The operator owns the car:
target, objective, scope changes and authority escalation remain operator decisions.
Luna may later execute selected capabilities on demand, but execution authority is
granted per capability and per intent, never by one global switch.

```text
OPERATOR OBJECTIVE / EVIDENCE
          |
          v
LUNA BUILD -> MODEL -> MATH/PHYSICS -> INVARIANTS
          |
          v
HYPOTHESIS / TEST / PoC
          |
          v
EXECUTION INTENT
  tool
  exact command/artifact
  target binding
  capability
  expected effect
  evidence expected
  mutation/privilege
  rollback/verification
          |
          v
CAPABILITY AUTHORITY
  L0 OBSERVE -> AUTO
  L1 PROBE   -> ON_DEMAND
  L2 MUTATE  -> APPROVAL_REQUIRED
  L3 HIGH IMPACT -> APPROVAL_REQUIRED or BLOCKED
          |
          v
FUTURE EXECUTOR
          |
          v
RAW RESULT -> EVIDENCE PLANE -> LUNA RECALCULATES
```

The current build remains instruction-only. The V1 intent model is implemented
before an executor so policy can be regression-tested independently.

## L0–L3 authority semantics

### L0 OBSERVE

Examples: local state inspection, file/type/hash/string/log/process/network-state
reads without intended mutation.

Default authority: `AUTO`.

Future automatic execution is still bounded to configured workspace/host scope.

### L1 PROBE

Examples: nmap, curl, HTTP probes, DNS queries, TLS/service enumeration and other
active target observations.

Default authority: `ON_DEMAND`.

The exact target must be bound to operator scope. Privileged probe modes remain L1
but can require explicit approval because authority and technical capability are
separate dimensions.

### L2 MUTATE

Examples: service restart, route/configuration change, package installation or
other bounded state mutation.

Default authority: `APPROVAL_REQUIRED`.

Required lifecycle:

```text
PRESTATE -> ONE CHANGE -> VERIFY -> CONTINUE or ROLLBACK
```

### L3 HIGH IMPACT

Examples: destructive operations, persistence, high-impact privilege transition,
exploit execution with meaningful state effects or other operations that can create
material host/target impact.

Default authority: `APPROVAL_REQUIRED`; existing host-safety invariants may make
a specific intent `BLOCKED`.

L3 requires an explicit bounded proof objective, target/environment binding and
report-grade evidence/cleanup expectations.

## Deterministic risk math

Execution risk is not delegated to the LLM.

The engineering risk index is bounded in `[0,1]` and uses a nonlinear compounding model:

```text
R = 1 - (1 - R_host) * product_i(1 - w_i * x_i)
```

where each `x_i` is a factual dimension such as active probe, privilege,
mutation, persistence, destructiveness, irreversibility or high-impact semantics.

This is an **engineering index**, not a probability of compromise. The multiplicative
form is intentional: one severe dimension cannot be averaged away by several benign ones.

Readiness uses a weighted geometric score with a critical floor over scope,
operator request and target binding. Missing a critical prerequisite therefore
dominates instead of being hidden by strong secondary dimensions.

## Exploit / PoC proof contract

Luna must be capable of constructing a minimal exploit/PoC when a finding needs
technical validation, but proof generation is evidence-bound.

```text
OBSERVED PRIMITIVE
  -> PRECONDITIONS
  -> EXACT TARGET/VERSION/STATE
  -> MINIMAL REPRODUCER
  -> SUCCESS PREDICATE
  -> EXECUTION INTENT
  -> RAW EVIDENCE
  -> POSTSTATE / CLEANUP
  -> VALIDATED FINDING
```

A crash, response change or partial access must not be promoted to a larger impact
without evidence for the larger claim.

Exploit-proof readiness uses a weighted geometric model over:

- primitive evidence;
- known preconditions;
- target binding;
- explicit success predicate;
- evidence-capture plan;
- cleanup/rollback plan.

Primitive evidence, target binding and success predicate form a critical floor.

For probabilistic/reliability claims, Luna must report observed successes/trials and
a calibrated interval rather than calling a one-off success "reliable". The V1
deterministic helpers include a Wilson score interval for binary repeated trials and
the exact one-sided zero-failure binomial upper bound:

```text
p_upper = 1 - alpha^(1/n)
```

These are report-calibration tools, not assumptions that exploit trials are
independent or stationary in the real target.

### Report evidence

Depending on the domain, Luna should preserve:

- exact command or PoC artifact hash;
- stdout/stderr;
- HTTP raw request/response;
- debugger register/stack/crash state;
- packet/protocol transcript or PCAP reference;
- Web3 transaction signature, program/cluster identity and account pre/post-state;
- timestamps;
- screenshots when visual state materially supports the finding;
- cleanup/rollback result.

## Evidence bundle and reproducibility math

Every proof that may become a report finding should be capable of producing a deterministic
evidence bundle. Raw artifacts are preserved byte-for-byte and individually SHA-256 hashed.
The bundle binds the exact target, explicit success predicate and (when present) the exact
command/PoC invocation hash.

Supported evidence classes include logs, stdout/stderr, raw HTTP exchanges, debugger traces,
PCAP/protocol transcripts, Web3 transaction artifacts and screenshots.

When a proof is repeated, Luna must record the exact numerator/denominator instead of saying
"reliable" from impression alone:

```text
success_rate = successes / trials
```

For binomial repeatability, the deterministic math layer computes a Wilson score interval:

```text
center = (p + z^2/(2n)) / (1 + z^2/n)

margin = z * sqrt((p(1-p) + z^2/(4n))/n) / (1 + z^2/n)
```

This interval describes uncertainty in the tested repetitions; it is not a probability that an
exploit works on untested hosts, versions or environments. Exact artifact hashes and tested
conditions remain the evidentiary authority.

## Visual evidence

Screenshots/images are first-class evidence.

The engine already has multimodal transport. V1 adds deterministic image manifests:

```text
image index
mime type
exact byte length
SHA-256
```

Visual reasoning contract:

```text
PIXELS
  -> OBSERVED visible facts
  -> exact visible strings/values/status
  -> INFERENCE
  -> HYPOTHESIS
```

Obscured or cropped text must never be invented. If visual resolution is
insufficient, Luna must identify the unresolved field instead of guessing.

Actual semantic image understanding requires a multimodal local model. Runtime now
queries the exact Ollama model with `/api/show` and requires the reported
`vision` capability before claiming that pixels were semantically read. If the
selected model is text-only, the image bytes/manifest remain preserved as evidence
but visual interpretation is blocked.

An explicit local multimodal model can be selected with:

```text
LUNA_VISION_MODEL=<installed Ollama vision model>
```

This is deliberately fail-closed: Luna must never pretend it inspected a screenshot
when the model cannot actually consume visual content.

## Kali knowledge plane

Kali knowledge will later be ingested from the operator's installed environment:

```text
man / --help / tool version
  -> deterministic parser
  -> source hash + version
  -> SQLite/FTS5
  -> capability/flag/side-effect metadata
  -> top-k retrieval
  -> Luna effective context
```

Per-tool metadata should include:

- capabilities;
- required privileges;
- side effects;
- network behavior;
- protocol coverage;
- dangerous flags;
- output/evidence format;
- version;
- source SHA-256;
- examples;
- execution authority class.

This avoids stuffing all Kali documentation into the model context and keeps
guidance aligned with the exact installed tool version.


## Report-grade evidence pack contract

A validated finding should be reproducible from an evidence pack rather than from
the narrative alone. The future executor/report pipeline will bind:

```text
finding id
target / environment
preconditions
exact command or PoC artifact
artifact SHA-256
raw stdout/stderr or protocol transcript
visual evidence SHA-256 when applicable
success predicate
quantitative measurements / sample counts
pre-state / post-state
cleanup / rollback result
timestamps
```

The evidence pack does not automatically promote a hypothesis to a finding. Promotion
still requires the success predicate to be observed and the causal mechanism to satisfy
the BUILD -> MODEL -> MATH/PHYSICS -> INVARIANT -> TEST -> EVIDENCE chain.
