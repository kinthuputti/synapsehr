"""
llm.py - the ONE place that talks to the LLM (Google Gemini, free tier).
Everything else calls ask(). To switch provider later, only this file changes.

Uses only Python's standard library (no SDK to install, no Python-version issues).
Needs two environment variables (set them in PowerShell, never in a file you commit):
    $env:GEMINI_API_KEY="your-key"
    $env:GEMINI_MODEL="model-name"      # run check_gemini.py to see which names work for you
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://generativelanguage.googleapis.com/v1beta"
CACHE_FILE = Path("cache") / "llm_cache.json"     # saved answers, so reruns cost no quota


def _cache_load():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _cache_save(cache):
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def _key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit('GEMINI_API_KEY is not set. In PowerShell: $env:GEMINI_API_KEY="your-key"')
    return key


def _model():
    model = os.environ.get("GEMINI_MODEL")
    if not model:
        raise SystemExit("GEMINI_MODEL is not set. Run 'python check_gemini.py' to see model names, "
                         'then: $env:GEMINI_MODEL="model-name"')
    return model


def _request(url, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"x-goog-api-key": _key(), "Content-Type": "application/json"},
        method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=int(os.environ.get("GEMINI_TIMEOUT", "120"))) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_models():
    """Names of models your key can use for text generation."""
    out = _request(f"{BASE}/models?pageSize=100")
    return [m["name"].replace("models/", "") for m in out.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


def ask(prompt, json_mode=False, retries=4):
    """Send a prompt, return the model's text. Retries when the free tier says 'slow down'."""
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0}}      # 0 = as repeatable as possible
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    url = f"{BASE}/models/{_model()}:generateContent"

    # same model + same prompt -> reuse the saved answer (no API call, no quota used)
    key = hashlib.sha256(f"{_model()}|{json_mode}|{prompt}".encode("utf-8")).hexdigest()
    cache = _cache_load()
    if key in cache:
        return cache[key]

    for attempt in range(retries):
        try:
            out = _request(url, body)
            text = out["candidates"][0]["content"]["parts"][0]["text"]
            cache[key] = text                              # only successful answers are saved
            _cache_save(cache)
            return text
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))            # free-tier rate limit: wait and retry
                continue
            raw = e.read().decode("utf-8", "ignore")
            msg = raw
            try:                                           # pull out the readable part of Google's error
                err = json.loads(raw)["error"]
                msg = err.get("message", raw)
                for d in err.get("details", []):
                    if isinstance(d, dict) and "retryDelay" in d:
                        msg += f"  [Google says retry after {d['retryDelay']}]"
            except (ValueError, KeyError, TypeError):
                pass
            raise RuntimeError(f"Gemini API error {e.code}: {msg[:1500]}")
        except (TimeoutError, urllib.error.URLError) as e:   # slow model or network hiccup
            if attempt < retries - 1:
                time.sleep(3)
                continue
            raise RuntimeError(f"No answer from Gemini (timeout or network problem): {e}")
        except (KeyError, IndexError):
            raise RuntimeError("The model returned no text (empty or blocked). Try again.")
