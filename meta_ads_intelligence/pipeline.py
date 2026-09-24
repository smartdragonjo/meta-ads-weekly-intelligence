from __future__ import annotations

from datetime import date
from pathlib import Path

from .csv_loader import load_ads
from .excel_report import write_report
from .history import compare_and_update, load_history, save_history


def run(input_dir: Path, reports_dir: Path, archive_dir: Path, scan_date: str | None = None, competitor_name: str = "", page_id: str = "") -> Path:
    scan_date = scan_date or date.today().isoformat()
    ads = load_ads(input_dir)
    history_path = archive_dir / "history.json"
    history = load_history(history_path)
    ads, history = compare_and_update(ads, history, scan_date)
    save_history(history_path, history)

    report_path = reports_dir / f"إعلانات_المنافسين_{scan_date}.xlsx"
    write_report(report_path, ads, scan_date, competitor_name=competitor_name, page_id=page_id)
    return report_path
