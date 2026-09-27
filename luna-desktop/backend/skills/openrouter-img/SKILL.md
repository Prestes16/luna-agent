---
name: openrouter-img
description: Generate or edit image assets through the OpenRouter Images API when external processing has been explicitly authorized. Use only as an optional companion to workflows such as img-to-html; never upload local images implicitly.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  luna-domain: "ui-engineering"
  luna-purpose: "external-image-generation"
  luna-risk: "external-data-transfer"
  luna-network: "explicit-opt-in"
---

# OpenRouter Img — Luna/Codex

This companion skill is intentionally gated.

## Authorization contract

Before sending any local image or crop to OpenRouter:
1. the user must explicitly authorize external processing for the current task;
2. the operator/agent must pass --allow-external.

The script refuses network execution without the flag. The flag is a mechanical guard, not proof of user consent.

Do not infer permission from the presence of OPENROUTER_API_KEY.

## Credentials

The script reads OPENROUTER_API_KEY only from:
- the process environment; or
- .env in the current working directory.

It does not read ~/.env and does not accept --api-key.

## Script

Path:

openrouter-img/scripts/generate_image.py

Example generation after authorization:

~~~bash
uv run openrouter-img/scripts/generate_image.py \
  --allow-external \
  --prompt "Recreate this UI icon with transparent background." \
  --input-image assets/crops/icon.png \
  --filename assets/icon.png \
  --model gpt2 \
  --resolution 1K \
  --aspect-ratio 1:1
~~~

Use --dry-run before an external request when validating paths/parameters.

## Current aliases

- flash -> google/gemini-3.1-flash-image
- pro -> google/gemini-3-pro-image
- gpt2 -> openai/gpt-image-2
- flux -> black-forest-labs/flux.2-pro
- flux-max -> black-forest-labs/flux.2-max
- seedream -> bytedance-seed/seedream-5-0-lite
- seedream-pro -> bytedance-seed/seedream-5-0-pro
- qwen -> qwen/qwen-image-3-pro
- grok -> x-ai/grok-imagine-image-2.0

A full model slug may be passed instead of an alias.

## Data minimization

When editing from a source image:
- crop locally first;
- include only the pixels required for the target asset;
- never send a full application screenshot when a small crop is sufficient;
- do not send secrets, tokens, private dashboards or unrelated user data.

External generation is optional. If authorization is absent, return to the parent workflow and use local reconstruction/crops instead.
