---
name: to-wireframe
description: Convert an existing UI image or a supplied screen brief into a typed nested wireframe in ASCII or SVG. Use when a structural UI wireframe is needed, including as Stage 1 of img-to-html.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  luna-domain: "ui-engineering"
  luna-purpose: "typed-wireframe"
  luna-risk: "read-only"
  luna-network: "deny"
---

# To Wireframe — Luna/Codex

## Inputs

The caller must provide:
- format=ascii or format=svg
- exactly one source: image=<path/attachment> or brief=<text>
- output=<path> for briefs; for image input, output may be derived beside the image.

For img-to-html, always use format=ascii.

## Structural vocabulary

Every visually distinct surface is a labeled region. Use short reusable identifiers such as:
- nav
- hero
- section
- card, card2, card3
- media
- form
- rail
- quote

Nested surfaces must be represented as nested regions rather than flattened text.

Visible content uses typed tags:

| Tag | Meaning |
|---|---|
| [h1:], [h2:], [h3:] | headings |
| [t1:], [t2:], [t3:] | body/meta text |
| [btn:], [btn2:], [btn3:] | controls/buttons |
| [lnk:] | inactive navigation link |
| [in:] | input content/placeholder |
| [ico:] | icon |
| [img:] | image |
| [av:] | avatar |
| [chart:] | chart/data visual |

Use the same identifier for the same visual role. Use a new identifier for a real visual variant.

If text in an image is not reliably legible, use ... inside the correct tag. Do not invent copy.

## ASCII rules

- Borders use only +, - and |.
- Put the region label on the first line of each box.
- Keep typed tags inside their owning region.
- Show meaningful nesting and columns.
- Do not simulate production colors, shadows, icons or exact pixels.

See references/wireframe.example.txt for density and nesting style.

## SVG rules

- Structural only.
- Use simple rect and text elements.
- Keep a grayscale planning appearance.
- No production gradients, shadows or illustrated assets.
- Preserve an aspect ratio reasonably matching the source.

## Process

1. Inspect the image or brief.
2. Identify regions, nesting and visible typed content.
3. Produce one wireframe pass.
4. Perform one structural review:
   - every surface has a label;
   - visible text/controls use typed tags;
   - nested components remain nested;
   - active navigation is represented as a control, not an inactive link.
5. Save and report the output path.

Do not perform OCR pipelines, crops, pixel sampling, color extraction, font detection, HTML implementation or asset generation. Those belong to later img-to-html stages.
