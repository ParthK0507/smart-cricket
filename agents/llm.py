"""Gemini access with key failover and a time budget.

Keys are tried in order. A key that hits its quota, is rejected, or is slow gets a cooldown and the next key is used.
If no key answers within the budget, LLMUnavailable is raised and the app sends the user to the dashboard pages.
Keys are never printed, logged or returned.
"""
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Model names change often: list what your keys can use and edit only these two lines.
FAST_MODEL = "gemini-3.5-flash-lite"       # understanding questions: quick and cheap
STRONG_MODEL = "gemini-3.6-flash"     # writing the final answer (a pro model gives better prose)

# Each job tries its models in order. A model that is overloaded or slow is skipped for a while.
# To use a larger model for answers when demand is calm, put it first in "strong".
MODELS = {"fast": ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
          "strong": ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]}
MODEL_BUDGET = {"fast": 10.0, "strong": 11.0}     # longest one model may take before the next one is tried
SICK_SECONDS = 45                               # how long a model that failed with overload or timeouts is skipped
_sick = {}

PER_KEY_SECONDS = 11.0                # longest we wait on one key
CLIENT_TIMEOUT = 30.0                 # what the client may wait; our own wait enforces the real limit
MIN_TRY_SECONDS = 2.0                 # do not start another key with less time than this left
COOLDOWN = {"quota": 65, "auth": 3600, "transient": 0, "model": 0}   # overload belongs to the model, not the key      # seconds a key is skipped after a failure

USER_MESSAGE = ("The AI assistant is busy or slow right now. You can get the same numbers from the dashboard pages "
                "in the sidebar: Player profile, Compare, Career timeline, Leaderboards, Matchups and Match predictor.")


class LLMUnavailable(Exception):
    """No key answered in time. str(error) is safe to show to users."""

    def __init__(self, reason, attempts=None):
        super().__init__(USER_MESSAGE)
        self.reason, self.attempts = reason, attempts or []


class LLMError(Exception):
    """The model answered, but not in a usable form (a bad structured answer, for example). Not a key problem."""


_state = {}                           # key index -> time.monotonic() until which the key is skipped
_qstate = {}                          # (key index, model) -> rest until: quota is per model, not per key
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=12)


def reset_state():
    with _lock:
        _state.clear()
        _qstate.clear()
        _sick.clear()


def _secret(name):
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:                              # on Streamlit Cloud the keys live in st.secrets
        import streamlit as st
        v = st.secrets[name]
        return str(v).strip() if v else None
    except Exception:
        return None


