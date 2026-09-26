from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_CACHE_PATH = Path("data/video-analysis-cache.json")
DEFAULT_RESULT_COLLECTION = "meta_ads_processing_results"


def load_video_analysis_cache(path: str | Path | dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    if isinstance(path, dict):
        return path
    cache_path = Path(path) if path else DEFAULT_CACHE_PATH
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_video_analysis_cache(cache: dict[str, dict[str, Any]], path: str | Path | None = None) -> Path:
    cache_path = Path(path) if path else DEFAULT_CACHE_PATH
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return cache_path


def _clean_text(value: Any) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    if isinstance(value, list):
        text = "\n".join(_clean_text(item) for item in value if _clean_text(item))
    elif isinstance(value, dict):
        text = "\n".join(
            _clean_text(item) for item in value.values() if isinstance(item, (str, int, float, bool, list, dict))
        )
    return text.strip()


def _extract_ad_body(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, list):
        flattened = []
        for item in value:
            text = _extract_ad_body(item)
            if text:
                flattened.append(text)
        return "\n".join(flattened)
    if isinstance(value, dict):
        for key in ("text", "body", "caption", "content", "value"):
            if key in value and value[key] not in (None, ""):
                return _extract_ad_body(value[key])
        return "\n".join(_extract_ad_body(item) for item in value.values() if _extract_ad_body(item))
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return _extract_ad_body(parsed)
        except json.JSONDecodeError:
            pass
    return text


def build_processing_batch(ads: pd.DataFrame, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    for _, row in ads.iterrows():
        ad_id = str(row.get("ad_id", "") or "").strip()
        video_url = str(row.get("video_url") or row.get("video_link") or "").strip()
        if not ad_id or not video_url:
            continue
        cached = cache.get(ad_id)
        if isinstance(cached, dict) and cached.get("status") == "success":
            continue
        items.append({
            "ad_id": ad_id,
            "page_id": str(row.get("page_id", "") or ""),
            "page_name": str(row.get("page_name") or row.get("competitor_name") or ""),
            "video_url": video_url,
            "ad_body": _clean_text(row.get("ad_body", "")),
            "ad_title": _clean_text(row.get("ad_title", "")),
        })
    return {"source": "meta_ads", "items": items}


def execute_cloud_run_job(
    *,
    job_name: str,
    region: str,
    project_id: str,
    run_id: str,
    processing_url: str,
    enabled: bool = True,
    result_collection: str | None = None,
) -> Any:
    if not enabled:
        return None

    env_vars = [
        "PROCESSING_SOURCE=meta_ads",
        f"META_ADS_INPUT_URL={processing_url}",
        f"META_ADS_RUN_ID={run_id}",
    ]
    if result_collection:
        env_vars.append(f"META_ADS_RESULT_COLLECTION={result_collection}")

    command = [
        "gcloud",
        "run",
        "jobs",
        "execute",
        job_name,
        "--project",
        project_id,
        "--region",
        region,
        "--wait",
        "--update-env-vars",
        ",".join(env_vars),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Cloud Run execution failed: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}")
    return result


def fetch_firestore_result(*, project_id: str, run_id: str, result_collection: str = DEFAULT_RESULT_COLLECTION) -> dict[str, Any] | None:
    try:
        from google.cloud import firestore
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("google-cloud-firestore is required to fetch Firestore results") from exc

    client = firestore.Client(project=project_id)
    document = client.collection(result_collection).document(run_id).get()
    if not document.exists:
        return None
    return document.to_dict() or {}


def merge_firestore_results(ads: pd.DataFrame, payload: dict[str, Any], run_id: str) -> pd.DataFrame:
    if not isinstance(payload, dict):
        raise ValueError("Firestore payload must be a dictionary")
    if payload.get("source") != "meta_ads":
        raise ValueError("Firestore payload source does not match meta_ads")
    if payload.get("run_id") != run_id:
        raise ValueError("Firestore payload run_id does not match the current execution")
    if payload.get("status") != "completed":
        raise ValueError("Firestore payload status is not completed")

    merged = ads.copy()
    merged["analysis_status"] = ""
    merged["video_analysis"] = pd.Series([None] * len(merged), index=merged.index, dtype="object")

    for item in payload.get("items") or []:
        ad_id = str(item.get("ad_id") or "").strip()
        if not ad_id:
            continue
        mask = merged["ad_id"].astype(str).str.strip() == ad_id
        if not mask.any():
            continue
        analysis_status = str(item.get("analysis_status") or "")
        merged.loc[mask, "analysis_status"] = analysis_status
        if "video_analysis" in item and isinstance(item.get("video_analysis"), dict):
            merged.loc[mask, "video_analysis"] = [item.get("video_analysis")] * int(mask.sum())
        elif analysis_status:
            merged.loc[mask, "video_analysis"] = [None] * int(mask.sum())

    return merged


def update_video_analysis_cache(cache: dict[str, dict[str, Any]], merged_ads: pd.DataFrame) -> dict[str, dict[str, Any]]:
    for _, row in merged_ads.iterrows():
        ad_id = str(row.get("ad_id") or "").strip()
        status = str(row.get("analysis_status") or "")
        if not ad_id or not status:
            continue
        if status == "success":
            cache[ad_id] = {"status": "success", "analysis": row.get("video_analysis")}
        elif status == "failed":
            if ad_id in cache and cache.get(ad_id, {}).get("status") == "success":
                continue
            cache[ad_id] = {"status": "failed", "analysis": None}
    return cache
