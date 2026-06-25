# Runware — Dify model provider plugin

Registers **Runware** as a first-class model provider in Dify. Runware exposes
an OpenAI-compatible `/v1/chat/completions` endpoint, so this plugin subclasses
the Dify SDK's `OAICompatLargeLanguageModel` and only adds Runware-specific
wiring (branding, credential schema, predefined model catalog).

## Design note (read before changing the shape)

The Dify Plugin SDK (`dify_plugin`) supports exactly two configurate methods:
`predefined-model` and `customizable-model`. There is **no `fetch-from-remote`
method**, and there is no runtime hook that returns a credential-authenticated
model list for the UI dropdown (`models()` / `predefined_models()` receive no
credentials; `get_ai_model_schemas` is per-model). Auto-discovery from
`/v1/models` is therefore a **build step**, not a runtime feature.

This plugin uses both methods (the OpenRouter pattern):

- **predefined-model** — models are checked-in YAMLs under `models/llm/`,
  generated from `/v1/models` by `tools/gen_runware_models.py`. The API key is
  entered **once** at the provider level (`provider_credential_schema`).
- **customizable-model** — fallback for any model not in the snapshot; the user
  enters the model id + per-model settings (`model_credential_schema`).

`endpoint_url` and `mode` are required by the OAICompat base; for predefined
models they are injected in `RunwareLargeLanguageModel._update_credentials`
before delegating to the base (the DeepSeek/OpenRouter pattern).

## Layout

```
runware/
├── manifest.yaml              # plugin manifest
├── main.py                    # entrypoint
├── requirements.txt
├── _assets/                   # brand icons (icon.svg, icon_square.svg)
├── provider/
│   ├── runware.yaml           # methods + dual credential schemas + model glob
│   └── runware.py             # validate_provider_credentials
├── models/llm/
│   ├── llm.py                 # OAICompat subclass + credential injection
│   ├── _position.yaml         # display order (generated)
│   └── *.yaml                 # predefined models (generated)
└── tools/
    └── gen_runware_models.py  # /v1/models -> YAMLs (build-time, not packaged)
```

## Regenerate the model catalog

`models/llm/` ships with the predefined catalog already generated from a real
Runware `/v1/models` response. To refresh it (new models, pricing, or context
changes), re-run the generator and bump the plugin version:

```bash
# live fetch (needs RUNWARE_API_KEY in the environment)
python tools/gen_runware_models.py --out models/llm --plan                 # preview, writes nothing
python tools/gen_runware_models.py --out models/llm                        # interactive: approve/edit/skip
python tools/gen_runware_models.py --out models/llm --all                  # regenerate every model
python tools/gen_runware_models.py --input models.json --out models/llm    # from a saved file (no network)
python tools/gen_runware_models.py --out models/llm --yes                  # non-interactive (CI)
```

Field mapping: `name` → `label` (with `LABEL_OVERRIDES` for ids whose upstream
name is just the raw id); `context_length` → `context_size`;
`pricing.prompt`/`pricing.completion` → per-million `pricing.input`/`pricing.output`
(unit `0.000001`, USD); `max_output_tokens` → max of the `max_tokens` rule.
`input_modalities` containing `image` → `vision`; audio/video/document are
intentionally NOT emitted, because the OpenAI-compatible transport only carries
text + image. `tool-call` and `structured-output` are on by default; per-model
exceptions (and opt-in `reasoning`) live in `CAPABILITY_OVERRIDES`. Models with
no `context_length` upstream are skipped unless `--default-context N` is passed.

## Local development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
dify plugin package ./   # produces runware.difypkg
```

The baseline that already works without this plugin: the official
`langgenius/openai_api_compatible` plugin with Base URL `https://api.runware.ai/v1`
+ API key + model id (manual, per model). This plugin adds branding, a one-time
key, and the predefined catalog.

## Publish

Third-party plugins go to the community marketplace repo (not the first-party one):

- Fork `langgenius/dify-plugins`, add this plugin under `<org>/runware/` together
  with the packaged `.difypkg`, then open a PR. Submissions are reviewed before listing.
- Or self-publish via the Creator Center at `creators.dify.ai`.

`langgenius/dify-official-plugins` is maintained by the Dify team (first-party
plugins) and is not the route for a third-party provider.

## Contact, source & privacy

- Privacy policy: see PRIVACY.md

Note: `author` in `manifest.yaml` must equal your Dify Marketplace organization
name (your GitHub handle/org). It is set to `Runware`; change it if you publish
under a different account.
