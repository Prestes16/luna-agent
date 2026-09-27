---
name: img-to-html
description: Recreate an existing UI screenshot or mock as faithful static HTML/CSS/JS using a staged, human-approved workflow. Use when the user explicitly names img-to-html or asks to reproduce an existing visual UI reference in code; do not use for text-only greenfield UI design.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  luna-domain: "ui-engineering"
  luna-purpose: "image-to-static-ui"
  luna-risk: "host-write"
  luna-network: "explicit-opt-in"
  luna-execution: "supervised"
---

# Img to HTML — Luna/Codex

## Contract

Input: one UI reference image (PNG, JPG or WebP) supplied as an attachment, local path or user-approved URL.

Output:

design-systems/<slug>/
  reference.<ext>
  wireframe.txt
  index.html
  assets/
    styles.css
    app.js              # only when behavior is required
    crops/
    generated-or-local-assets...

The final entry point is always index.html.

Default implementation is static HTML + CSS + optional JS. Do not introduce React, Vite, Tailwind, a bundler, package.json or node_modules unless the user explicitly requests a framework stack.

## Companion skills

- to-wireframe is required for Stage 1.
- openrouter-img is optional. It is used only when an asset genuinely benefits from external image generation and the user explicitly authorizes external processing for that task.
- External generation is never required for completion. CSS, locally extracted crops, project assets and local SVG/HTML reconstruction are valid fallbacks.

Before starting implementation, read references/workflow.md.

## Non-negotiable behavior

1. Preserve the reference image as reference.<ext>.
2. Build the typed ASCII wireframe before implementation.
3. Use the wireframe as the structural contract for HTML/CSS naming.
4. Complete one stage at a time.
5. At the end of every applicable stage, show the result and stop for explicit approval.
6. Do not silently advance through multiple gates.
7. Keep CSS out of index.html. No style attributes and no inline style blocks.
8. Keep JS out of index.html. Use assets/app.js only when behavior is needed.
9. Use relative asset paths.
10. Never upload a reference image, crop or derived visual to an external provider without explicit user authorization in the current task.

## Workflow

Stage 1 — Structure
- Copy the reference.
- Invoke to-wireframe with format=ascii.
- Save wireframe.txt.
- Present a short per-region implementation plan.
- Gate: structure + plan.

Stage 2 — Background
- Create the minimum index.html and assets/styles.css.
- Recreate the complete page background only.
- Prefer CSS/local assets first.
- Gate: background.

Stage 3 — Structure, components and type
- Implement nav/chrome first, then surfaces and text.
- Choose typography before fine layout tuning.
- Prefer local/project fonts; external font retrieval requires normal network authorization.
- Complete component backgrounds in this stage.
- Gate: components + typography.

Stage 4 — Remaining assets
- Add icons, avatars and content imagery left by the plan.
- Prefer exact local crops or local reconstruction when possible.
- External image generation is optional and requires explicit authorization plus the mechanical --allow-external flag in openrouter-img.
- Omit this stage when there are no remaining assets.
- Gate: assets.

Stage 5 — Integrated review
- Render at the same viewport as the reference.
- Compare full-screen screenshots.
- When both screenshots are available locally, use scripts/visual_diff.py for deterministic pixel metrics in addition to visual inspection.
- Fix integration drift: alignment, clipping, wrapping, layering and spacing.
- Gate: final result.

## Privacy and external processing

Treat screenshots as potentially sensitive by default.

Do not infer consent to upload from:
- the existence of an API key;
- a prior task;
- the presence of openrouter-img;
- the fact that the repository is public.

Authorization must apply to the current task. If it is absent, keep the workflow local and still deliver the HTML/CSS/JS result.

## Definition of done

A run is complete only when:
- reference.<ext>, wireframe.txt and index.html exist;
- CSS is externalized under assets/;
- all referenced local assets resolve;
- the final page opens without a build step;
- the implemented viewport has been compared with the reference;
- any approximation is stated explicitly;
- the final gate is approved by the user.
