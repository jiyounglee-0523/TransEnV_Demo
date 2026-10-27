"""Trans-EnV demo REST backend for the static (GitHub Pages) frontend in docs/.

Runs the Trans-EnV guideline pipeline rule by rule and streams progress to the UI.

Request path in production:
    browser (docs/index.html) -> ngrok -> proxy.py (frontend host) -> ssh tunnel -> this server (backend host)

Run with:  ./run_backend.sh <host> <port> [--foreground]
           ./run_proxy_server.sh <host> <port> <backend_url> [--foreground]
           ./run_ngrok.sh <port> <ngrok_config>

Environment variables:
    CORS_ORIGINS   comma-separated allowed origins (default "*")

Endpoints:
    GET  /api/health      liveness check used by the UI on load
    GET  /api/meta        dialects, L1 languages, CEFR levels, providers, examples
    POST /api/transform   NDJSON stream of rule-by-rule events
"""

import json
import logging
import os
import random
import re
import sys
from pathlib import Path

import anthropic
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
_logger = logging.getLogger("transenv.backend")

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

from registry.guidline import L1_GRAMMARERROR                      # noqa: E402
from registry.prompt import return_system_message, semantic_check  # noqa: E402
from utils.guidline_utils import (                                 # noqa: E402
    extract_guideline_examples,
    extract_transformed_sentence,
)

# ---------------------------------------------------------------------------
# Guideline loading
# ---------------------------------------------------------------------------

DIALECTS = {
    "AAVE (Urban African American Vernacular English)": "Urban African American Vernacular English",
    "Appalachian English": "Appalachian English",
    "Australian English": "Australian English",
    "Australian Vernacular English": "Australian Vernacular English",
    "Bahamian English": "Bahamian English",
    "East Anglian English": "East Anglian English",
    "Irish English": "Irish English",
    "Manx English": "Manx English",
    "New Zealand English": "New Zealand English",
    "Newfoundland English": "Newfoundland English",
    "North of England dialects": "English dialects in the North of England",
    "Ozark English": "Ozark English",
    "Scottish English": "Scottish English",
    "Southeast American enclave dialects": "Southeast American enclave dialects",
    "Southeast of England dialects": "English dialects in the Southeast of England",
    "Southwest of England dialects": "English dialects in the Southwest of England",
    "Tristan da Cunha English": "Tristan da Cunha English",
    "Welsh English": "Welsh English",
}

L1_LANGUAGES = list(L1_GRAMMARERROR.keys())

with open(ROOT / "assets/guidelines/orig_generated_guideline_wo_example.json") as f:
    _dialect_guidelines = {g["feature"][3:-3]: g["guideline"] for g in json.load(f)}

with open(ROOT / "assets/guidelines/python_grammar_error.json") as f:
    _l1_guidelines = {g["grammar_error"]: g["guideline"] for g in json.load(f)}

with open(ROOT / "assets/guidelines/orig_generated_guideline_wo_example_grammar_error.json") as f:
    _cefr_guidelines = {g["feature"][1:-1].strip(): g["guideline"] for g in json.load(f)}

with open(ROOT / "assets/cefr_features.json") as f:
    _cefr_features = json.load(f)  # {"A": [...], "B": [...]} precomputed from the Grammar Profile

_ewave = pd.read_csv(ROOT / "assets/ewave/ewave.csv")

CEFR_SAMPLE_SIZE = 10
CEFR_CHOICES = ["A (beginner)", "B (intermediate)", "None (L1 errors only)"]


def dialect_rule_count(label):
    language_id = DIALECTS[label]
    features = _ewave[
        (_ewave["Language_ID"] == language_id) & (_ewave["Value"] == "A")
    ]["Parameter_ID"].tolist()
    return len([f for f in features if f in _dialect_guidelines])


