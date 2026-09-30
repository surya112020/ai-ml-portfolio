"""One shared HTTP session: real UA, retries, and polite pacing.

Every adapter goes through here so rate-limit handling and the certifi trust
store are configured in exactly one place. (The system python3 on this Mac has
no root certs — requests bundles certifi, which is why we use it everywhere.)
"""

from __future__ import annotations

import logging
import random
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        sess = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        sess.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        _session = sess
    return _session


def get_json(url: str, **kwargs) -> dict | list | None:
    return _json("GET", url, **kwargs)


def post_json(url: str, payload: dict, **kwargs) -> dict | list | None:
    return _json("POST", url, json=payload, **kwargs)


def _json(method: str, url: str, **kwargs) -> dict | list | None:
    kwargs.setdefault("timeout", 30)
    headers = kwargs.pop("headers", None)
    try:
        resp = session().request(method, url, headers=headers, **kwargs)
    except requests.RequestException as exc:
        log.warning("%s %s failed: %s", method, url, exc)
        return None
    if resp.status_code != 200:
        log.warning("%s %s -> HTTP %s", method, url, resp.status_code)
        return None
    try:
        return resp.json()
    except ValueError:
        log.warning("%s %s -> non-JSON body", method, url)
        return None


def pace(base: float = 0.25) -> None:
    """Small jittered pause between paged requests to the same host."""
    time.sleep(base + random.random() * base)
