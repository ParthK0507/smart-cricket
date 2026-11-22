"""Safeguards for the Ask page: a rate limit per visitor, a daily cap shared by all visitors, and an answer cache.
State lives in the running app and resets when the host restarts, so it complements spending limits on the keys
rather than replacing them."""
import os
import string
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone

DASHBOARDS = ("You can get the same numbers from the dashboard pages in the sidebar: Player profile, Compare, "
              "Career timeline, Leaderboards, Matchups and Match predictor.")
_PUNCT = str.maketrans({c: " " for c in string.punctuation})


def normalize(question):
    """Cache key text: lower case, ASCII punctuation removed, spaces collapsed. Other scripts are left untouched."""
    return " ".join(str(question or "").lower().translate(_PUNCT).split())


def _day(now):
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")


class Guard:
    def __init__(self, per_minute=5, per_session_day=40, daily_cap=300, cache_size=300, cache_ttl=86400,
                 clock=time.time):
        self.per_minute, self.per_session_day, self.daily_cap = per_minute, per_session_day, daily_cap
        self.cache_size, self.cache_ttl, self.clock = cache_size, cache_ttl, clock
        self._lock = threading.Lock()
        self._recent = {}              # visitor -> timestamps of the last 24 hours
        self._day, self._count = None, 0
        self._cache = OrderedDict()    # (question, data version) -> (time stored, value)

    def allow(self, session_id):
        """Call before answering a question that needs the model. Returns (ok, message).
        A question is counted only when it is allowed."""
        now = self.clock()
        with self._lock:
            day = _day(now)
            if day != self._day:
                self._day, self._count = day, 0
            if len(self._recent) > 2000:                    # forget visitors who have gone away
                for sid in list(self._recent):
                    dq = self._recent[sid]
                    while dq and now - dq[0] > 86400:
                        dq.popleft()
                    if not dq:
                        del self._recent[sid]
            q = self._recent.setdefault(session_id, deque())
            while q and now - q[0] > 86400:
                q.popleft()
            last_minute = [t for t in q if now - t < 60]
            if len(last_minute) >= self.per_minute:
                wait = int(60 - (now - last_minute[0])) + 1
                return False, f"You are asking quickly. Please wait about {wait} seconds and try again."
            if len(q) >= self.per_session_day:
                return False, "You have reached today's question limit for one visitor. " + DASHBOARDS
            if self._count >= self.daily_cap:
                return False, "The AI assistant has reached its limit for today. " + DASHBOARDS
            q.append(now)
            self._count += 1
            return True, None

    def used_today(self):
        with self._lock:
            return {"day": self._day, "count": self._count, "cap": self.daily_cap}

    def cache_get(self, question, version=""):
        key = (normalize(question), version)
        if not key[0]:
            return None
        now = self.clock()
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            if now - item[0] > self.cache_ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return item[1]

    def cache_put(self, question, value, version=""):
        key = (normalize(question), version)
        if not key[0]:
            return
        with self._lock:
            self._cache[key] = (self.clock(), value)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)


def _setting(name, default):
    """Read a limit from the environment (Streamlit passes top-level secrets that way), so it can change without a redeploy."""
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


GUARD = Guard(per_minute=_setting("ASK_PER_MINUTE", 5), per_session_day=_setting("ASK_PER_VISITOR_DAY", 40),
              daily_cap=_setting("ASK_DAILY_CAP", 150))