def build_guideline(variety_type, dialect_label, l1_language, cefr_level):
    """Return stages: a list of lists of (feature, guideline_text, task_name)."""
    if variety_type == "dialect":
        language_id = DIALECTS[dialect_label]
        features = _ewave[
            (_ewave["Language_ID"] == language_id) & (_ewave["Value"] == "A")
        ]["Parameter_ID"].tolist()
        return [[(f, _dialect_guidelines[f], "english_dialect")
                 for f in features if f in _dialect_guidelines]]

    stages = []
    if cefr_level and cefr_level[0] in "AB":
        level = cefr_level[0]
        sampled = random.sample(
            _cefr_features[level], min(CEFR_SAMPLE_SIZE, len(_cefr_features[level]))
        )
        stages.append([(f"CEFR-{level}: {f}", _cefr_guidelines[f], "cefr")
                       for f in sampled])
    features = L1_GRAMMARERROR[l1_language]
    stages.append([(f, _l1_guidelines[f], "L1")
                   for f in features if f in _l1_guidelines])
    return stages


# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------

PROVIDERS = {
    "OpenAI": {
        "base_url": None,
        "models": ["gpt-4o-mini", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-sol",
                   "gpt-5.4-mini", "gpt-5.2", "gpt-4o", "gpt-4.1"],
        "default": "gpt-4o-mini",
        "key_hint": "sk-...",
    },
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
                   "gemini-3.1-pro-preview", "gemini-2.5-flash", "gemini-2.5-pro",
                   "gemini-flash-latest"],
        "default": "gemini-3.7-flash",
        "key_hint": "AIza...",
    },
    "Anthropic Claude": {
        "sdk": "anthropic",
        "models": ["claude-opus-5", "claude-sonnet-5", "claude-sonnet-4-6",
                   "claude-haiku-4-5", "claude-opus-4-8"],
        "default": "claude-opus-5",
        "key_hint": "sk-ant-...",
    },
}


def make_client(provider, api_key):
    if PROVIDERS[provider].get("sdk") == "anthropic":
        return anthropic.Anthropic(api_key=api_key.strip())
    return OpenAI(api_key=api_key.strip(), base_url=PROVIDERS[provider]["base_url"])


def chat(client, model, messages, temperature=0.8, top_p=0.95, max_tokens=2000):
    if isinstance(client, anthropic.Anthropic):
        # Claude 4.6+ models take no temperature/top_p; adaptive thinking runs by
        # default and its tokens count toward max_tokens, so leave headroom.
        system = None
        converted = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                converted.append(m)
        kwargs = {"model": model, "max_tokens": max_tokens * 4, "messages": converted}
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        return "".join(b.text for b in response.content if b.type == "text")
    if model.startswith("gpt-5"):
        # gpt-5.x reasoning models: no max_tokens/temperature/top_p; leave
        # headroom for reasoning tokens on top of the visible answer.
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens * 4,
        )
        return response.choices[0].message.content
    if model.startswith(("gemini-3", "gemini-flash-latest")):
        # Thinking models: thoughts count toward the output token limit.
        max_tokens = max_tokens * 4
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
    except Exception as e:
        # Newer OpenAI models reject max_tokens / non-default temperature.
        if "max_tokens" in str(e) or "temperature" in str(e):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_tokens,
            )
        else:
            raise
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Transformation pipeline (chat-API port of src/framework/transformation.py)
# ---------------------------------------------------------------------------

def build_messages(feature, guideline_text, task_name, sentence):
    guideline_instruction, example = extract_guideline_examples(guideline_text, task_name)
    system_message = return_system_message(guideline_instruction)
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": example[0]["input"]},
        {"role": "assistant", "content": example[0]["output"]},
        {"role": "user", "content": f"**Original Sentence:** {sentence}"},
    ]


def strip_wrapping_quotes(candidate):
    """Drop a single pair of double quotes wrapping the whole sentence."""
    result = candidate.strip()
    if len(result) >= 2 and result[0] in '"“' and result[-1] in '"”':
        result = result[1:-1].strip()
    return result


