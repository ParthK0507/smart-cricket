import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents.llm as L

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


class Msg:
    def __init__(self, content):
        self.content = content


def ok(text):
    return lambda p: Msg(text)


def boom(msg):
    def f(p):
        raise Exception(msg)
    return f


def slow(seconds):
    def f(p):
        time.sleep(seconds)
        return Msg("late")
    return f


OVERLOAD = "503 UNAVAILABLE. This model is currently experiencing high demand."


def setup(behaviours, keys=("k1", "k2", "k3")):
    calls = []

    def build(kind, key, max_tokens, timeout):
        model = kind.split(":", 1)[1]

        def run(prompt):
            calls.append((model, key))
            return behaviours[model](prompt)
        return Fake(run)

    L.build_model, L.load_keys = build, lambda: list(keys)
    L.PER_KEY_SECONDS, L.MIN_TRY_SECONDS = 1.0, 0.1
    L.MODELS = {"fast": ["m1", "m2"], "strong": ["m1", "m2"]}
    L.MODEL_BUDGET = {"fast": 1.5, "strong": 1.5}
    L.reset_state()
    return calls


# 1) a healthy first model answers
calls = setup({"m1": ok("a"), "m2": ok("b")})
out, att = L.invoke_llm("fast", "hi")
check("the first model answers", out.content == "a" and calls == [("m1", "k1")])

# 2) an overloaded first model: the second model answers, and the keys are not rested
calls = setup({"m1": boom(OVERLOAD), "m2": ok("b")})
out, att = L.invoke_llm("strong", "hi", budget=10)
check("overloaded model: the next model answers", out.content == "b" and calls[-1] == ("m2", "k1"))
check("every key was tried on the failing model", [c for c in calls if c[0] == "m1"] == [("m1", "k1"), ("m1", "k2"), ("m1", "k3")])
check("the attempts record the overload and then the success",
      [a.get("problem") for a in att if not a["ok"]] == ["transient"] * 3 and att[-1]["ok"])
check("overload does not rest the keys", all(t <= time.monotonic() for t in L._state.values()))

# 3) the failing model is skipped for a while
calls.clear()
out, att = L.invoke_llm("strong", "hi")
check("a sick model is skipped, and the next call goes straight to the second model", out.content == "b" and calls == [("m2", "k1")])
L._sick["m1"] = time.monotonic() - 1
calls.clear()
L.invoke_llm("strong", "hi")
check("a model is tried again after its rest", calls[0][0] == "m1")

# 4) a slow first model
calls = setup({"m1": slow(3), "m2": ok("b")})
t0 = time.monotonic()
out, att = L.invoke_llm("fast", "hi", budget=10)
check("a slow model times out and the next one answers", out.content == "b" and att[0]["problem"] == "timeout"
      and time.monotonic() - t0 < 4)

# 5) both models fail
calls = setup({"m1": boom(OVERLOAD), "m2": boom(OVERLOAD)})
try:
    L.invoke_llm("strong", "hi", budget=10)
    check("both models failing raises LLMUnavailable", False)
except L.LLMUnavailable as e:
    check("both models failing raises LLMUnavailable", e.reason == "all_failed" and len(e.attempts) == 6 and str(e) == L.USER_MESSAGE)
t0 = time.monotonic()
try:
    L.invoke_llm("strong", "hi", budget=10)
except L.LLMUnavailable as e:
    check("then the next call fails fast, without waiting", time.monotonic() - t0 < 0.3 and e.reason == "no_time_or_all_cooling_down")

# 6) an unusable answer is not an availability problem
calls = setup({"m1": boom("ValidationError: schema mismatch"), "m2": ok("b")})
try:
    L.invoke_llm("fast", "hi")
    check("an unusable answer raises LLMError", False)
except L.LLMError:
    check("an unusable answer raises LLMError and does not try the next model", calls == [("m1", "k1")])

# 7) quota is still a problem of the key
calls = setup({"m1": boom("429 RESOURCE_EXHAUSTED quota exceeded"), "m2": ok("b")})
out, att = L.invoke_llm("fast", "hi", budget=10)
check("quota rests the key and the next model answers", out.content == "b" and L._qstate[(0, "m1")] > time.monotonic() + 30)

# 8) no keys, reset, explicit models, unknown jobs
setup({"m1": ok("a"), "m2": ok("b")}, keys=())
try:
    L.invoke_llm("fast", "hi")
    check("no keys", False)
except L.LLMUnavailable as e:
    check("no keys is reported as such", e.reason == "no_keys")
calls = setup({"m1": boom(OVERLOAD), "m2": ok("b")})
L.invoke_llm("fast", "hi", budget=10)
L.reset_state()
check("reset_state empties every rest table", not L._sick and not L._state and not L._qstate)
calls.clear()
L.invoke_llm("fast", "hi")
check("after a reset the first model is tried again", calls[0][0] == "m1")
calls = setup({"m1": ok("a"), "m2": ok("b")})
out, att = L.invoke_llm("fast:m2", "hi")
check("a named model is used directly", out.content == "b" and calls == [("m2", "k1")])


# 9) quota belongs to a model, so another model on the same keys still works
calls = setup({"m1": boom("429 RESOURCE_EXHAUSTED quota exceeded"), "m2": ok("b")})
L.invoke_llm("fast", "hi", budget=10)
calls.clear()
out, att = L.invoke_llm("strong", "hi", budget=10)
check("quota on one model does not block another model on the same keys", out.content == "b" and calls == [("m2", "k1")])

# 10) failed attempts carry an error text without any key
calls = setup({"m1": boom("503 UNAVAILABLE for key k1"), "m2": ok("b")})
out, att = L.invoke_llm("fast", "hi", budget=10)
errs = [a["error"] for a in att if not a["ok"]]
check("failed attempts record the error text, with keys removed", errs and all("k1" not in e and "[key]" in e for e in errs))


# 11) a rejected request is a request problem; a missing model is skipped for a long time
check("classify: a 400 INVALID_ARGUMENT is a request problem",
      L.classify(Exception("Error calling model 'x' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. maxOutputTokens 1500 exceeds")) == "other")
check("classify: numbers inside other numbers are not status codes", L.classify(Exception("tokens 1500 and 14003 and 4500")) == "other")
check("classify: a bad API key is still an auth problem", L.classify(Exception("400 API key not valid. Please pass a valid API key.")) == "auth")
check("classify: a retired model is a model problem", L.classify(Exception("404 NOT_FOUND. This model is no longer available to new users")) == "model")
check("classify: 503 and 504 are still transient", L.classify(Exception("503 UNAVAILABLE")) == "transient" and L.classify(Exception("504 DEADLINE_EXCEEDED")) == "transient")

calls = setup({"m1": boom("400 INVALID_ARGUMENT request is malformed"), "m2": ok("b")})
try:
    L.invoke_llm("strong", "hi", budget=10)
    check("an invalid request raises LLMError", False)
except L.LLMError as e:
    check("an invalid request raises LLMError at once and rests nothing",
          calls == [("m1", "k1")] and not L._sick and not L._state and "400" in str(e))

calls = setup({"m1": boom("404 NOT_FOUND no longer available"), "m2": ok("b")})
out, att = L.invoke_llm("strong", "hi", budget=10)
check("a missing model is tried once, then the next model answers", out.content == "b" and [c for c in calls if c[0] == "m1"] == [("m1", "k1")])
check("a missing model is skipped for about an hour and the keys are not rested", L._sick["m1"] > time.monotonic() + 3000 and not L._state)

print("\nfailures:", fails)
