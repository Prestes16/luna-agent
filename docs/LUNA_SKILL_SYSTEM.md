# Luna Cyber Agent Skills

## Purpose

Agent Skills are Luna's procedural knowledge layer. They tell the model **how to perform a class of work** without changing who is allowed to execute host actions.

```text
User
  -> Luna/Qwen
  -> Reasoning Pipeline
  -> SkillRouter (deterministic, max 2)
  -> SkillLoader (read-only SKILL.md)
  -> bounded procedural prompt context
  -> AgentHarness / validators
  -> response

Any real command execution remains a separate path:
operator request -> ExecutionIntent -> host safety -> supervised executor
```

## Invariants

1. `INSTRUCTION_ONLY_BUILD = True` remains unchanged.
2. `HarnessPolicy.max_tool_calls = 0` remains unchanged.
3. `allowed-tools` in a skill is descriptive metadata, never authority.
4. Skill loading never executes scripts.
5. Skills cannot alter scope, approval, `ExecutionIntent`, host safety or executor policy.
6. Only enabled skills enter routing.
7. Current-turn intent dominates routing; stale ScenarioContext cannot activate a skill by itself.
8. Manual `/skill <name>` activation is allowed for an installed/enabled skill.
9. At most two skills enter one turn by default.
10. External/adapted skills carry provenance and license metadata.

## Configuration

`LUNA_SKILLS_ENABLED=true|false` controls the complete subsystem.

If `LUNA_ENABLED_SKILLS` is **unset**, Luna discovers every valid installed skill under
`luna-desktop/backend/skills/<name>/SKILL.md`.

If `LUNA_ENABLED_SKILLS` is set, it becomes an explicit comma-separated allowlist.

Example:

```text
LUNA_SKILLS_ENABLED=true
LUNA_ENABLED_SKILLS=audit-context-building,solana-vulnerability-scanner
```

This lets us isolate one skill during regression tests without editing code.

## Routing model

Priority order:

1. explicit `/skill name` or `skill:name`;
2. current-message triggers;
3. Luna skill priority for resolving generic vs specialist overlap;
4. scenario context only for prerequisite continuity such as “a confirmed finding already exists”.

A skill may declare:
- `luna-triggers`
- `luna-exclude-triggers`
- `luna-requires-current-any`
- `luna-requires-any`
- `luna-context-triggers`
- `luna-priority`
- `luna-auto-activate`

These are routing hints, not security permissions.

## Installed catalog

### Foundation

- `audit-context-building` — reconstruct architecture, trust boundaries, invariants and unenforced assumptions before hunting.
- `entry-point-analyzer` — map externally reachable state-changing blockchain entry points and authority.
- `security-data-analysis` — analyze security logs/findings/telemetry with provenance, grain, time and data-quality gates.

### Code/diff hunting

- `differential-review` — security review of PRs/commits/diffs with history, tests and blast radius.
- `variant-analysis` — search for other manifestations of a confirmed root cause.
- `static-analysis` — choose/orchestrate Semgrep, CodeQL or SARIF processing.
- `semgrep-rule-creator` — create and validate custom Semgrep detections.
- `insecure-defaults` — trace fail-open defaults, fallback secrets, default credentials and permissive settings.

### Verification/testing

- `property-based-testing` — properties, generators, invariants, oracles and shrink interpretation.
- `constant-time-analysis` — static/compiled timing side-channel review for secret-dependent operations.
- `post-patch-validation` — baseline-versus-patch validation of security fixes; replaces the older “fix-review” concept.
- `harness-writing` — build deterministic, meaningful fuzz harnesses.
- `coverage-analysis` — measure what fuzzing actually reaches and identify blockers.

### Blockchain

- `solana-vulnerability-scanner` — six-class Solana/Anchor review: CPI, PDA, ownership, signer, sysvar and instruction introspection.
- `token-integration-analyzer` — non-standard token behavior and integration assumptions.

## Bundle mapping

The upstream Trail of Bits repositories contain plugin bundles. Luna deliberately does not load a bundle as one giant prompt.

`building-secure-contracts` currently contributes:
- `solana-vulnerability-scanner`
- `token-integration-analyzer`

`testing-handbook-skills` currently contributes:
- `harness-writing`
- `coverage-analysis`

`static-analysis` is represented in Luna by an orchestration skill that chooses Semgrep/CodeQL/SARIF based on mechanism. Custom Semgrep rule authoring remains a separate skill.

This decomposition keeps progressive context small and makes activation observable.

## Typical compositions

### Start Solana audit
```text
solana-vulnerability-scanner
+ audit-context-building
```

### Map contract surface
```text
entry-point-analyzer
(+ audit-context-building when the broader architecture is also requested)
```

### Review a security patch
```text
post-patch-validation
+ variant-analysis   (only when a known root cause/variant hunt is explicitly requested)
```

### Create a detector for a confirmed bug family
```text
semgrep-rule-creator
+ variant-analysis
```

### Fuzzing campaign plateau
```text
coverage-analysis
+ harness-writing   (when the current request explicitly involves harness redesign)
```

## Evidence contract

Skills must not turn:
- scanner candidate -> finding without mechanism validation;
- missing check -> vulnerability without tracing;
- correlation -> causality;
- zero findings -> safety;
- failed exploit -> fixed patch;
- modifier/function name -> enforcement;
- approximate arithmetic -> exact quantitative claim.

Existing Luna output validators, including quantitative V17/V18, remain authoritative.

## Third-party provenance

Trail of Bits-derived/adapted skills remain marked `CC-BY-SA-4.0` and point to their upstream source URL in metadata. See `luna-desktop/backend/skills/THIRD_PARTY_NOTICES.md`.

`security-data-analysis` is original Luna Cyber/Shield-Corp work.

## Regression gate

Before expanding the catalog further:

```powershell
cd luna-desktop\backend
python -m unittest tests.test_skill_system -v
python -m unittest discover -s tests -p "test_*.py"
```

Then validate live routing in the Luna app using positive and negative prompts and inspect `selected_skills` in turn telemetry/diagnostics.
