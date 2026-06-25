#!/usr/bin/env python3
"""Generate Dify predefined model YAMLs for Runware from /v1/models.

Smart-but-honest:
  - one /v1/models fetch (or --input FILE); no per-model probing.
  - capabilities default on (tool_call, structured_output); per-model exceptions
    live in CAPABILITY_OVERRIDES. vision/document/audio/video are derived from
    input_modalities. reasoning is opt-in per model (adds a reasoning_effort rule).
  - pricing converted to Dify's per-million + unit=1e-6 convention (USD).
  - a missing context_length is NOT faked: the model is skipped with a warning
    (use --default-context N to include it with a fallback).
  - every entity is validated against dify_plugin's AIModelEntity before writing.
  - interactive review (approve/edit/skip) by default; --yes for CI; --plan dry-run.
  - idempotent: existing YAMLs are skipped unless --all.

Build-time tool; excluded from the package (.difyignore). Re-run and bump the
plugin version when Runware's catalog changes.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

try:
    from dify_plugin.entities.model import AIModelEntity  # validation only
except Exception:  # pragma: no cover
    AIModelEntity = None

API_KEY_ENV = "RUNWARE_API_KEY"
DEFAULT_BASE = "https://api.runware.ai/v1"
CURRENCY = "USD"
UNIT = "0.000001"  # Dify: per-token cost = value * unit  ->  value is "per million"
QUANT = ("fp8", "fp16", "bf16", "awq", "gptq", "int4", "int8", "w8a8", "w4a16")

# Applied to every chat model; override per model in CAPABILITY_OVERRIDES.
DEFAULT_CAPS = {"tool_call": True, "structured_output": True, "reasoning": False}

# The smart bit: encode known per-model exceptions here, keyed by exact model id.
#   "some-model-without-tools": {"tool_call": False},
#   "a-thinking-model":         {"reasoning": True},
#   "vision-only-edge-case":    {"structured_output": False},
CAPABILITY_OVERRIDES: dict[str, dict] = {}

# Clean display labels for models whose /v1/models `name` is just the raw id.
# (Values are suggestions — confirm against Runware's intended naming.)
LABEL_OVERRIDES: dict[str, str] = {
    "moonshotai-kimi-k2-6": "Kimi K2.6",
    "google-gemma-4-31b": "Gemma 4 31B",
    "google-gemini-3-5-flash": "Gemini 3.5 Flash",
    "anthropic-claude-fable-5": "Claude Fable 5",
}


def fetch_models(base: str) -> list:
    import httpx
    token = os.environ.get(API_KEY_ENV)
    if not token:
        sys.exit(f"{API_KEY_ENV} not set (or pass --input FILE)")
    with httpx.Client(base_url=base.rstrip("/") + "/",
                      headers={"Authorization": f"Bearer {token}"}, timeout=30) as c:
        data = c.get("models").json()
    return data["data"] if isinstance(data, dict) and "data" in data else data


def load_models(args) -> list:
    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        return data["data"] if isinstance(data, dict) and "data" in data else data
    return fetch_models(args.base)


def per_million(value) -> str | None:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    return f"{round(rate * 1_000_000, 6):g}" if rate else None


def caps_for(model_id: str) -> dict:
    caps = dict(DEFAULT_CAPS)
    caps.update(CAPABILITY_OVERRIDES.get(model_id, {}))
    return caps


def fallback_label(model_id: str) -> str:
    s = model_id
    for q in QUANT:
        s = re.sub(rf"[-_]?{q}\b", "", s, flags=re.I)
    return s.replace("_", " ").replace("-", " ").strip() or model_id


def features_for(caps: dict, modalities: list) -> list:
    feats = ["agent-thought"]
    if caps.get("tool_call"):
        feats += ["tool-call", "multi-tool-call", "stream-tool-call"]
    if caps.get("structured_output"):
        feats.append("structured-output")
    # Dify's OpenAI-compatible transport only sends text + image content, so we
    # advertise vision only. audio/video/document are intentionally NOT emitted
    # even when /v1/models lists them, because the chat path cannot carry them.
    mods = {str(m).lower() for m in modalities}
    if "image" in mods:
        feats.append("vision")
    seen, out = set(), []
    for f in feats:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def parameter_rules(caps: dict, max_output) -> list:
    rules = [
        {"name": "temperature", "use_template": "temperature", "type": "float"},
        {"name": "top_p", "use_template": "top_p", "type": "float"},
        {"name": "frequency_penalty", "use_template": "frequency_penalty", "type": "float"},
        {"name": "presence_penalty", "use_template": "presence_penalty", "type": "float"},
    ]
    mt = {"name": "max_tokens", "use_template": "max_tokens", "type": "int"}
    if isinstance(max_output, int) and max_output > 0:
        mt.update({"default": min(1024, max_output), "min": 1, "max": max_output})
    rules.append(mt)
    if caps.get("structured_output"):
        rules.append({"name": "response_format", "label": {"en_US": "Response Format"},
                      "type": "string", "required": False, "options": ["text", "json_object"]})
    if caps.get("reasoning"):
        rules.append({"name": "reasoning_effort", "label": {"en_US": "Reasoning Effort"},
                      "type": "string", "required": False, "options": ["low", "medium", "high"]})
    return rules


def pricing_for(model: dict):
    price = model.get("pricing") or {}
    inp, out = per_million(price.get("prompt")), per_million(price.get("completion"))
    if inp is None and out is None:
        return None
    return {"input": inp or "0", "output": out or "0", "unit": UNIT, "currency": CURRENCY}


def build_entity(model: dict, default_context):
    model_id = model["id"]
    context = model.get("context_length") or default_context
    if not context:
        print(f"WARN  {model_id}: no context_length in /v1/models — skipped "
              f"(use --default-context N to include it)", file=sys.stderr)
        return None
    caps = caps_for(model_id)
    label = LABEL_OVERRIDES.get(model_id) or model.get("name") or fallback_label(model_id)
    entity = {
        "model": model_id,
        "label": {"en_US": label, "zh_Hans": label},
        "model_type": "llm",
        "features": features_for(caps, model.get("input_modalities") or ["text"]),
        "model_properties": {"mode": "chat", "context_size": int(context)},
        "parameter_rules": parameter_rules(caps, model.get("max_output_tokens")),
    }
    pricing = pricing_for(model)
    if pricing:
        entity["pricing"] = pricing
    else:
        print(f"WARN  {model_id}: no pricing in /v1/models — emitted without pricing",
              file=sys.stderr)
    return entity


def validate(entity: dict) -> None:
    if AIModelEntity is not None:
        AIModelEntity(**entity)


def safe_filename(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", model_id.replace("/", "_")).strip("_") or "model"


def edit_yaml(text: str) -> str:
    with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as fh:
        fh.write(text)
        path = Path(fh.name)
    subprocess.run([os.environ.get("EDITOR", "nano"), str(path)], check=False)
    out = path.read_text()
    path.unlink()
    return out


def review(model_id: str, text: str):
    while True:
        print(f"\n# models/llm/{safe_filename(model_id)}.yaml\n{text}")
        choice = input("[a]pprove / [e]dit / [s]kip > ").strip().lower()
        if choice in ("a", "y", ""):
            return text
        if choice == "s":
            return None
        if choice == "e":
            text = edit_yaml(text)
            try:
                validate(yaml.safe_load(text))
            except Exception as exc:
                print(f"  invalid after edit: {exc}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Runware predefined model YAMLs for Dify.")
    ap.add_argument("--input", type=Path, help="Saved /v1/models JSON (default: fetch live).")
    ap.add_argument("--base", default=DEFAULT_BASE, help="API base for the live fetch.")
    ap.add_argument("--out", type=Path, required=True, help="Output dir, e.g. models/llm.")
    ap.add_argument("--all", action="store_true", help="Re-generate models that already have a YAML.")
    ap.add_argument("--yes", "-y", action="store_true", help="Non-interactive: accept all (for CI).")
    ap.add_argument("--plan", action="store_true", help="Print decisions; write nothing.")
    ap.add_argument("--default-context", type=int, help="Fallback context_size when omitted upstream.")
    args = ap.parse_args()

    models = load_models(args)
    if not isinstance(models, list) or not models:
        sys.exit("No models in the /v1/models payload.")

    out: Path = args.out
    ordered_ids: list = []
    written = 0
    for model in models:
        if not isinstance(model, dict) or "id" not in model:
            continue
        model_id = model["id"]
        path = out / (safe_filename(model_id) + ".yaml")

        if path.exists() and not args.all:
            ordered_ids.append(model_id)
            print(f"SKIP  {model_id} (exists)")
            continue

        entity = build_entity(model, args.default_context)
        if entity is None:
            continue
        try:
            validate(entity)
        except Exception as exc:
            print(f"WARN  {model_id}: invalid entity, skipped: {exc}", file=sys.stderr)
            continue

        if args.plan:
            print(f"PLAN  {model_id}  ctx={entity['model_properties']['context_size']}  "
                  f"[{','.join(entity['features'])}]")
            ordered_ids.append(model_id)
            continue

        text = yaml.safe_dump(entity, allow_unicode=True, sort_keys=False)
        if not args.yes:
            text = review(model_id, text)
            if text is None:
                print(f"  skipped {model_id}", file=sys.stderr)
                continue

        out.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        ordered_ids.append(model_id)
        written += 1
        print(f"  wrote {path.name}", file=sys.stderr)

    if not args.plan:
        out.mkdir(parents=True, exist_ok=True)
        (out / "_position.yaml").write_text(
            yaml.safe_dump(ordered_ids, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"  _position.yaml ({len(ordered_ids)} models, {written} (re)written)", file=sys.stderr)


if __name__ == "__main__":
    main()
