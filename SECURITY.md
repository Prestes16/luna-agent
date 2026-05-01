# Security Policy

## Supported versions

Only the latest release receives security patches.

| Version | Supported |
| ------- | --------- |
| 0.4.x   | Yes       |
| < 0.4   | No        |

## Reporting a vulnerability

**Do not open a public issue for security bugs.**

Send details through a private channel:
- Email: [to be configured before publishing]
- Or open a private GitHub security advisory once the repo is published

Include:
- Description of the vulnerability
- Reproduction steps (PoC if possible)
- Estimated impact
- Suggested fix (optional)

## SLA

- Initial response: 72 business hours
- Patch for P0 (RCE, credential leak): 7 days
- Patch for P1 (XSS, path traversal): 30 days
- Public credit: after the fix is released

## Scope

In scope:
- Bugs allowing unauthorized code execution
- Leakage of API keys or user data
- Privilege escalation
- Bypass of critical guardrails

Out of scope:
- Social engineering of maintainers
- Bugs in third-party dependencies (report upstream)
- Attacks requiring physical access to the device
- Insecure configuration set by the user

## User best practices

- Keep Luna up to date
- Never share your `~/.luna-agent/` folder (it contains API keys)
- Do not run Luna with root / admin privileges unless necessary
- Review commands before allowing them in agentic modes
- Use `--master-mode` only on development machines