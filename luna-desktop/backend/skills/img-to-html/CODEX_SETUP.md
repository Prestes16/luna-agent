# Codex setup

Canonical project copies live under:

luna-desktop/backend/skills/

Required bundle:
- img-to-html
- to-wireframe
- openrouter-img

Codex supports repository-scoped skills under .codex/skills/<skill>/SKILL.md and user-scoped skills under ~/.codex/skills/<skill>/SKILL.md.

## Windows installation

From the repository root:

~~~powershell
pwsh -File .\luna-desktop\backend\skills\img-to-html\scripts\install_codex.ps1 -Scope Repo
~~~

For user-wide installation:

~~~powershell
pwsh -File .\luna-desktop\backend\skills\img-to-html\scripts\install_codex.ps1 -Scope User
~~~

Preview without writing:

~~~powershell
pwsh -File .\luna-desktop\backend\skills\img-to-html\scripts\install_codex.ps1 -Scope Repo -WhatIf
~~~

The installer copies only the three required directories and does not configure credentials.

## External image generation

The core img-to-html workflow works locally without OpenRouter.

If a specific task requires external asset regeneration:
1. the user must explicitly authorize external processing for that task;
2. set OPENROUTER_API_KEY in the process environment or current working directory .env;
3. invoke openrouter-img with --allow-external.

The supporting script deliberately does not read ~/.env and does not accept an API key on the command line.

## Verification

After installation, Codex should discover:
- img-to-html
- to-wireframe
- openrouter-img

Invoke img-to-html explicitly for the first validation run and use a non-sensitive screenshot. Confirm that Stage 1 stops after the wireframe + plan gate before allowing later stages.
