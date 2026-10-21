"""
SerpApi monthly budget and response cache, persisted at ~/.best-price/serpapi_budget.json.

The counter resets when the calendar month changes. can_spend() is the hard
stop the server checks before every SerpApi call; past monthly_budget the call
is refused and reported as 'quota_exhausted'. Cache entries expire after
cache_ttl_hours so a repeated query within a session costs nothing.
"""
import json
import time
from datetime import datetime, timezone

import settings as settings_mod


class SerpApiBudget:
    def __init__(self):
        self.reload()

    def reload(self):
        s = settings_mod.current().serpapi
        self.key = s.api_key
        self.limit = s.monthly_budget
        self.ttl = s.cache_ttl_hours * 3600
        self.path = settings_mod.STATE_DIR / "serpapi_budget.json"
        self._state = self._read()

    def _read(self) -> dict:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        if self.path.exists():
            state = json.loads(self.path.read_text())
            if state.get("month") == month:
                return state
        return {"month": month, "spent": 0, "cache": {}}

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state))

    @property
    def spent(self) -> int:
        return self._state["spent"]

    @property
    def remaining(self) -> int:
        return max(self.limit - self.spent, 0)

    def can_spend(self) -> bool:
        return self.remaining > 0

    def spend(self):
        self._state["spent"] += 1
        self._write()

    @staticmethod
    def _cache_key(key) -> str:
        return json.dumps(key, sort_keys=True, default=str)

    def cache_get(self, key):
        entry = self._state["cache"].get(self._cache_key(key))
        if entry and time.time() - entry["at"] < self.ttl:
            return entry["data"]
        return None

    def cache_put(self, key, data):
        cache = self._state["cache"]
        cache[self._cache_key(key)] = {"at": time.time(), "data": data}
        # -- drop expired entries so the file never grows past one month of queries
        for k in [k for k, e in cache.items() if time.time() - e["at"] >= self.ttl]:
            del cache[k]
        self._write()


serpapi_budget = SerpApiBudget()
