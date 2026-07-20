---
name: image-studio
description: Generate, compare, refine, and export image assets from a single creative brief. Recraft-first; uses other configured image providers only with explicit user approval.
allowed-tools: "Read,Write,Grep,Glob,AskUserQuestion,ToolSearch,Bash(curl:*),Bash(file:*),Bash(mkdir:*),mcp__recraft__*"
model-tier: standard
effort: high
version: "1.0.0"
author: "flurdy"
---

# Image Studio

Generate project-ready icons, illustrations, backgrounds, and raster imagery from one creative brief. Use Recraft when it is configured. Other image providers are optional adapters, not a requirement.

## Usage

```
/image-studio "A friendly green leaf icon for an environmental dashboard"
/image-studio icon "A green leaf" --vector
/image-studio illustration "A product onboarding scene" --providers recraft,openai --variants 2
/image-studio refine <image-url> "use a dark background and retain the subject"
```

## Guardrails

- Do not generate or call a provider until the user has confirmed the provider set and number of variants for this run. Treat provider billing as unknown unless the runtime proves otherwise. An explicit current-run command such as `--providers recraft --variants 2` is confirmation; otherwise ask immediately before generation.
- Never infer that OpenAI, Google, or another provider is configured, available, or free. Use only tools actually available in the current runtime, and do not perform hidden retries or extra generations.
- Keep one shared brief across providers. State unavoidable provider-specific changes before generating.
- Do not claim outputs are equivalent. Compare them against the brief, not against each other as a technical benchmark.
- Do not use third-party logos, characters, or living-artist imitation unless the user confirms they have the necessary rights. Flag uncertainty rather than making a legal claim.
- Do not alter source code or commit assets unless the user explicitly asks. Do not overwrite an existing asset without confirmation.

## 1. Build the creative brief

Extract or ask for the minimum missing details:

| Field | Required guidance |
|---|---|
| Asset | Icon, logo, illustration, background, or photorealistic image |
| Subject and composition | Main subject, must-have and must-avoid details |
| Destination | Product surface and intended path, if known |
| Format | SVG/vector for scalable icons; PNG/WebP/JPEG for raster assets |
| Size and ratio | Pixel dimensions or ratio; request target sizes for raster |
| Transparency | Required, forbidden, or irrelevant |
| Style | Reference, palette, lighting, line weight, and accessibility constraints |
| Variants | Provider set and variants per provider |

For a vague brief, ask one grouped question before generation. Default to **one Recraft variant only after the user explicitly confirms it**. Recommend vector output for simple UI icons and raster output for photographic or textured work.

Convert the brief into a concise provider-neutral prompt. Preserve negative constraints explicitly, for example: `no text, no border, transparent background`.

## 2. Select providers and generation plan

1. Use `ToolSearch` to discover image-capable MCP tools in the current runtime when they are not already loaded. A missing search result means the provider is unavailable for this run.
2. Propose the smallest useful run: provider names, model where relevant, variants per provider, requested ratio, style, and total expected images.
3. Ask for confirmation if the user has not already specified the providers and variant count.
4. Record this run's metadata in the response: brief/prompt, provider, model, style, requested ratio, and timestamp. Do not expose credentials or opaque account data.

### Provider adapter contract

Use an adapter only when its tools are configured. Each adapter must support, or clearly report it cannot support:

- text-to-image generation;
- requested ratio or dimensions;
- format/transparency capability;
- model/style selection;
- output URL or downloadable output;
- provider and model metadata.

If an adapter cannot meet a hard requirement, exclude it from the run and explain why. Do not invent a common API or add provider configuration while using this skill.

## 3. Recraft adapter

Use `recraft_suggest_model` when model, speed, quality, or style compatibility is unclear. Include the asset type, desired output, constraints, and quality/cost trade-off in its request.

Use `recraft_generate_image` with:

- `prompt`: the normalized brief;
- `image_size`: requested ratio or compatible dimensions;
- `n`: the confirmed count, from 1 to 6;
- `model`: the suggested model or the user-selected model;
- `input_style`: `vector_illustration` for scalable illustrations/logos, `icon` only when its compatible model is selected, or a raster style such as `realistic_image`/`digital_illustration` when appropriate.

`input_style` and `input_style_id` are mutually exclusive. Only use a custom `input_style_id` when the user names or selects an available style. Recraft returns output URLs and previews; use `recraft_get_image_viewer` when visual comparison is needed.

### Recraft refinement

After the user chooses a candidate, use only the operation suited to the requested outcome:

| Need | Recraft tool |
|---|---|
| Remove a background | `recraft_remove_background` |
| Convert a raster to vector | `recraft_vectorize_image` |
| Preserve detail while enlarging | `recraft_crisp_upscale` |
| Creatively enhance while enlarging | `recraft_creative_upscale` |
| Produce related alternatives | `recraft_variate_image` |
| Change/edit a supplied image | `recraft_image_to_image`, `recraft_inpaint_image`, or region/background tools |

These operations require a publicly accessible HTTPS image URL. For a local input, obtain an upload URL with `recraft_request_upload_url`, upload it as directed, then pass the resulting image URL. Re-check transparency and output type after any transformation.

## 4. Compare and select

Present variants in a compact table, grouped by provider:

| ID | Provider / model | Format or type | Ratio | Notes |
|---|---|---|---|---|
| R1 | Recraft / recraftv4_1 | vector illustration | 1:1 | Meets brief; transparent background requested |

Use the viewer or supplied previews for visual inspection. State concrete differences against the brief: composition, readability at target size, transparency, palette, and unwanted artifacts. Ask the user to select an ID, request a refinement, or reject the batch. Never download or place every candidate in the repository by default.

## 5. Export the selected asset

1. Confirm the candidate, destination directory, filename, and final format. Inspect the project for established asset conventions before proposing a path.
2. Download only the selected output using its returned URL. Create the destination directory only after confirmation.
3. Use predictable names: lowercase kebab-case, purpose first (for example, `environment-leaf-icon.svg`). Retain the provider's original extension unless the provider explicitly returns a compatible requested format.
4. Verify the downloaded file exists and inspect its type with `file`. For raster assets, report actual dimensions when available. For vector assets, confirm it is SVG before claiming it is scalable.
5. Report provenance: final file path, source candidate ID, provider/model, prompt, style, and transformations. Store a sidecar metadata file only when the user asks or the repository has an established convention.

If a requested format cannot be produced, say so and offer the available format or a post-processing option; do not relabel file extensions.

## Report

After each run, report:

- the confirmed generation plan and providers used;
- generated candidate IDs and their output URLs;
- which hard requirements each candidate met or missed;
- selected asset path and provenance, if exported;
- any unavailable provider or capability and why.
