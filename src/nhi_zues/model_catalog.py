from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from .config import AppConfig, load_config
from .redaction import redact_secret_text
from .state_io import write_json_file


OPENAI_MODEL_FALLBACKS = [
    {
        "id": "gpt-5.4-nano",
        "label": "GPT-5.4 nano - lowest-cost default",
        "source": "fallback",
    },
    {
        "id": "gpt-5.4-mini",
        "label": "GPT-5.4 mini - balanced low-cost drafting",
        "source": "fallback",
    },
    {
        "id": "gpt-5.4",
        "label": "GPT-5.4 - stronger reasoning",
        "source": "fallback",
    },
    {
        "id": "gpt-5.5",
        "label": "GPT-5.5 - strongest, higher cost",
        "source": "fallback",
    },
]


def model_catalog_state(config: AppConfig) -> dict:
    cache = _read_json(config.state_dir / "openai_models.json", default={})
    cached_models = cache.get("models") if isinstance(cache, dict) else None
    live = bool(cached_models)
    models = merge_model_options(
        config.openai_model,
        cached_models if isinstance(cached_models, list) else OPENAI_MODEL_FALLBACKS,
        include_fallbacks=not live,
    )
    source = "OpenAI /v1/models" if live else "fallback"
    message = (
        f"{len(models)} account model options cached from OpenAI."
        if live
        else "Fallback model suggestions shown. Add an API key and refresh models for this project."
    )
    return {
        "live": live,
        "source": source,
        "message": message,
        "fetched_at": str(cache.get("fetched_at") or "") if isinstance(cache, dict) else "",
        "total_models": int(cache.get("total_models") or len(models)) if isinstance(cache, dict) else len(models),
        "models": models,
    }


def fetch_openai_models() -> dict:
    load_dotenv(override=True)
    config = load_config()
    fallback = model_catalog_state(config)
    if not config.openai_api_key:
        return {
            "ok": False,
            "live": False,
            "source": fallback["source"],
            "message": "OpenAI API key is missing. Save a key first, then refresh models.",
            "models": fallback["models"],
        }

    request = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "live": False,
            "source": fallback["source"],
            "message": safe_openai_error(exc),
            "models": fallback["models"],
        }
    except Exception as exc:
        return {
            "ok": False,
            "live": False,
            "source": fallback["source"],
            "message": f"Could not fetch OpenAI models: {redact_secret_text(str(exc))}",
            "models": fallback["models"],
        }

    raw_models = payload.get("data", [])
    fetched_options = []
    if isinstance(raw_models, list):
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not looks_like_text_model(model_id):
                continue
            fetched_options.append(
                {
                    "id": model_id,
                    "label": model_id,
                    "source": "openai",
                    "owned_by": str(item.get("owned_by") or ""),
                    "created": item.get("created"),
                }
            )

    if not fetched_options:
        models = merge_model_options(
            config.openai_model,
            OPENAI_MODEL_FALLBACKS,
            include_fallbacks=True,
        )
        return {
            "ok": False,
            "live": False,
            "source": "fallback",
            "message": "OpenAI returned models, but none matched Kabuki-Cord's text/reasoning filter.",
            "models": models,
            "total_models": len(raw_models) if isinstance(raw_models, list) else 0,
        }

    models = merge_model_options(config.openai_model, fetched_options)
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cache_payload = {
        "live": True,
        "source": "OpenAI /v1/models",
        "fetched_at": fetched_at,
        "models": models,
        "total_models": len(raw_models) if isinstance(raw_models, list) else len(models),
    }
    write_json_file(config.state_dir / "openai_models.json", cache_payload)
    return {
        "ok": True,
        **cache_payload,
        "message": f"Loaded {len(models)} OpenAI text/reasoning model options for this key.",
    }


def merge_model_options(
    current_model: str,
    model_options: list | tuple,
    *,
    include_fallbacks: bool = False,
) -> list[dict]:
    by_id: dict[str, dict] = {}
    if include_fallbacks:
        for option in OPENAI_MODEL_FALLBACKS:
            by_id[option["id"]] = dict(option)
    for option in model_options:
        if isinstance(option, str):
            model_id = option.strip()
            payload = {"id": model_id, "label": model_id, "source": "openai"}
        elif isinstance(option, dict):
            model_id = str(option.get("id") or "").strip()
            payload = dict(option)
            payload["id"] = model_id
            payload["label"] = str(payload.get("label") or model_id)
        else:
            continue
        if model_id:
            by_id[model_id] = payload
    if current_model and current_model not in by_id:
        by_id[current_model] = {
            "id": current_model,
            "label": f"{current_model} - current setting",
            "source": "current",
        }
    return sorted(by_id.values(), key=model_option_sort_key)


def model_option_sort_key(option: dict) -> tuple[int, str]:
    model_id = str(option.get("id") or "")
    preferred_order = {
        "gpt-5.4-nano": 0,
        "gpt-5.4-mini": 1,
        "gpt-5.4": 2,
        "gpt-5.5": 3,
    }
    return (preferred_order.get(model_id, 20), model_id)


def looks_like_text_model(model_id: str) -> bool:
    if not model_id:
        return False
    lowered = model_id.lower()
    excluded = (
        "embedding",
        "moderation",
        "realtime",
        "whisper",
        "tts",
        "transcribe",
        "image",
        "dall-e",
        "audio",
        "search",
    )
    if any(part in lowered for part in excluded):
        return False
    modern_gpt_prefixes = (
        "gpt-5",
        "gpt-4.5",
        "gpt-4.1",
        "gpt-4o",
        "chatgpt-4o",
    )
    return lowered.startswith(modern_gpt_prefixes) or (
        lowered.startswith("o") and len(lowered) > 1 and lowered[1].isdigit()
    )


def safe_openai_error(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        detail = str(payload.get("error", {}).get("message") or raw)
    except Exception:
        detail = str(exc)
    return f"OpenAI model fetch failed ({exc.code}): {redact_secret_text(detail)}"


def _read_json(path, *, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))
