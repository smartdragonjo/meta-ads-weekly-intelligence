from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


HISTORY_FIELDS = ["first_seen", "last_seen", "times_seen"]


def load_history(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def compare_and_update(ads: pd.DataFrame, history: dict[str, dict[str, object]], scan_date: str) -> tuple[pd.DataFrame, dict[str, dict[str, object]]]:
    result = ads.copy()
    comparison: list[str] = []
    first_seen: list[str] = []
    last_seen: list[str] = []
    times_seen: list[int] = []

    for ad_id in result["ad_id"].tolist():
        previous = history.get(ad_id)
        is_new = previous is None
        record = {
            "first_seen": scan_date if is_new else str(previous.get("first_seen", scan_date)),
            "last_seen": scan_date,
            "times_seen": 1 if is_new else int(previous.get("times_seen", 0)) + 1,
        }
        history[ad_id] = record
        comparison.append("جديد في سجلنا" if is_new else "موجود سابقاً")
        first_seen.append(record["first_seen"])
        last_seen.append(record["last_seen"])
        times_seen.append(record["times_seen"])

    result["comparison"] = comparison
    result["first_seen"] = first_seen
    result["last_seen"] = last_seen
    result["times_seen"] = times_seen
    return result, history


def save_history(path: Path, history: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(history, handle, ensure_ascii=False, indent=2, sort_keys=True)
