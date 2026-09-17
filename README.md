# hutch-provider

[Hermes Agent](https://github.com/NousResearch/hermes-agent) plugins that wire
the whole Hermes ecosystem — chat/auxiliary LLM calls, image generation, and
video generation — to **`hutch`**, a private OpenAI-compatible relay.

Three components, one repo:

| Component | Kind | What it provides |
|---|---|---|
| `model-provider/` | model-provider | First-class `hutch` inference provider (chat, aux, plugin LLM calls) |
| `image_gen/` | backend | Relay image models (gpt-image-2/2.5, Grok Imagine, Muse Image) |
| `video_gen/` | backend | Relay video models (grok-imagine-video\*, …) |

All catalogs are discovered live from the relay (`/models`, `/images/models`,
`/videos/models`) — new relay models appear in Hermes pickers without a plugin
update.

## Why

Pointing a `providers.openrouter`/`custom:openrouter` config entry at a private
relay collides with the built-in `openrouter` provider name: name normalization
can silently route requests to the official openrouter.ai endpoint with
credentials from the built-in pool (`hermes-agent#109015`). A distinct
first-class provider name sidesteps that entire bug class — nothing to
normalize, nothing to collide.

The inference profile subclasses the bundled `OpenRouterProfile` at runtime, so
the relay keeps OpenRouter's wire behavior (provider preferences,
reasoning-config passthrough, Anthropic adaptive-thinking handling, speed-tier
endpoint pins, sticky routing) and inherits upstream improvements automatically
— only the name, endpoint, and credentials differ. The image and video
backends likewise reuse the bundled OpenRouter-compatible providers with hutch
credentials.

## Install

Clone once, symlink each component into its discovery directory (drop-in,
survives Hermes upgrades):

```bash
git clone https://github.com/smwbev/hutch-provider "$HOME/.hermes/hutch-provider"

mkdir -p "$HOME/.hermes/plugins/model-providers" "$HOME/.hermes/plugins"
ln -s "$HOME/.hermes/hutch-provider/model-provider" \
      "$HOME/.hermes/plugins/model-providers/hutch"
ln -s "$HOME/.hermes/hutch-provider/image_gen" \
      "$HOME/.hermes/plugins/hutch-image"
ln -s "$HOME/.hermes/hutch-provider/video_gen" \
      "$HOME/.hermes/plugins/hutch-video"
```

Enable the two backend plugins (model providers need no enabling):

```bash
hermes plugins enable hutch-image
hermes plugins enable hutch-video
```

Updating later: `git -C "$HOME/.hermes/hutch-provider" pull`.

## Configure

`~/.hermes/.env` (secrets only):

```bash
HUTCH_BASE_URL=https://relay.example.com/v1   # your relay endpoint (required)
HUTCH_API_KEY=sk-...                          # your relay key (required)
```

The plugin ships no hardcoded endpoint — both values are yours to provide,
and `HUTCH_BASE_URL` is simultaneously Hermes' standard base-URL override
slot for the provider.

`~/.hermes/config.yaml`:

```yaml
model:
  provider: hutch
  default: anthropic/claude-fable-5
image_gen:
  provider: hutch        # optional: make hutch the active image backend
video_gen:
  provider: hutch        # optional: make hutch the active video backend
```

Verify:

```bash
hermes doctor            # Provider Connectivity -> hutch (/models probe)
hermes model             # picker lists the relay's live catalog
hermes -z "hello" --provider hutch -m anthropic/claude-fable-5
```

### Relay endpoint coverage (probed live)

| Endpoint | Relay status | Effect |
|---|---|---|
| `/models` | ✅ | text catalog + media models listed together |
| `/images/generations` | ✅ | image generation works |
| `/images/models` | ❌ 404 | catalog probe fails → unknown models default to the chat surface. Force the Images API per config: `image_gen.hutch.surface: images` |
| `/videos/generations`, `/videos` | ✅ | video generation works (xAI-family submit + `GET /videos/:request_id` polling) |
| `/videos/models` | ❌ (route absent; GET is captured by the `:request_id` poller → 400) | hutch video backend synthesizes its catalog from `/models` (video-named slugs, permissive limits) |
| `/audio/transcriptions` | ❌ 404 (CLIProxyAPI has no audio routes) | STT via the relay not possible yet (`meta/muse-voice-transcribe-1.0` unreachable through the OpenAI audio surface) |

## Notes

- `fetch_models` intentionally does **not** reuse OpenRouter's public-catalog
  override: that variant queries openrouter.ai unauthenticated and caches the
  result in a class-shared global. The `hutch` profile queries
  `{base_url}/models` with Bearer auth instead.
- The endpoint is env-only by design (no URL baked into the code): the
  `README.md` example uses a placeholder, and the profile logs a warning when
  `HUTCH_BASE_URL` is missing instead of silently registering a dead provider.
- No OAuth: the relay uses a static API key (`auth_type: api_key`).

### Known limitations (inherited OpenRouter wire behavior)

- **Speed-tier endpoint pins**: the inherited profile rewrites
  `openai/gpt-6-astra-fast` / `-flex` slugs to the base slug plus an
  OpenRouter `provider.only` preference. If your relay ever serves a REAL
  model under one of those exact slugs, the request would be silently
  rewritten to the base model. The relay's current catalog has no such slugs;
  revisit if that changes.
- **Mandatory-reasoning Anthropic models** (Claude 4.6+/fable): the profile
  deliberately omits the `reasoning` field and routes the effort knob through
  top-level `verbosity`. Whether the knob works depends on the relay mapping
  `verbosity` the way OpenRouter does; otherwise those models simply think
  adaptively.
- **Reasoning-effort clamping** consults the public openrouter.ai catalog
  (unauthenticated metadata fetch — no key or prompt content is sent). For
  slugs whose capabilities differ between the relay and OpenRouter, the clamp
  may be off.

## Tests

```bash
python -m pytest tests/ -q
```

Tests exercise the real Hermes discovery path against a temp `HERMES_HOME`
(requires a hermes-agent checkout on `PYTHONPATH`).

## License

MIT
