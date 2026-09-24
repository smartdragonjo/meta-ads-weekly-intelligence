from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd

from .csv_loader import load_ads
from .excel_report import write_report
from .history import compare_and_update, load_history, save_history


def _json_value(value: object) -> object:
    if pd.isna(value):
        return ""
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _write_latest_json(path: Path, ads: pd.DataFrame, scan_date: str) -> None:
    records = []
    for row in ads.to_dict(orient="records"):
        records.append({
            "ad_id": _json_value(row.get("ad_id", "")),
            "page_id": _json_value(row.get("page_id", "")),
            "page_name": _json_value(row.get("competitor_name", "")),
            "ad_body": _json_value(row.get("ad_text", "")),
            "ad_title": _json_value(row.get("ad_title", "")),
            "start_date": _json_value(row.get("start_date", "")),
            "is_active": _json_value(row.get("is_active", "")),
            "format": _json_value(row.get("format", "") or row.get("ad_type", "")),
            "media_type": _json_value(row.get("media_type", "")),
            "platforms": _json_value(row.get("platforms", "")),
            "cta": _json_value(row.get("cta", "")),
            "ad_url": _json_value(row.get("ad_link", "")),
            "video_url": _json_value(row.get("video_link", "")),
            "image_url": _json_value(row.get("image_link", "")),
            "comparison_result": _json_value(row.get("comparison", "")),
            "first_seen": _json_value(row.get("first_seen", "")),
            "last_seen": _json_value(row.get("last_seen", "")),
            "times_seen": _json_value(row.get("times_seen", "")),
        })

    grouped = ads.copy()
    grouped["competitor"] = grouped["competitor_name"].replace("", "غير محدد")
    competitors = []
    for competitor, group in grouped.groupby("competitor", sort=True):
        formats = group["format"].where(group["format"] != "", group["ad_type"])
        media_types = group["media_type"].str.lower()
        type_counts = {
            "video": int((formats.str.lower().str.contains("video") | media_types.str.contains("video")).sum()),
            "image": int((formats.str.lower().str.contains("image|photo") | media_types.str.contains("image|photo")).sum()),
            "carousel": int(formats.str.lower().str.contains("carousel").sum()),
        }
        competitors.append({
            "name": str(competitor),
            "total_ads": int(len(group)),
            "total_new_ads": int((group["comparison"] == "جديد في سجلنا").sum()),
            "video_count": type_counts["video"],
            "image_count": type_counts["image"],
            "carousel_count": type_counts["carousel"],
        })

    payload = {
        "scan_date": scan_date,
        "total_ads": len(records),
        "total_new_ads": int((ads["comparison"] == "جديد في سجلنا").sum()),
        "competitors": competitors,
        "ads": records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def run(input_dir: Path, reports_dir: Path, archive_dir: Path, scan_date: str | None = None, competitor_name: str = "", page_id: str = "") -> Path:
    scan_date = scan_date or date.today().isoformat()
    ads = load_ads(input_dir)
    history_path = archive_dir / "history.json"
    history = load_history(history_path)
    ads, history = compare_and_update(ads, history, scan_date)
    if competitor_name:
        ads["competitor_name"] = competitor_name
    if page_id:
        ads["page_id"] = page_id
    save_history(history_path, history)

    report_path = reports_dir / f"إعلانات_المنافسين_{scan_date}.xlsx"
    write_report(report_path, ads, scan_date, competitor_name=competitor_name, page_id=page_id)
    _write_latest_json(reports_dir.parent / "docs" / "data" / "latest.json", ads, scan_date)
    return report_path
