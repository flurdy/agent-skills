# Image providers

Checked 2026-10-13 against the official documentation linked below. These are published
prices and capabilities, not account state: the runtime proves nothing about a balance, plan,
or quota. Recheck a source before relying on a figure.

## Adapter decisions

| Provider route | Auth | Billing per official docs | Output | Decision |
|---|---|---|---|---|
| Recraft hosted MCP server (`https://mcp.recraft.ai/mcp`) | OAuth | Studio **subscription credits**, the same balance as the Recraft Studio app | PNG/WebP/JPG raster; native SVG from `*_vector` models | **Default.** The only adapter this skill ships. |
| Recraft API | API key | Prepaid **API Units**, a separate pool ($1 = 1,000 units) | Same | **Not used** by this skill. Listed so unit prices are not mistaken for MCP prices. |
| Recraft external models (GPT Image, Nano Banana, Flux, Ideogram, …) | Studio UI | Studio credits, 1–40 per image by model | Raster | **Skip.** Studio-only; not on the API and not in the documented MCP tool list. |
| OpenAI built-in image tool in Codex | ChatGPT sign-in | Draws on the ChatGPT plan's usage limits 3–5x faster than text turns, then on credits; API pricing when signed in with an API key | Raster | **Conditional.** Eligible only inside Codex when the tool is actually exposed in the run and the user accepts that usage draw. Not a bridge for Pi or Claude Code. |
| OpenAI Images API, including the `imagegen` skill's CLI fallback | API key | Metered API tokens, billed separately from ChatGPT plans | Raster | **Not a default.** Explicit opt-in only when already configured. |
| Google Gemini image models (Nano Banana family) | Gemini API key | Paid tier only; Google AI Pro/Ultra plans cover the AI Studio UI, not API calls | Raster | **Not a default.** Explicit opt-in only when already configured. |
| Local Flux / SDXL via ComfyUI or diffusers | Local runtime | No per-image fee; model licences apply (Flux.1 schnell Apache-2.0, SDXL OpenRAIL++-M) | Raster | **Skip** until a runner is separately set up and verified. This skill never installs one. |

Documented capability, not a quality ranking: native SVG comes only from Recraft vector models;
every other route returns raster output.

## Recraft credit costs on the MCP route

Studio credits per image; a top-up of 200 credits costs $2.

| Operation | Credits |
|---|---|
| V4.1 Flash raster | 1 |
| V4.1 raster / V4.1 Utility | 2 |
| V4.1 Pro raster | 10 |
| V4.1 Vector | 4 |
| V4.1 Pro Vector | 12 |
| V3 raster / V3 Vector | 1 / 2 |
| Remove background, vectorize, crisp upscale | 1 each |
| Image editing, variations, replace background | model price |

Subscription credits reset monthly and do not roll over; top-up credits never expire and are used
after them. An "insufficient credits" error means the Studio balance, not API Units.

## Other reference prices

- Gemini Nano Banana 2.1 (`gemini-nano-banana-2.1`): $0.0336 per 1K image output, plus input and
  thinking tokens; no free tier.
- OpenAI GPT Image via the API: token-priced per image input/output; see the pricing page.

## Sources

- Recraft MCP: [getting started](https://www.recraft.ai/docs/mcp-reference/getting-started),
  [tools](https://www.recraft.ai/docs/mcp-reference/tools),
  [remote server](https://www.recraft.ai/docs/mcp-reference/remote-server),
  [Developer Terms §4.3 and §5.6](https://www.recraft.ai/legal/developer-terms)
- Recraft billing: [credits](https://www.recraft.ai/docs/plans-and-billing/credits),
  [API pricing](https://www.recraft.ai/docs/api-reference/pricing),
  [external models](https://www.recraft.ai/docs/recraft-models/external-models)
- OpenAI: [Codex pricing](https://developers.openai.com/codex/pricing),
  [Codex authentication](https://developers.openai.com/codex/auth),
  [imagegen skill](https://github.com/openai/skills/blob/main/skills/.system/imagegen/SKILL.md),
  [image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- Google: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing),
  [Nano Banana 2.1](https://ai.google.dev/gemini-api/docs/models/gemini-nano-banana-2.1),
  [Google AI plans](https://ai.google.dev/gemini-api/docs/google-ai-plans)
- Local: [ComfyUI system requirements](https://docs.comfy.org/installation/system_requirements),
  [FLUX.1 schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell),
  [SDXL base 1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)