def run_transform(req):
    """Generator of event dicts, one per pipeline step."""
    text = (req.text or "").strip()
    if not text:
        yield {"type": "error", "message": "Enter a sentence to transform."}
        return
    if req.provider not in PROVIDERS:
        yield {"type": "error", "message": f"Unknown provider: {req.provider}"}
        return
    if not (req.api_key or "").strip():
        hint = PROVIDERS[req.provider]["key_hint"]
        yield {"type": "error", "message": f"Enter your {req.provider} API key ({hint})."}
        return
    if req.variety_type == "dialect" and req.dialect not in DIALECTS:
        yield {"type": "error", "message": f"Unknown dialect: {req.dialect}"}
        return
    if req.variety_type != "dialect" and req.l1 not in L1_GRAMMARERROR:
        yield {"type": "error", "message": f"Unknown L1 language: {req.l1}"}
        return

    stages = build_guideline(req.variety_type, req.dialect, req.l1, req.cefr)
    guideline = []
    for stage in stages:
        stage = stage[:]
        if req.shuffle_rules:
            random.shuffle(stage)
        guideline.extend(stage)

    client = make_client(req.provider, req.api_key)
    sentence = re.sub(r"_{2,}", "<blank>", text)
    original = sentence
    total = len(guideline)
    applied = []
    errors = 0

    yield {"type": "start", "total": total, "model": req.model, "original": original,
           "rules": [f for f, _, _ in guideline]}

    for index, (feature, guideline_text, task_name) in enumerate(guideline):
        event = {"type": "rule", "index": index, "feature": feature, "note": ""}
        try:
            messages = build_messages(feature, guideline_text, task_name, sentence)
            response = chat(client, req.model, messages)
            candidate = strip_wrapping_quotes(
                extract_transformed_sentence(response or "")
            )

            if "no change" in candidate.lower():
                event["status"] = "nochange"
            elif req.use_judge:
                verdict = chat(
                    client, req.model,
                    [{"role": "user", "content": semantic_check(original, candidate)}],
                )
                if "no" in (verdict or "").lower():
                    sentence = candidate
                    applied.append(feature)
                    event["status"] = "applied"
                else:
                    event["status"] = "rejected"
                    event["note"] = "meaning changed"
            else:
                sentence = candidate
                applied.append(feature)
                event["status"] = "applied"
        except Exception as e:
            errors += 1
            message = str(e)
            event["status"] = "error"
            event["note"] = message[:160]
            lowered = message.lower()
            if any(k in lowered for k in ("api key", "authentication", "401", "permission")):
                yield event
                yield {"type": "error",
                       "message": f"Stopped: authentication failed. {message[:200]}"}
                return
        yield event

    final_sentence = sentence.replace("<blank>", "____")
    yield {"type": "done", "original": original.replace("<blank>", "____"),
           "transformed": final_sentence, "applied": applied, "total": total,
           "errors": errors}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

EXAMPLES = [
    "Janet's ducks lay 16 eggs per day. She eats three for breakfast every morning and bakes muffins for her friends every day with four. She sells the remainder at the farmers' market daily for $2 per fresh duck egg. How much in dollars does she make every day at the farmers' market?",
    "A robe takes 2 bolts of blue fiber and half that much white fiber. How many bolts in total does it take?",
    "The committee has not yet decided where the annual conference will be held next year.",
]

VERSION = (ROOT / "version.txt").read_text().strip()


class TransformRequest(BaseModel):
    text: str
    variety_type: str = Field("dialect", pattern="^(dialect|esl)$")
    dialect: str = list(DIALECTS)[0]
    l1: str = L1_LANGUAGES[0]
    cefr: str = CEFR_CHOICES[0]
    provider: str = "OpenAI"
    model: str = PROVIDERS["OpenAI"]["default"]
    api_key: str = ""
    shuffle_rules: bool = True
    use_judge: bool = True


app = FastAPI(title="Trans-EnV demo API", version=VERSION)

# The UI is served from a different origin (GitHub Pages).
# allow_headers="*" also covers the ngrok-skip-browser-warning header the UI sends.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
_logger.info("Backend starts up! (version: %s, CORS origins: %s)", VERSION, CORS_ORIGINS)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "trans-env-demo", "version": VERSION}


@app.get("/api/meta")
def meta():
    return {
        "version": VERSION,
        "dialects": [{"label": d, "rules": dialect_rule_count(d)} for d in DIALECTS],
        "l1_languages": L1_LANGUAGES,
        "cefr_choices": CEFR_CHOICES,
        "cefr_sample_size": CEFR_SAMPLE_SIZE,
        "providers": {
            name: {"models": p["models"], "default": p["default"], "key_hint": p["key_hint"]}
            for name, p in PROVIDERS.items()
        },
        "examples": EXAMPLES,
    }


@app.post("/api/transform")
def transform(req: TransformRequest):
    _logger.info("Transform request (type: %s, provider: %s, model: %s)",
                 req.variety_type, req.provider, req.model)

    def stream():
        for event in run_transform(req):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