def load_keys():
    keys = []
    for name in ("GOOGLE_API_KEY_1", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        v = _secret(name)
        if v and v not in keys:
            keys.append(v)
    return keys[:5]


def classify(exc):
    """quota / auth / model / transient: a problem with the key, the model or the service, so another key or model
    may work. other: the request itself was rejected or the answer was unusable, so trying elsewhere will not help."""
    text = f"{type(exc).__name__} {exc}".lower()
    codes = set(re.findall(r"(?<![\w.])([45]\d\d)(?![\w.])", text))
    if "429" in codes or any(s in text for s in ("resource_exhausted", "resourceexhausted", "quota", "rate limit", "rate_limit")):
        return "quota"
    if codes & {"401", "403"} or any(s in text for s in ("api key not valid", "api_key_invalid", "permission_denied",
                                                       "permissiondenied", "unauthenticated")):
        return "auth"
    if "404" in codes or "not_found" in text or "no longer available" in text:
        return "model"
    if "400" in codes or "invalid_argument" in text:
        return "other"
    if isinstance(exc, TimeoutError) or codes & {"408", "500", "502", "503", "504"} or any(
            s in text for s in ("timeout", "timed out", "deadline", "unavailable", "overloaded", "connection")):
        return "transient"
    return "other"


def _cool(i, kind, model=None):
    with _lock:
        if kind == "quota" and model:
            _qstate[(i, model)] = time.monotonic() + COOLDOWN["quota"]
        elif COOLDOWN[kind] > 0:
            _state[i] = time.monotonic() + COOLDOWN[kind]


def status():
    """Safe to show on an admin page: how many keys exist and how many are cooling down. Never the keys."""
    now = time.monotonic()
    with _lock:
        return {"keys": len(load_keys()), "cooling_down": sum(1 for t in list(_state.values()) + list(_qstate.values()) if t > now)}


def build_model(kind, key, max_tokens, timeout):
    from langchain_google_genai import ChatGoogleGenerativeAI
    if ":" in kind:                                   # "fast:model-name" picks one model
        kind, model = kind.split(":", 1)
    else:
        model = FAST_MODEL if kind == "fast" else STRONG_MODEL
    # Gemini 2.x: temperature 0 for repeatable routing. Gemini 3+: keep Google's default (1.0), as Google advises.
    base = {"model": model, "max_output_tokens": max_tokens}
    if model.startswith("gemini-2"):
        base["temperature"] = 0
    last = None
    for key_arg in ("api_key", "google_api_key"):                 # the argument name differs between versions
        for opts in ({"timeout": max(timeout, CLIENT_TIMEOUT), "max_retries": 0}, {}):
            try:
                return ChatGoogleGenerativeAI(**base, **{key_arg: key}, **opts)
            except Exception as e:
                last = e
    raise RuntimeError(f"could not create the Gemini client: {type(last).__name__}")


def as_text(message):
    """The text of a model reply (newer Gemini models may return a list of content parts)."""
    c = getattr(message, "content", message)
    if isinstance(c, str):
        return c
    return "".join(p if isinstance(p, str) else p.get("text", "") for p in c)


def _call(kind, key, prompt, schema, max_tokens, timeout):
    model = build_model(kind, key, max_tokens, timeout)
    if schema is not None:
        model = model.with_structured_output(schema)
    return model.invoke(prompt)


def _scrub(text, keys):
    for k in keys:
        text = text.replace(k, "[key]")
    return text


def _invoke_one(kind, prompt, schema=None, budget=20.0, max_tokens=1024):
    """Ask the model, trying each key in turn within `budget` seconds.
    Returns (result, attempts). Raises LLMUnavailable when no key answers in time, LLMError for unusable answers."""
    keys = load_keys()
    if not keys:
        raise LLMUnavailable("no_keys")
    deadline = time.monotonic() + budget
    now = time.monotonic()
    model_name = kind.split(":", 1)[1] if ":" in kind else (FAST_MODEL if kind == "fast" else STRONG_MODEL)
    with _lock:
        order = [i for i in range(len(keys)) if _state.get(i, 0) <= now and _qstate.get((i, model_name), 0) <= now]
    attempts = []
    for i in order:
        remaining = deadline - time.monotonic()
        if remaining < MIN_TRY_SECONDS:
            break
        per_call = min(remaining, PER_KEY_SECONDS)
        t0 = time.monotonic()
        fut = _pool.submit(_call, kind, keys[i], prompt, schema, max_tokens, per_call)
        try:
            out = fut.result(timeout=per_call)
            attempts.append({"key": i + 1, "ok": True, "seconds": round(time.monotonic() - t0, 2)})
            return out, attempts
        except FuturesTimeout:
            problem = "transient"
            attempts.append({"key": i + 1, "ok": False, "problem": "timeout", "seconds": round(time.monotonic() - t0, 2)})
        except Exception as e:
            problem = classify(e)
            if problem == "other":
                raise LLMError(_scrub(f"{type(e).__name__}: {str(e)[:200]}", keys)) from e
            attempts.append({"key": i + 1, "ok": False, "problem": problem, "seconds": round(time.monotonic() - t0, 2),
                             "error": _scrub(str(e)[:110], keys)})
        _cool(i, problem, model_name)
        if problem == "model":
            break                  # every key would get the same answer from a missing model
    raise LLMUnavailable("all_failed" if attempts else "no_time_or_all_cooling_down", attempts)


def invoke_llm(kind, prompt, schema=None, budget=20.0, max_tokens=1024):
    """Ask the model for a job ("fast" or "strong"): each model in the job's list is tried in turn, and a model that
    is overloaded or slow is skipped for a while. Returns (result, attempts). Raises LLMUnavailable or LLMError."""
    if ":" in kind or kind not in MODELS:
        return _invoke_one(kind, prompt, schema=schema, budget=budget, max_tokens=max_tokens)
    deadline = time.monotonic() + budget
    attempts = []
    for model in MODELS[kind]:
        now = time.monotonic()
        with _lock:
            sick_until = _sick.get(model, 0)
        left = deadline - now
        if sick_until > now:
            continue
        if left < MIN_TRY_SECONDS:
            break
        try:
            out, att = _invoke_one(f"{kind}:{model}", prompt, schema=schema,
                                   budget=min(left, MODEL_BUDGET[kind]), max_tokens=max_tokens)
            return out, attempts + att
        except LLMUnavailable as e:
            if e.reason == "no_keys":
                raise
            attempts += e.attempts
            problems = {a.get("problem") for a in e.attempts}
            if problems & {"timeout", "transient", "model"}:
                with _lock:
                    _sick[model] = time.monotonic() + (3600 if "model" in problems else SICK_SECONDS)
    raise LLMUnavailable("all_failed" if attempts else "no_time_or_all_cooling_down", attempts)
