from __future__ import annotations

import argparse
from pathlib import Path

from meta_ads_intelligence.pipeline import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="إنشاء تقرير Meta Ads Weekly Intelligence")
    parser.add_argument("--input", type=Path, required=True, help="مجلد CSV الخاص بالفحص")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    parser.add_argument("--date", dest="scan_date", help="تاريخ الفحص بصيغة YYYY-MM-DD")
    parser.add_argument("--competitor", default="", help="اسم المنافس")
    parser.add_argument("--page-id", default="", help="معرف الصفحة")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run(
        input_dir=args.input,
        reports_dir=args.reports_dir,
        archive_dir=args.archive_dir,
        scan_date=args.scan_date,
        competitor_name=args.competitor,
        page_id=args.page_id,
    )
    print(f"تم إنشاء التقرير: {report}")


if __name__ == "__main__":
    main()
