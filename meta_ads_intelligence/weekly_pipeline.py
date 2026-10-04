from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from .cloud_run_processing import (
    DEFAULT_CACHE_PATH,
    apply_cached_analyses,
    build_processing_batch,
    execute_cloud_run_job,
    fetch_firestore_result,
    load_video_analysis_cache,
    merge_firestore_results,
    save_video_analysis_cache,
    update_video_analysis_cache,
)
from .csv_loader import load_ads

DEFAULT_PROCESSING_INPUT_PATH = Path("docs/data/processing_input.json")


def _normalize_scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _ad_type_from_row(row: pd.Series) -> str:
    format_value = str(row.get("format") or "").strip()
    media_value = str(row.get("media_type") or "").strip()
    combined = f"{format_value} {media_value}".lower()

    if "carousel" in combined:
        return "carousel"
    if "video" in combined:
        return "video"
    if "image" in combined or "photo" in combined:
        return "image"
    return format_value or media_value or "other"


def load_weekly_ads(input_dir: str | Path) -> pd.DataFrame:
    ads = load_ads(Path(input_dir))

    for historical in [
        "comparison",
        "comparison_result",
        "first_seen",
        "last_seen",
        "times_seen",
    ]:
        if historical in ads.columns:
            ads = ads.drop(columns=[historical])

    return ads.reset_index(drop=True)


