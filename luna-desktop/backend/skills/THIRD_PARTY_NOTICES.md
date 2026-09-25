# Luna Cyber — Third-Party Skill Adaptations

The following Luna Cyber skills are adapted from methodologies published in the
Trail of Bits `skills` repository, whose repository license is Creative Commons
Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).

Upstream: https://github.com/trailofbits/skills

Adapted skill directories:
- `audit-context-building`
- `entry-point-analyzer`
- `differential-review`
- `variant-analysis`
- `static-analysis` (Luna orchestration layer adapted from the upstream static-analysis bundle)
- `semgrep-rule-creator`
- `property-based-testing`
- `constant-time-analysis`
- `post-patch-validation`
- `insecure-defaults` (adapted from the upstream plugin/workflow methodology)
- `solana-vulnerability-scanner`
- `token-integration-analyzer`
- `harness-writing`
- `coverage-analysis`
- `rust-review`
- `c-review`
- `fp-check`
- `supply-chain-risk-auditor`
- `spec-to-code-compliance`
- `mutation-testing`
- `zeroize-audit`
- `yara-rule-authoring`
- `constant-time-testing`
- `fuzzing-obstacles`
- `sharp-edges`

Luna-specific changes include deterministic local routing metadata, a separate skill-admission gate,
bounded prompt injection, evidence contracts, integration with Luna BUILD-TO-BREAK/V17/V18 concepts,
removal of upstream subagent/workflow assumptions, and explicit separation between skill
instructions and host/tool execution authority.

The `security-data-analysis` skill is original Shield-Corp/Luna Cyber work and is not
derived from the Trail of Bits repository.

No upstream executable workflow, shell script, subagent, or scanner is imported merely by
installing these skill definitions. Tool names in `allowed-tools` are descriptive metadata
only. Luna's `AgentHarness`, `ExecutionIntent`, host-safety checks, and supervised executor
remain authoritative.
