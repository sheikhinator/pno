"""A small OpenAI-compatible chat client: Groq, Google Gemini and OpenRouter in the cloud, llama.cpp's llama-server on this
PC. All of them speak the same /chat/completions protocol, so one client serves every provider. Standard library only."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_MODELS = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS = ["openai/gpt-4o-mini", "google/gemini-2.5-flash", "anthropic/claude-sonnet-4", "openai/gpt-4.1",
                     "meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat-v3.1", "qwen/qwen3-235b-a22b"]

# Cloud providers in the order Auto tries them. URLs are looked up at call time (tests point them at a fake server).
PROVIDERS = {
    "groq": {"name": "Groq", "tag": "fast", "url": "GROQ_URL", "models": GROQ_MODELS, "hint": "gsk_…",
             "signup": "console.groq.com/keys", "note": "Free key, very fast answers."},
    "gemini": {"name": "Gemini", "tag": "Google", "url": "GEMINI_URL", "models": GEMINI_MODELS, "hint": "AIza…",
               "signup": "aistudio.google.com/apikey", "note": "Google's models; free tier available."},
    "openrouter": {"name": "OpenRouter", "tag": "any model", "url": "OPENROUTER_URL", "models": OPENROUTER_MODELS, "hint": "sk-or-…",
                   "signup": "openrouter.ai/keys", "note": "One key for GPT, Claude, Gemini, Llama, DeepSeek and more."},
}


def provider_url(pid: str) -> str:
    return globals()[PROVIDERS[pid]["url"]]
_SSL = None


class LLMError(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def ssl_ctx() -> ssl.SSLContext:
    global _SSL
    if _SSL is None:
        _SSL = ssl.create_default_context()
        try:
            import certifi
            _SSL.load_verify_locations(certifi.where())
        except Exception:
            pass
    return _SSL


_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen(req, timeout: float):
    """Open a URL; the offline AI on this PC is always reached directly, never through an office proxy."""
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in ("127.0.0.1", "localhost", "::1"):
        return _DIRECT.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx())


def _service(url: str) -> str:
    for p in PROVIDERS.values():
        if url.startswith(globals()[p["url"]]):
            return p["name"]
    return "AI service"


def _friendly(status: int, body: str, service: str = "AI service") -> str:
    try:
        err = json.loads(body)
        err = err[0] if isinstance(err, list) and err else err
        msg = (err.get("error") or {}).get("message", "") if isinstance(err, dict) else ""
    except Exception:
        msg = body[:200]
    if status in (401, 403) or (status == 400 and re.search(r"api key|API_KEY", msg or "")):
        return f"The {service} key was not accepted. Check it in Settings → AI."
    if status == 402:
        return f"{service} says the account has no credit left. Add credit or switch to another AI in Settings → AI."
    if status == 404:
        return f"{service} does not have the model chosen in Settings → AI ({msg[:120]})."
    if status == 429:
        return f"{service}'s limit was reached for now. P&O switches to the next available AI meanwhile."
    if status == 413:
        return "The question needed too much data for this model. Try narrowing it (a store or department)."
    return f"AI service error {status}: {msg}"


def chat(base_url: str, key: str, model: str, messages: list[dict], tools: list[dict] | None = None,
         timeout: float = 90, temperature: float = 0.2, max_tokens: int = 1800) -> dict:
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers=_headers(base_url, key), method="POST")
    service = _service(base_url)
    try:
        with urlopen(req, timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(_friendly(e.code, e.read().decode("utf-8", "replace"), service), e.code) from None
    except urllib.error.URLError as e:
        raise LLMError(f"Could not reach the AI service ({e.reason}). Check the internet connection.") from None
    except TimeoutError:
        raise LLMError("The AI service took too long to answer.") from None
    if isinstance(data, dict) and data.get("error"):
        raise LLMError(f"{service}: {(data['error'] or {}).get('message', 'error')}")
    choice = (data.get("choices") or [{}])[0]
    return choice.get("message") or {}


def _headers(base_url: str, key: str) -> dict:
    h = {"Content-Type": "application/json", "User-Agent": "PNO/1.0"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    if "openrouter" in base_url:
        h["HTTP-Referer"] = "https://github.com/sheikhinator/pno"
        h["X-Title"] = "P&O"
    return h


def list_models(base_url: str, key: str, timeout: float = 15) -> list[str]:
    req = urllib.request.Request(base_url.rstrip("/") + "/models", headers=_headers(base_url, key))
    try:
        with urlopen(req, timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(_friendly(e.code, e.read().decode("utf-8", "replace"), _service(base_url)), e.code) from None
    except urllib.error.URLError as e:
        raise LLMError(f"Could not reach the AI service ({e.reason}).") from None
    return sorted({str(m["id"]).removeprefix("models/") for m in data.get("data") or [] if m.get("id")})
