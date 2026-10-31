"""Two Gemma 4 backends behind one call.

- gemini: gemma-4-31b-it through the Gemini API (needs GEMINI_API_KEY)
- ollama: gemma4:e4b on this machine; nothing leaves the laptop

Every successful response is cached by a hash of (backend, model, prompt, image).
With KASSZA_REPLAY=1 only the cache is used, so the demo survives bad wifi.
"""
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx

CACHE = Path(__file__).resolve().parent.parent / "cache"
CACHE.mkdir(exist_ok=True)

_backend = os.getenv("KASSZA_BACKEND", "gemini")


def get_backend() -> str:
    return _backend


def set_backend(name: str) -> None:
    global _backend
    if name not in ("gemini", "ollama"):
        raise ValueError(name)
    _backend = name


def model_name(backend: str | None = None) -> str:
    backend = backend or _backend
    if backend == "ollama":
        return os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    return os.getenv("GEMINI_MODEL", "gemma-4-31b-it")


def _key(backend: str, prompt: str, image: bytes | None) -> str:
    h = hashlib.sha256(f"{backend}|{model_name(backend)}|{prompt}".encode())
    if image:
        h.update(image)
    return h.hexdigest()[:24]


def _gemini(prompt: str, image: bytes | None, mime: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set (put it in .env)")
    parts = [{"text": prompt}]
    if image:
        parts.insert(0, {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name('gemini')}:generateContent"
    r = httpx.post(url, headers={"x-goog-api-key": key},
                   json={"contents": [{"role": "user", "parts": parts}],
                         "generationConfig": {"temperature": 0}},
                   timeout=120)
    r.raise_for_status()
    cand = r.json()["candidates"][0]["content"]["parts"]
    # Thinking models may return thought parts first; keep the visible answer.
    return "".join(p.get("text", "") for p in cand if not p.get("thought"))


def _ollama(prompt: str, image: bytes | None, mime: str) -> str:
    msg = {"role": "user", "content": prompt}
    if image:
        msg["images"] = [base64.b64encode(image).decode()]
    r = httpx.post(f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/chat",
                   json={"model": model_name("ollama"), "messages": [msg], "stream": False,
                         "format": "json", "options": {"temperature": 0}},
                   timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"]


def generate(prompt: str, image: bytes | None = None, mime: str = "image/jpeg",
             backend: str | None = None) -> dict:
    """Returns {text, backend, model, seconds, cached}."""
    backend = backend or _backend
    key = _key(backend, prompt, image)
    path = CACHE / f"{key}.json"
    if path.exists():
        hit = json.loads(path.read_text(encoding="utf-8"))
        return {**hit, "cached": True}
    if os.getenv("KASSZA_REPLAY") == "1":
        raise RuntimeError("Replay mode: no cached response for this input")
    t = time.perf_counter()
    text = (_ollama if backend == "ollama" else _gemini)(prompt, image, mime)
    out = {"text": text, "backend": backend, "model": model_name(backend),
           "seconds": round(time.perf_counter() - t, 1)}
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {**out, "cached": False}


def parse_json(text: str):
    """Models sometimes wrap JSON in ``` fences or add a sentence; take the JSON body."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("No JSON in model output")
    return json.loads(text[start:text.rfind("}" if text[start] == "{" else "]") + 1])