def _apply_cached_failed_statuses(
    ads: pd.DataFrame,
    cache: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    result = ads.copy()
    for index, row in result.iterrows():
        ad_id = str(row.get("ad_id") or "").strip()
        cached = cache.get(ad_id)
        if (
            isinstance(cached, dict)
            and cached.get("status") == "failed"
            and str(result.at[index, "analysis_status"] or "") != "success"
        ):
            result.at[index, "analysis_status"] = "failed"
            result.at[index, "video_analysis"] = None
    return result


def build_weekly_latest_json(
    input_dir: str | Path = "imports/current",
    output_path: str | Path = "docs/data/latest.json",
    scan_date: str | None = None,
    ads: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if ads is None:
        ads = load_weekly_ads(input_dir)

    if ads.empty:
        raise ValueError("No ads available for the current weekly report")

    scan_date = scan_date or date.today().isoformat()
    records: list[dict[str, Any]] = []

    for _, row in ads.iterrows():
        record = {
            "ad_id": _normalize_scalar(row.get("ad_id", "")),
            "page_id": _normalize_scalar(row.get("page_id", "")),
            "page_name": _normalize_scalar(row.get("competitor_name", "")),
            "ad_body": _normalize_scalar(row.get("ad_body", row.get("ad_text", ""))),
            "ad_title": _normalize_scalar(row.get("ad_title", "")),
            "start_date": _normalize_scalar(row.get("start_date", "")),
            "is_active": _normalize_scalar(row.get("is_active", "")),
            "format": _normalize_scalar(row.get("format", "") or row.get("ad_type", "")),
            "media_type": _normalize_scalar(row.get("media_type", "")),
            "platforms": _normalize_scalar(row.get("platforms", "")),
            "cta": _normalize_scalar(row.get("cta", "")),
            "ad_url": _normalize_scalar(row.get("ad_link", "")),
            "video_url": _normalize_scalar(row.get("video_link", "")),
            "image_url": _normalize_scalar(row.get("image_link", "")),
        }

        if row.get("analysis_status") not in (None, ""):
            record["analysis_status"] = _normalize_scalar(row.get("analysis_status", ""))

        if isinstance(row.get("video_analysis"), dict):
            record["video_analysis"] = row.get("video_analysis")

        records.append(record)

    grouped = ads.copy()
    grouped["competitor_name"] = grouped["competitor_name"].replace("", "غير محدد")
    competitor_rows: list[dict[str, Any]] = []

    for competitor, group in grouped.groupby("competitor_name", sort=True):
        ad_type_values = group.apply(_ad_type_from_row, axis=1)
        competitor_rows.append(
            {
                "name": str(competitor),
                "total_ads": int(len(group)),
                "video_count": int(ad_type_values.str.contains("video").sum()),
                "image_count": int(ad_type_values.str.contains("image|photo").sum()),
                "carousel_count": int(ad_type_values.str.contains("carousel").sum()),
            }
        )

    payload = {
        "scan_date": scan_date,
        "total_ads": len(records),
        "total_video_ads": sum(
            1 for row in records if str(row.get("video_url") or "").strip()
        ),
        "analyzed_video_ads": sum(
            1
            for row in records
            if str(row.get("analysis_status") or "").lower() == "success"
        ),
        "failed_video_ads": sum(
            1
            for row in records
            if str(row.get("analysis_status") or "").lower() == "failed"
        ),
        "competitors": competitor_rows,
        "ads": records,
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    return payload


def write_processing_input(
    batch: dict[str, Any],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(batch, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def run_weekly_pipeline(
    *,
    input_dir: str | Path = "imports/current",
    latest_json_path: str | Path = "docs/data/latest.json",
    processing_input_path: str | Path = DEFAULT_PROCESSING_INPUT_PATH,
    cache_path: str | Path = DEFAULT_CACHE_PATH,
    scan_date: str | None = None,
    gcp_project_id: str | None = None,
    gcp_region: str | None = None,
    cloud_run_job_name: str | None = None,
    firestore_project_id: str | None = None,
    result_collection: str | None = None,
    cloud_run_enabled: bool = False,
    processing_url: str | None = None,
    run_id: str | None = None,
    prepare_only: bool = False,
    process_ad_id: str | None = None,
) -> dict[str, Any]:
    ads = load_weekly_ads(input_dir)

    if ads.empty:
        raise ValueError("No weekly CSV data was found")

    cache = load_video_analysis_cache(cache_path)
    ads = apply_cached_analyses(ads, cache)
    ads = _apply_cached_failed_statuses(ads, cache)

    batch = build_processing_batch(ads, cache)

    if process_ad_id:
        process_ad_id = str(process_ad_id).strip()
        batch = {
            "source": "meta_ads",
            "items": [
                item
                for item in batch.get("items", [])
                if str(item.get("ad_id") or "").strip() == process_ad_id
            ],
        }

    if batch["items"]:
        write_processing_input(batch, processing_input_path)

    if prepare_only:
        return batch

    if batch["items"] and cloud_run_enabled and processing_url:
        run_id = run_id or f"meta-ads-{uuid4().hex}"
        try:
            execute_cloud_run_job(
                job_name=cloud_run_job_name or "competitors-report",
                region=gcp_region or "",
                project_id=gcp_project_id or "",
                run_id=run_id,
                processing_url=processing_url,
                enabled=True,
                result_collection=result_collection,
            )
            payload = fetch_firestore_result(
                project_id=firestore_project_id or gcp_project_id or "",
                run_id=run_id,
                result_collection=result_collection or "meta_ads_processing_results",
            )
            if payload is None:
                raise ValueError("Firestore result is missing")

            ads = merge_firestore_results(ads, payload, run_id)

            pending_ids = {item["ad_id"] for item in batch["items"]}
            missing = ads["ad_id"].isin(pending_ids) & ads["analysis_status"].eq("")
            ads.loc[missing, "analysis_status"] = "failed"

        except Exception as exc:
            logging.warning(
                "Video analysis unavailable (%s); saving failed status for this item",
                type(exc).__name__,
            )
            pending_ids = {item["ad_id"] for item in batch["items"]}
            ads.loc[ads["ad_id"].isin(pending_ids), "analysis_status"] = "failed"

    elif batch["items"]:
        logging.warning(
            "Video analysis disabled or input URL unavailable; saving current report"
        )

    cache = update_video_analysis_cache(cache, ads)
    save_video_analysis_cache(cache, cache_path)

    latest = build_weekly_latest_json(
        input_dir,
        latest_json_path,
        scan_date=scan_date,
        ads=ads,
    )
    return latest


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Weekly Meta Ads intelligence pipeline"
    )

    parser.add_argument("--input-dir", default="imports/current", type=Path)
    parser.add_argument("--latest-json", default="docs/data/latest.json", type=Path)
    parser.add_argument("--scan-date", default=date.today().isoformat())
    parser.add_argument("--cache-path", default=DEFAULT_CACHE_PATH, type=Path)
    parser.add_argument(
        "--processing-input",
        type=Path,
        default=DEFAULT_PROCESSING_INPUT_PATH,
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare the batch without executing Cloud Run or replacing latest.json",
    )
    parser.add_argument("--processing-url", default=os.getenv("META_ADS_INPUT_URL"))
    parser.add_argument("--run-id", default=os.getenv("META_ADS_RUN_ID"))
    parser.add_argument(
        "--process-ad",
        dest="process_ad_id",
        default=None,
        help="Process exactly one ad_id from the current batch",
    )
    args = parser.parse_args()

    try:
        result = run_weekly_pipeline(
            input_dir=args.input_dir,
            latest_json_path=args.latest_json,
            scan_date=args.scan_date,
            cache_path=args.cache_path,
            processing_input_path=args.processing_input,
            prepare_only=args.prepare_only,
            processing_url=args.processing_url,
            run_id=args.run_id,
            process_ad_id=args.process_ad_id,
            cloud_run_enabled=os.getenv(
                "CLOUD_RUN_PROCESSING_ENABLED",
                "false",
            ).lower() == "true",
            gcp_project_id=os.getenv("GCP_PROJECT_ID"),
            gcp_region=os.getenv("GCP_REGION"),
            cloud_run_job_name=os.getenv("CLOUD_RUN_JOB_NAME"),
            firestore_project_id=os.getenv("FIRESTORE_PROJECT_ID"),
            result_collection=os.getenv("META_ADS_RESULT_COLLECTION"),
        )

        if args.prepare_only:
            has_batch = str(bool(result["items"])).lower()
            if os.getenv("GITHUB_OUTPUT"):
                with open(
                    os.environ["GITHUB_OUTPUT"],
                    "a",
                    encoding="utf-8",
                ) as output:
                    output.write(f"has_batch={has_batch}\n")
            print(f"Prepared weekly batch: {len(result['items'])} videos")
            return

        print(
            f"Created weekly report for "
            f"{args.scan_date} from {args.input_dir}"
        )

    except FileNotFoundError:
        print(
            f"No CSV files were found in {args.input_dir}. "
            f"Weekly processing stopped without changing latest.json."
        )
        raise SystemExit(1)

    except ValueError as exc:
        print(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
