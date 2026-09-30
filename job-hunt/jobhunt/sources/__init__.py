"""Source adapter registry.

Every adapter exposes:
    fetch(entry: dict) -> list[Job]        cheap list pass, no descriptions
    hydrate(job: Job) -> str               optional; fetches the JD text

`entry` is one record from config/companies.yml.
"""

from __future__ import annotations

from typing import Callable, Protocol

from ..models import Job


class Adapter(Protocol):
    def fetch(self, entry: dict) -> list[Job]: ...


_REGISTRY: dict[str, object] = {}


def register(name: str, module: object) -> None:
    _REGISTRY[name] = module


def get(name: str) -> object | None:
    return _REGISTRY.get(name)


def names() -> list[str]:
    return sorted(_REGISTRY)


def fetch(entry: dict) -> list[Job]:
    module = _REGISTRY.get(entry["source"])
    if module is None:
        raise KeyError(f"no adapter registered for source {entry['source']!r}")
    return module.fetch(entry)


def hydrate(job: Job) -> str:
    """Fetch full JD text for a job, if its adapter supports it."""
    module = _REGISTRY.get(job.source)
    fn: Callable[[Job], str] | None = getattr(module, "hydrate", None)
    if fn is None:
        return job.description
    try:
        return fn(job) or job.description
    except Exception:  # noqa: BLE001 - one bad JD must not kill the run
        return job.description


from . import (  # noqa: E402
    aggregator, amazon, ashby, greenhouse, lever, oracle, smartrecruiters,
    workday,
)

for _mod in (aggregator, amazon, ashby, greenhouse, lever, oracle,
             smartrecruiters, workday):
    register(_mod.NAME, _mod)
