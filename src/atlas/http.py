"""A deliberately slow, identifiable HTTP client.

Every request made by this project goes through PoliteSession, which
  * sends a User-Agent naming the project,
  * waits between requests to the same host,
  * retries transient failures with back-off, and
  * can refuse URLs that a site's robots.txt disallows.
It never rotates identities, solves captchas or otherwise works around blocks.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests


class RobotsDisallowed(RuntimeError):
    """Raised when robots.txt forbids fetching a URL."""


class PoliteSession:
    def __init__(self, user_agent: str, delay: float = 1.5, timeout: float = 30,
                 retries: int = 3, sleep=time.sleep, session: requests.Session | None = None):
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self._sleep = sleep
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    @classmethod
    def from_settings(cls, settings: dict) -> PoliteSession:
        return cls(settings["user_agent"], settings["request_delay_seconds"],
                   settings["timeout_seconds"])

    def _wait(self, host: str) -> None:
        last = self._last_hit.get(host)
        if last is not None:
            remaining = self.delay - (time.monotonic() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_hit[host] = time.monotonic()

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlparse(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            parser = RobotFileParser()
            try:
                resp = self._session.get(base + "/robots.txt", timeout=self.timeout)
                if resp.status_code >= 400:
                    # No robots.txt published: nothing is disallowed by it.
                    parser.parse([])
                else:
                    parser.parse(resp.text.splitlines())
                self._robots[base] = parser
            except requests.RequestException:
                self._robots[base] = None  # unknown -> treat as not allowed
        parser = self._robots[base]
        return bool(parser and parser.can_fetch(self.user_agent, url))

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            respect_robots: bool = False) -> requests.Response:
        if respect_robots and not self.allowed_by_robots(url):
            raise RobotsDisallowed(url)
        host = urlparse(url).netloc
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self._wait(host)
            try:
                resp = self._session.get(url, params=params, headers=headers,
                                         timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"{resp.status_code} from {host}", response=resp)
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status not in (429, 500, 502, 503, 504):
                    break  # a 403/404 will not get better by retrying
                self._sleep(self.delay * (2 ** attempt))
        raise last_error  # type: ignore[misc]
