# Luna Cyber Skill System

## Objective

Add interoperable Agent Skills as a procedural knowledge layer without replacing or weakening the existing Luna harness.

Architecture invariant:

```text
User -> Luna/Qwen -> deterministic Skill Router -> SKILL.md procedural context
                                      |
                                      v
                           AgentHarness / ExecutionIntent
                                      |
                                      v
                          supervised executor (separate)
```

A skill teaches **how to perform a task**. It does not grant authority to perform host actions.

## Non-negotiable invariants

1. `INSTRUCTION_ONLY_BUILD` remains enabled.
2. `HarnessPolicy.max_tool_calls` remains `0`.
3. `allowed-tools` from `SKILL.md` is parsed as descriptive metadata only.
4. Skill loading is read-only and path-contained.
5. No skill script is executed by the skill loader.
6. A skill cannot alter `ExecutionIntent`, host-safety policy, scope, approval or supervised-executor policy.
7. Only enabled skills may be routed into runtime context.
8. Routing is deterministic and observable in turn telemetry.
9. Skill content enters the existing procedural memory class and uses the exact TTL retrieval cache.
10. External skills require provenance/license review before inclusion.

## Runtime components

- `app/skill_loader.py`: validates and loads the Agent Skills-compatible safe subset.
- `app/skill_router.py`: deterministic activation using Luna metadata/triggers.
- `skills/<name>/SKILL.md`: procedural skill definition.
- `tests/test_skill_system.py`: activation, parsing, path-safety and authority-regression tests.

## Luna metadata

Agent Skills permits arbitrary string metadata. Luna uses:

- `luna-domain`
- `luna-purpose`
- `luna-risk`
- `luna-auto-activate`
- `luna-priority`
- `luna-triggers`
- `luna-exclude-triggers`
- `luna-host-write`
- `luna-network`
- `luna-execution`
- `luna-evidence`

These fields are descriptive/routing metadata. They are not a replacement for runtime policy enforcement.

## Skill #1 — audit-context-building

Purpose: reconstruct an unfamiliar target before vulnerability hunting.

Activation examples:
- start an audit of an unfamiliar codebase;
- build a threat model;
- map architecture/trust boundaries;
- understand code before hunting.

Non-goals:
- no vulnerability verdict;
- no severity;
- no PoC;
- no payload choice;
- no execution authority.

Handoff: assumptions without confirmed enforcement, open questions and evidence-indexed context feed later hunting/validation skills.

Origin: adapted from Trail of Bits `audit-context-building`, kept under CC BY-SA 4.0 in its own skill directory.
