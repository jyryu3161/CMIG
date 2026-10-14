"""Checks a page makes before it starts a run the CLI is certain to refuse (Qt-free).

They read the model browse index (`models/.index/<sha256>.json`) only to name ids a model
lacks; the index is never an analysis input or a CLI argument. Without a usable index a check
says nothing and the run goes ahead — the CLI still refuses — so a check can only remove a
certain failure, never block a valid run.
"""

from __future__ import annotations

from typing import Any


def initial_exchange_ids(initial: str) -> list[str]:
    """The keys of a `--initial` string (`ID=value,…`), in order, as the CLI reads them.

    Malformed entries are skipped: the CLI reports those itself.
    """
    ids: list[str] = []
    for item in initial.split(","):
        key, separator, _value = item.partition("=")
        key = key.strip()
        if separator and key and key not in ids:
            ids.append(key)
    return ids


def missing_from_index(ids: list[str], index: dict[str, Any] | None) -> list[str] | None:
    """The ids that are not reactions of the indexed model, or None without a usable index.

    `cmig dfba` refuses an id that is not a reaction of the model, so this is exactly what it
    would refuse. An index without reactions is not a model's index and tells nothing.
    """
    if not isinstance(index, dict):
        return None
    reactions = {
        str(item["id"]) for item in index.get("reactions") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if not reactions:
        return None
    return [rid for rid in ids if rid not in reactions]
