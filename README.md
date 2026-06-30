# Runware — Dify model provider plugin

Registers **Runware** as a first-class model provider in Dify. Runware exposes
an OpenAI-compatible `/v1/chat/completions` endpoint, so this plugin subclasses
the Dify SDK's `OAICompatLargeLanguageModel` and only adds Runware-specific
wiring (branding, credential schema, predefined model catalog).
 
## Install & configure
 
1. Install from the Dify Marketplace, or upload the `.difypkg` directly under
   **Plugins → Install Plugin → Local Package**.
2. Go to **Settings → Model Provider → Runware** and add credentials:
   - **API Key** — required. Get one from [runware.ai](https://runware.ai/).
   - **API endpoint URL** — optional, defaults to `https://api.runware.ai/v1`.
     Only change this if you're proxying or self-hosting an OpenAI-compatible
     endpoint.
3. Enable the models you want under that provider. Predefined models (Claude,
   GPT, Gemini, DeepSeek, Qwen, GLM, MiniMax, Kimi, Grok) show up automatically
   — no per-model setup needed.
4. For a model not in the predefined list, add it as a **customizable model**:
   enter the model id, the same API key, and its context size, max output
   tokens, vision support, and tool-calling support (check Runware's model
   catalog for these values per model).
5. Use the model anywhere Dify lets you pick an LLM — chatbot, agent, or
   workflow node.
 
No other connection requirements: the plugin only calls Runware's
OpenAI-compatible HTTPS API (`/v1/chat/completions`) with the credentials
above. No webhooks, no inbound connections, no other services involved.

## Design note (read before changing the shape)

The Dify Plugin SDK (`dify_plugin`) supports exactly two configurate methods:
`predefined-model` and `customizable-model`. There is **no `fetch-from-remote`
method**, and there is no runtime hook that returns a credential-authenticated
model list for the UI dropdown (`models()` / `predefined_models()` receive no
credentials; `get_ai_model_schemas` is per-model). Auto-discovery from
`/v1/models` is therefore a **build step**, not a runtime feature.

This plugin uses both methods:

- **predefined-model** — models are checked-in YAMLs under `models/llm/`. The
  API key is entered **once** at the provider level (`provider_credential_schema`).
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
├── pyproject.toml             # deps, dev dependency group, pytest config
├── _assets/                   # brand icons (icon.svg, icon_square.svg)
├── provider/
│   ├── runware.yaml           # methods + dual credential schemas + model glob
│   └── runware.py             # validate_provider_credentials
├── models/llm/
│   ├── llm.py                 # OAICompat subclass + credential injection
│   ├── _position.yaml         # display order
│   └── *.yaml                 # predefined models
└── tests/
    ├── test_llm.py
    └── test_provider.py
```

## Local development

```bash
uv sync                   # installs runtime + dev deps (pytest)
uv run pytest             # run the test suite
dify plugin package ./   # produces runware.difypkg
```

The baseline that already works without this plugin: the official
`langgenius/openai_api_compatible` plugin with Base URL `https://api.runware.ai/v1`
+ API key + model id (manual, per model). This plugin adds branding, a one-time
key, and the predefined catalog.

## Contact, source & privacy

- Source: https://github.com/runware/dify-runware
- Privacy policy: see PRIVACY.md

Note: `author` in `manifest.yaml` must equal your Dify Marketplace organization
name (your GitHub handle/org). It is set to `Runware`; change it if you publish
under a different account.
