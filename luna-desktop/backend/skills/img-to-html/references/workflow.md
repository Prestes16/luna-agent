# Img-to-HTML detailed workflow

This reference contains the operational detail for the img-to-html skill. The parent SKILL.md remains the routing and behavioral contract.

## Stage 1 — typed ASCII wireframe and plan

Create design-systems/<slug>/ and copy the source image to reference.<ext>.

Invoke the companion skill:

to-wireframe format=ascii image=<reference-path> output=<wireframe-path>

Do not perform pixel measurement, OCR, cropping, color sampling or asset generation in this stage. The purpose is structural decomposition.

After the wireframe exists, produce a compact plan that maps each region to:
- implementation stage;
- intended technique: CSS, local crop, local SVG/HTML, existing project asset, or user-authorized external generation.

Classify an image by function:
- page background -> Stage 2;
- component background -> Stage 3;
- content image/icon/avatar -> Stage 4.

Show wireframe.txt plus the plan and stop.

## Stage 2 — full page background

Prerequisite: Stage 1 approved.

Create:
- index.html with stylesheet link and empty body/minimal decorative markup;
- assets/styles.css with reset and :root variables.

Implement only the page background. CSS gradients, pseudo-elements and locally available imagery are preferred because they are deterministic and offline.

Do not add nav, cards or content yet.

Render the result in a browser and compare it with the reference. On Windows, Start-Process index.html is acceptable for manual preview. When a browser automation capability is available, prefer a fixed viewport screenshot because it improves reproducibility.

Stop at the background gate.

## Stage 3 — structure, surfaces and typography

Prerequisite: Stage 2 approved.

Implement in this order:
1. global chrome/navigation;
2. main layout regions;
3. repeated surface types;
4. text hierarchy and controls;
5. component-specific background imagery.

Use the wireframe identifiers consistently as CSS classes where practical.

Typography is selected before fine spacing work. Prefer:
1. existing project font assets;
2. installed/system fonts;
3. externally fetched fonts only when network access is appropriate and allowed.

Tune with evidence:
- sampled colors;
- measured spacing;
- gradients and stops;
- border/rim values;
- shadow/glow;
- radius;
- font size/weight/line height;
- actual line breaks at the target viewport.

Keep all CSS in assets/styles.css unless it becomes genuinely unmanageable; only then split by region and link each file explicitly.

Stop at the component gate.

## Stage 4 — remaining visual assets

Prerequisite: Stage 3 approved.

For every pending asset, choose the least risky technique that preserves fidelity:

1. reuse an existing project asset;
2. crop the exact reference locally when the crop is usable as-is;
3. recreate simple shapes/icons locally with SVG/CSS;
4. use external generation only when the user explicitly approved external processing for this task.

If external generation is authorized, use the openrouter-img companion skill. Its script requires --allow-external and reads the API key only from the process environment or the current working directory .env.

Never use the flag as a substitute for conversational authorization: both are required.

Stop at the asset gate.

## Stage 5 — integrated review

Prerequisite: previous applicable stage approved.

Capture the candidate at the same viewport dimensions as the reference.

Perform:
- visual side-by-side inspection;
- deterministic local pixel comparison with scripts/visual_diff.py when candidate/reference screenshots are both available.

Example:

uv run luna-desktop/backend/skills/img-to-html/scripts/visual_diff.py \
  --reference design-systems/<slug>/reference.png \
  --candidate design-systems/<slug>/candidate.png \
  --diff-out design-systems/<slug>/visual-diff.png

The numeric metric is diagnostic, not an automatic quality verdict. A small pixel error can still hide a meaningful UI defect, and antialiasing can create harmless differences.

Correct:
- layer ordering;
- clipping;
- viewport overflow;
- alignment;
- text wrapping;
- spacing changed by final assets;
- missing relative paths.

Show the final page and report any real approximation. Stop at the final gate.
