import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.guard import DASHBOARDS, Guard, normalize

fails = 0


def check(label, ok):
    global fails
    ok = bool(ok)
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


class Clock:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# ---- the cache key
check("normalize: case, punctuation and spaces", normalize("  Compare Kohli, and RAINA?? ") == "compare kohli and raina")
check("normalize: hyphens and apostrophes", normalize("Kohli's strike-rate") == "kohli s strike rate")
check("normalize: other scripts are kept", normalize("कोहली का स्ट्राइक रेट?") == "कोहली का स्ट्राइक रेट")
check("normalize: empty", normalize(None) == "" and normalize("  !! ") == "")

# ---- rate limit per visitor
c = Clock()
g = Guard(per_minute=5, clock=c)
check("five questions in a minute are allowed", all(g.allow("a")[0] for _ in range(5)))
ok, msg = g.allow("a")
check("the sixth is refused with a wait time", (not ok) and "wait about" in msg and "seconds" in msg)
check("a refused question is not counted", g.used_today()["count"] == 5)
check("another visitor is not affected", g.allow("b")[0])
c.t += 10
ok, msg = g.allow("a")
check("still refused 10 s later, with a shorter wait", (not ok) and "51 seconds" in msg)
c.t += 51
check("allowed again after a minute", g.allow("a")[0])

c = Clock()
g = Guard(per_minute=100, per_session_day=3, clock=c)
for _ in range(3):
    g.allow("a")
ok, msg = g.allow("a")
check("per-visitor daily limit", (not ok) and "limit for one visitor" in msg and DASHBOARDS in msg)
c.t += 86401
check("the visitor limit resets after 24 hours", g.allow("a")[0])

# ---- daily cap for the whole app
c = Clock()
g = Guard(per_minute=100, per_session_day=100, daily_cap=3, clock=c)
check("cap: three questions allowed across visitors", g.allow("a")[0] and g.allow("b")[0] and g.allow("c")[0])
ok, msg = g.allow("d")
check("cap: the next visitor is refused politely", (not ok) and "limit for today" in msg and DASHBOARDS in msg)
c.t += 86400
check("cap: resets on a new UTC day", g.allow("d")[0] and g.used_today()["count"] == 1)
check("used_today reports the cap", {"day", "count", "cap"} <= set(g.used_today()) and g.used_today()["cap"] == 3)

g = Guard(per_minute=1000, per_session_day=1000, daily_cap=50)
results = []


def worker(i):
    results.append(g.allow(f"s{i}")[0])


threads = [threading.Thread(target=worker, args=(i,)) for i in range(120)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("the cap holds under concurrent use", sum(results) == 50 and g.used_today()["count"] == 50)

# ---- the answer cache
c = Clock()
g = Guard(cache_size=3, cache_ttl=100, clock=c)
g.cache_put("Compare Kohli and Raina?", {"v": 1}, version="d1")
check("cache: the same question in other wording", g.cache_get("compare   kohli and raina", "d1") == {"v": 1})
check("cache: a new data version misses", g.cache_get("compare kohli and raina", "d2") is None)
c.t += 101
check("cache: entries expire", g.cache_get("compare kohli and raina", "d1") is None)
g.cache_put("a", 1)
g.cache_put("b", 2)
g.cache_put("c", 3)
g.cache_get("a")
g.cache_put("d", 4)
check("cache: the least recently used entry goes first", g.cache_get("b") is None and g.cache_get("a") == 1 and g.cache_get("d") == 4)
g.cache_put("   ", 5)
check("cache: empty questions are not stored", g.cache_get("   ") is None)

print("\nfailures:", fails)
