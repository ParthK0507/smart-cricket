import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents.llm as L

L.MODELS = {"fast": ["only"], "strong": ["only"]}      # one model, so these tests see one model's attempts

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


class Fake:
    def __init__(self, fn):
        self.fn = fn

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.fn(prompt)


def setup(behaviours, keys=("k1", "k2", "k3"), per_key=1.0, min_try=0.1):
    calls = []

    def build(kind, key, max_tokens, timeout):
        def run(prompt):
            calls.append(key)
            return behaviours[key](prompt)
        return Fake(run)

    L.build_model = build
    L.load_keys = lambda: list(keys)
    L.PER_KEY_SECONDS, L.MIN_TRY_SECONDS = per_key, min_try
    L.reset_state()
    return calls


def ok(text):
    return lambda p: text


def boom(msg):
    def f(p):
        raise Exception(msg)
    return f


def slow(seconds, text="late"):
    def f(p):
        time.sleep(seconds)
        return text
    return f


QUOTA, AUTH = "429 RESOURCE_EXHAUSTED quota exceeded", "400 API key not valid. Please pass a valid API key."

# 1) the first key answers: nothing else is touched
calls = setup({"k1": ok("a"), "k2": ok("b"), "k3": ok("c")})
out, att = L.invoke_llm("fast", "hi")
check("first key answers", out == "a" and att[0]["key"] == 1 and calls == ["k1"])

# 2) quota: key 2 answers, and key 1 is skipped on the next question
calls = setup({"k1": boom(QUOTA), "k2": ok("b"), "k3": ok("c")})
out, att = L.invoke_llm("fast", "hi")
check("quota error moves on to key 2", out == "b" and [a["key"] for a in att] == [1, 2] and att[0]["problem"] == "quota")
out2, att2 = L.invoke_llm("fast", "hi")
check("key 1 is skipped while it rests", out2 == "b" and [a["key"] for a in att2] == [2] and calls == ["k1", "k2", "k2"])

# 3) slow key: a timeout moves on, quickly
calls = setup({"k1": slow(1.5), "k2": ok("b"), "k3": ok("c")}, per_key=0.4)
t0 = time.monotonic()
out, att = L.invoke_llm("fast", "hi", budget=5)
check("slow key times out and key 2 answers", out == "b" and att[0]["problem"] == "timeout" and time.monotonic() - t0 < 1.4)

# 4) rejected key rests for an hour
calls = setup({"k1": boom(AUTH), "k2": ok("b"), "k3": ok("c")})
out, att = L.invoke_llm("fast", "hi")
check("rejected key: key 2 answers", out == "b" and att[0]["problem"] == "auth")
check("rejected key rests for about an hour", L._state[0] - time.monotonic() > 3000)

# 5) every key fails: a polite error, never a crash
calls = setup({"k1": boom(QUOTA), "k2": boom(QUOTA), "k3": boom(QUOTA)})
try:
    L.invoke_llm("fast", "hi")
    check("all keys failing raises LLMUnavailable", False)
except L.LLMUnavailable as e:
    check("all keys failing raises LLMUnavailable", e.reason == "all_failed" and len(e.attempts) == 3)
    check("the message is the friendly one", str(e) == L.USER_MESSAGE and "dashboard" in str(e))

# 6) all keys resting: fail at once instead of making the user wait
n, t0 = len(calls), time.monotonic()
try:
    L.invoke_llm("fast", "hi")
    check("all keys resting fails fast", False)
except L.LLMUnavailable as e:
    check("all keys resting fails fast", time.monotonic() - t0 < 0.3 and len(calls) == n
          and e.reason == "no_time_or_all_cooling_down")

# 7) an unusable answer is not a key problem: no rotation
calls = setup({"k1": boom("ValidationError: schema mismatch"), "k2": ok("b"), "k3": ok("c")})
try:
    L.invoke_llm("fast", "hi")
    check("unusable answer raises LLMError", False)
except L.LLMError:
    check("unusable answer raises LLMError and does not rotate keys", calls == ["k1"])

# 8) the time budget is respected
calls = setup({"k1": slow(1.5), "k2": slow(1.5), "k3": slow(1.5)}, per_key=0.6)
t0 = time.monotonic()
try:
    L.invoke_llm("fast", "hi", budget=1.0)
    check("budget is respected", False)
except L.LLMUnavailable as e:
    check("budget is respected", time.monotonic() - t0 < 1.5 and len(e.attempts) == 2)

# 9) no keys at all
setup({}, keys=())
try:
    L.invoke_llm("fast", "hi")
    check("no keys configured", False)
except L.LLMUnavailable as e:
    check("no keys configured", e.reason == "no_keys")

# 10) a rested key is used again
B = {"k1": boom(QUOTA), "k2": ok("b"), "k3": ok("c")}
calls = setup(B)
L.invoke_llm("fast", "hi")
B["k1"] = ok("a")
L._state.clear()
L._qstate.clear()
out, att = L.invoke_llm("fast", "hi")
check("a key is used again after its rest", out == "a")

# 11) keys never leak
calls = setup({"k1": boom("ValidationError with key k1 inside"), "k2": ok("b"), "k3": ok("c")})
try:
    L.invoke_llm("fast", "hi")
except L.LLMError as e:
    check("keys are scrubbed from error messages", "k1" not in str(e))
calls = setup({"k1": boom(QUOTA), "k2": ok("b"), "k3": ok("c")})
out, att = L.invoke_llm("fast", "hi")
check("keys never appear in attempts or the user message", "k1" not in str(att) and "k1" not in L.USER_MESSAGE)

# 12) how errors are classified
for text, want in [("429 Resource has been exhausted", "quota"), ("403 PERMISSION_DENIED", "auth"),
                   (AUTH, "auth"), ("503 The model is overloaded", "transient"), ("500 internal error", "transient")]:
    check(f"classify: {text[:40]}", L.classify(Exception(text)) == want)
check("classify: TimeoutError", L.classify(TimeoutError()) == "transient")
check("classify: a bad schema is not a key problem", L.classify(ValueError("bad schema")) == "other")

print("\nfailures:", fails)
