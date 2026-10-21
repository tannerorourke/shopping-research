"""
Persistent Chromium context with the Capital One Shopping extension loaded.
C1Browser starts lazily on first use, patches fetch inside the extension
service worker to record JSON responses, and shuts itself down when idle.
c1.check owns one instance and drains hits() after each page load.
"""
import asyncio
import os
import time

from playwright.async_api import async_playwright

from c1 import settings as c1_settings

_INTERCEPT_JS = """
() => {
  if (self.__bp_patched) return;
  const orig = self.fetch;
  self.__bp_hits = [];
  self.fetch = async (...args) => {
    const res = await orig(...args);
    try {
      const url = typeof args[0] === 'string' ? args[0] : args[0].url;
      const data = await res.clone().json().catch(() => null);
      self.__bp_hits.push({url, status: res.status, data});
    } catch (e) {}
    return res;
  };
  self.__bp_patched = true;
}
"""

_DRAIN_JS = """
() => {
  if (!self.__bp_patched) return null;
  const hits = self.__bp_hits;
  self.__bp_hits = [];
  return hits;
}
"""


class C1Browser:
    def __init__(self, s):
        self.s = s
        self._pw = None
        self._ctx = None
        self._sw = None
        self._last_used = 0.0
        self._calls = 0

    async def context(self):
        if self._ctx is None:
            self._pw = await async_playwright().start()
            ext = c1_settings.extension_path(self.s)
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=os.path.expanduser(self.s.profile_dir),
                channel="chromium",  # -- required for extensions in headless
                headless=self.s.headless,
                args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}"],
            )
            self._sw = (self._ctx.service_workers[0] if self._ctx.service_workers
                        else await self._ctx.wait_for_event("serviceworker"))
            await self._install_intercept()
            asyncio.create_task(self._idle_reaper())
        self._last_used = time.time()
        return self._ctx

    async def _install_intercept(self):
        await self._sw.evaluate(_INTERCEPT_JS)

    async def hits(self) -> list[dict]:
        # -- MV3 suspends the worker and drops the patch; a null drain means re-install
        drained = await self._sw.evaluate(_DRAIN_JS)
        if drained is None:
            await self._install_intercept()
            return []
        return drained

    async def _idle_reaper(self):
        while self._ctx is not None:
            await asyncio.sleep(15)
            if self._ctx is not None and time.time() - self._last_used > self.s.idle_close_seconds:
                await self.close()

    async def close(self):
        ctx, pw = self._ctx, self._pw
        self._ctx = self._pw = self._sw = None
        self._calls = 0
        if ctx is not None:
            await ctx.close()
        if pw is not None:
            await pw.stop()
