"""A small OpenAI-compatible chat client (Groq in the cloud, llama.cpp's llama-server on this PC). Standard library only."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_MODELS = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
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


def _friendly(status: int, body: str) -> str:
    try:
        msg = json.loads(body).get("error", {}).get("message", "")
    except Exception:
        msg = body[:200]
    if status == 401:
        return "The Groq key was not accepted. Check it in Settings → AI."
    if status == 429:
        return "Groq's free limit was reached for now. PNO will answer with the offline / built-in assistant meanwhile."
    if status == 413:
        return "The question needed too much data for this model. Try narrowing it (a store or department)."
    return f"AI service error {status}: {msg}"


def chat(base_url: str, key: str, model: str, messages: list[dict], tools: list[dict] | None = None,
         timeout: float = 90, temperature: float = 0.2, max_tokens: int = 1800) -> dict:
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    headers = {"Content-Type": "application/json", "User-Agent": "PNO/1.0"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx()) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(_friendly(e.code, e.read().decode("utf-8", "replace")), e.code) from None
    except urllib.error.URLError as e:
        raise LLMError(f"Could not reach the AI service ({e.reason}). Check the internet connection.") from None
    except TimeoutError:
        raise LLMError("The AI service took too long to answer.") from None
    choice = (data.get("choices") or [{}])[0]
    return choice.get("message") or {}


def list_models(base_url: str, key: str, timeout: float = 15) -> list[str]:
    req = urllib.request.Request(base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}", "User-Agent": "PNO/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx()) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(_friendly(e.code, e.read().decode("utf-8", "replace")), e.code) from None
    except urllib.error.URLError as e:
        raise LLMError(f"Could not reach the AI service ({e.reason}).") from None
    return sorted(m["id"] for m in data.get("data") or [])
