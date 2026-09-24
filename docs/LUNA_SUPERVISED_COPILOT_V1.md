# Luna Cyber — Supervised Copilot Execution V1

This document freezes the operator-control model for the implemented supervised executor.
The executor exists as a separate gate and is disabled by default; the LLM tool loop remains hard-locked.

## Role

Luna is a **copilot**, not an autonomous auditor. The operator owns the car:
target, objective, scope changes and authority escalation remain operator decisions.
Luna may execute selected capabilities on demand through the separate supervised executor,
but execution authority is granted per capability and per intent, never by one global switch.

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
SUPERVISED EXECUTOR (default disabled)
          |
          v
RAW RESULT -> EVIDENCE PLANE -> LUNA RECALCULATES
```

The model-facing tool loop remains instruction-only (`INSTRUCTION_ONLY_BUILD=True`).
Separately, `SupervisedExecutor` recomputes the execution intent before every process start.
Its default policy is disabled; L0/L1 can be enabled independently, while L2/L3 stay
disabled unless the operator deliberately enables those levels. Approval-required
actions must carry an exact, expiring grant bound to command SHA-256, authority level
and target. Shell control operators are rejected and execution uses argv, never
`shell=True`.

## Execution backend and operator UI

Approved execution is routed independently from the model. The default backend is the
backend host process runner. For the isolated Kali VM, execution can be bound to OpenSSH
without enabling the LLM tool loop:

```text
LUNA_EXEC_BACKEND=kali-ssh
LUNA_KALI_SSH_HOST=<Kali address>
LUNA_KALI_SSH_USER=<Kali user>
LUNA_KALI_SSH_PORT=22
LUNA_KALI_SSH_IDENTITY=<local private-key path>
LUNA_KALI_SSH_KNOWN_HOSTS=<local known_hosts path>
LUNA_KALI_SSH_HOST_KEY_POLICY=strict
LUNA_KALI_SSH_CONNECT_TIMEOUT=10
```

If `kali-ssh` is requested but its host/user/port/timeout/policy configuration is invalid,
Luna fails closed and does **not** fall back to executing the command on Windows. Numeric
SSH settings are parsed strictly: malformed ports/timeouts are rejected rather than silently
clamped or replaced with defaults. `BatchMode=yes` keeps the execution path non-interactive;
authentication must therefore be available through the configured identity or the local
OpenSSH agent/default key mechanism. Public diagnostics expose only whether identity/known-host
files are configured, never their local paths.

The desktop chat receives the exact validated execution actions from response metadata.
The operator sees the exact command, L0-L3 class, authority, target and risk index. A button
click is the current-turn on-demand request. Approval-required actions perform a separate,
short-lived approval exchange; rollback-required actions require the operator to confirm
that the rollback/cleanup plan has been reviewed before process start. Destructive or
persistent actions require an additional explicit confirmation.

The executor independently recomputes the intent immediately before execution, so UI
metadata is informative but is never the authority.

## L0–L3 authority semantics

### L0 OBSERVE

Examples: local state inspection, file/type/hash/string/log/process/network-state
reads without intended mutation.

Default authority: `AUTO`.

Automatic L0 execution is still bounded to configured host/workspace scope and to a
known read-only tool semantic. Unknown tools fail closed instead of being guessed safe.

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
independent or stationary in the real target. The formulas have one deterministic
implementation authority in `quantitative_reasoning.py`; exploit-proof and evidence-bundle
layers only wrap that implementation so report values cannot drift because two modules
rounded or implemented the same formula differently.

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

## Immutable evidence vault

Report artifacts are also persisted in a local content-addressed vault. Exact bytes are
stored under SHA-256, while SQLite keeps project-scoped metadata:

```text
project id
kind / media type / source
original name / description
SHA-256
exact byte length
observed timestamp
sensitivity
```

Repeated identical bytes share the same immutable blob while preserving separate
observation records. Reads re-check byte length and SHA-256; tampering therefore
fails integrity verification. Deleting a project removes its references and garbage
collects blobs only when no remaining project references the digest.

Project chat screenshots are persisted into this vault before semantic interpretation,
so a later report can attach the original image rather than a reconstructed rendering.

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

The current structured Kali registry is now also the conservative baseline authority for
execution class. Guidance and execution therefore do not maintain independent notions of
what a known tool is. Command-specific semantics can only escalate that baseline; they
cannot downgrade a tool below its registry class. Examples: network/web/DNS tools default
to L1, authentication testing defaults to L3, VPN/proxy mutation defaults to L2, and
offline/static-analysis tools default to L0.

The next knowledge expansion will ingest the operator's installed environment:

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
