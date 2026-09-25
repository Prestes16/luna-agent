# Luna Cyber Agent Skills

## Purpose

Agent Skills are Luna's procedural knowledge layer. They explain **how to perform a class of work** without changing who is allowed to execute host actions.

The runtime now separates three decisions:

```text
Current user request
  -> SkillRouter
       discovers/ranks up to 6 relevant candidates
  -> SkillAdmissionPolicy
       decides which candidates are actually worth prompt context
       hard limits: max 2 active skills / context budget 5
  -> SkillLoader
       injects only bounded excerpts from admitted SKILL.md files
  -> AgentHarness / output validators
  -> response

Real execution remains a separate path:
operator request -> ExecutionIntent -> host safety -> supervised executor
```

## Non-negotiable invariants

1. `INSTRUCTION_ONLY_BUILD = True` remains unchanged.
2. `HarnessPolicy.max_tool_calls = 0` remains unchanged.
3. `allowed-tools` is descriptive skill metadata, never execution authority.
4. Skill loading never executes scripts.
5. Skills cannot alter scope, approval, `ExecutionIntent`, host safety or executor policy.
6. Current-turn intent is required for automatic activation. Stale ScenarioContext alone cannot activate a skill.
7. Manual `/skill <name>` and `skill:<name>` selection has routing precedence.
8. Automatic admission is bounded by relevance, exclusive groups and context cost.
9. At most two skills enter one model turn by default.
10. Every rejected candidate is observable through admission telemetry.

## Why routing and admission are separate

A large installed catalog is useful only if the model does not receive every procedure on every turn.

`SkillRouter` answers:

> Which skills look relevant to the current request?

`SkillAdmissionPolicy` answers:

> Which of those candidates are sufficiently relevant, compatible and worth spending context on now?

A candidate may therefore be correctly detected and still be rejected from prompt context.

Examples:

- a high-context skill with weak intent -> rejected as `insufficient_relevance`;
- a second skill from the same exclusive capability group -> rejected;
- a third otherwise-useful skill -> rejected by `max_active_skills_reached`;
- a skill that would exceed the context budget -> rejected;
- an explicit operator selection -> may override the soft context budget, but never the hard two-skill limit.

## Admission metadata

Luna-specific metadata fields include:

- `luna-auto-activate`
- `luna-priority`
- `luna-triggers`
- `luna-exclude-triggers`
- `luna-requires-current-any`
- `luna-requires-any`
- `luna-context-triggers`
- `luna-admission`: `on-demand | evidence | explicit-only`
- `luna-context-cost`: `low | medium | high`
- `luna-auto-min-score`
- `luna-min-evidence-delta`
- `luna-exclusive-group`
- `luna-domain`
- `luna-purpose`
- `luna-execution`

These are routing/admission controls. They are **not** security permissions.

## Context budget

Default admission policy:

```text
low    = 1 context unit
medium = 2 context units
high   = 3 context units

max active skills = 2
max context units = 5
```

This deliberately allows a focused specialist + one supporting procedure, for example:

```text
solana-vulnerability-scanner (high = 3)
+ audit-context-building       (medium = 2)
= 5
```

but prevents two unrelated high-context procedures from auto-stacking.

## Installed portfolio

### Foundation / context

- `audit-context-building`
- `entry-point-analyzer`
- `security-data-analysis`

### Differential / finding validation

- `differential-review`
- `variant-analysis`
- `fp-check`
- `post-patch-validation`

### Static analysis / configuration / design

- `static-analysis`
- `semgrep-rule-creator`
- `insecure-defaults`
- `sharp-edges`
- `spec-to-code-compliance`
- `supply-chain-risk-auditor`

### Native / crypto

- `rust-review`
- `c-review`
- `constant-time-analysis`
- `constant-time-testing`
- `zeroize-audit`

### Fuzzing / test strength

- `property-based-testing`
- `harness-writing`
- `coverage-analysis`
- `fuzzing-obstacles`
- `mutation-testing`

### Blockchain

- `solana-vulnerability-scanner`
- `token-integration-analyzer`

### Malware / detection engineering

- `yara-rule-authoring`

Total installed procedural skills after this wave: **26**.

## Important specialization rules

### Rust vs Solana

`rust-review` explicitly excludes Solana/Anchor prompts. Solana programs route to `solana-vulnerability-scanner`, which understands account constraints, PDA, signer, ownership, CPI and instruction introspection.

### C/C++ vs Rust

`c-review` and `rust-review` share the `language-security-review` exclusive group. They do not auto-stack on an ambiguous mixed-language request; the higher-ranked current target wins unless the operator explicitly selects otherwise.

### Static timing vs runtime timing

- `constant-time-analysis`: source/compiler/assembly mechanism review.
- `constant-time-testing`: runtime/statistical measurement such as dudect/Timecop.

They are complementary but independently triggered.

### Variant hunting

`variant-analysis` requires a known finding/root cause in the current/scenario context. It cannot activate merely because prior conversation text contains the word "vulnerability".

### Audit context

Generic words like `audit` or `auditoria` are intentionally **not** sufficient anymore. `audit-context-building` activates for explicit context-building intent such as unfamiliar codebase, threat model, architecture review or surface mapping.

This prevents it from becoming an unnecessary companion on every specialist review.

## Configuration

`LUNA_SKILLS_ENABLED=true|false` controls the subsystem.

If `LUNA_ENABLED_SKILLS` is unset, Luna discovers every valid installed skill under:

```text
luna-desktop/backend/skills/<name>/SKILL.md
```

If set, it becomes an explicit allowlist:

```text
LUNA_ENABLED_SKILLS=audit-context-building,solana-vulnerability-scanner
```

This is useful for isolated regression testing.

## Telemetry

Each turn exposes:

- `skill_candidates`
- `selected_skills`
- `skill_route_reasons`
- `skill_admission_rejections`

The distinction is intentional:

```text
candidate != admitted
admitted != authority
authority remains in AgentHarness / ExecutionIntent / supervised executor
```

## Evidence contract

Skills must not turn:

- scanner candidate -> finding without mechanism validation;
- missing check -> vulnerability without tracing;
- correlation -> causality;
- zero findings -> safety;
- failed exploit -> fixed patch;
- modifier/function name -> enforcement;
- approximate arithmetic -> exact quantitative claim;
- coverage percentage -> proof of security;
- upstream/canonical patch -> proof of correctness.

Existing Luna validators, including V17/V18, remain authoritative.

## Third-party provenance

Trail of Bits-derived/adapted skills are marked `CC-BY-SA-4.0` and retain upstream source metadata.

See:

```text
luna-desktop/backend/skills/THIRD_PARTY_NOTICES.md
```

`security-data-analysis` is original Shield-Corp/Luna Cyber work.

## Regression gate

After pulling this wave:

```powershell
cd luna-desktop\backend
python -m unittest tests.test_skill_system -v
python -m unittest discover -s tests -p "test_*.py"
```

Then use live Luna prompts to verify positive routing, negative routing, skill composition and telemetry before changing any execution policy.
