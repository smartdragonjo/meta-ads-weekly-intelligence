from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


FIELD_ALIASES = {
    "ad_id": ["ad_id", "ad id", "adid", "معرف الإعلان", "رقم الإعلان"],
    "page_id": ["page_id", "page id", "pageid", "معرف الصفحة", "معرّف الصفحة"],
    "competitor_name": ["competitor", "competitor_name", "page name", "page_name", "اسم المنافس", "اسم الصفحة"],
    "ad_body": [
        "ad text", "ad_text", "ad body", "ad_body", "body", "primary text", "primary_text",
        "text", "caption", "ad copy", "ad_copy", "ad_creative_body", "ad_creative_bodies",
        "creative_body", "creative_bodies", "نص الإعلان", "الكابشن"
    ],
    "ad_title": ["ad title", "ad_title", "headline", "title", "عنوان الإعلان"],
    "start_date": ["start date", "start_date", "ad start date", "تاريخ بدء الإعلان"],
    "status": ["status", "ad status", "حالة الإعلان"],
    "ad_type": ["ad type", "type", "نوع الإعلان"],
    "is_active": ["is active", "is_active", "active", "نشط"],
    "format": ["format", "صيغة الإعلان"],
    "media_type": ["media type", "media_type", "نوع الوسائط"],
    "media_urls": ["media urls", "media_urls", "urls", "روابط الوسائط"],
    "cta": ["cta", "call to action", "call_to_action", "الدعوة إلى الإجراء"],
    "platforms": ["platforms", "platform", "المنصات"],
    "ad_link": ["ad link", "ad_link", "ad url", "ad_url", "library link", "ad library url", "رابط الإعلان"],
    "video_link": ["video link", "video_url", "video url", "رابط الفيديو"],
    "image_link": ["image link", "image_url", "image url", "رابط الصورة"],
}


def normalize_name(value: object) -> str:
    text = str(value).strip().lower().replace("\ufeff", "")
    text = re.sub(r"[\s\-/.]+", "_", text)
    return text.strip("_")


def _flatten_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            text = _flatten_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        for key in ("text", "body", "caption", "content", "value"):
            if key in value:
                nested = _flatten_text(value[key])
                if nested:
                    return nested
        parts = []
        for item in value.values():
            text = _flatten_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, (pd.Series, pd.DataFrame)):
        return ""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(parsed, list):
            return _flatten_text(parsed)
    return text


def _build_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for field, names in FIELD_ALIASES.items():
        for name in names:
            aliases[normalize_name(name)] = field
    return aliases


def _coalesce_field_values(values: pd.Series) -> Any:
    cleaned: list[Any] = []
    for value in values.tolist():
        if value is None or pd.isna(value):
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        cleaned.append(value)
    if not cleaned:
        return ""
    return cleaned[-1]


ALIAS_MAP = _build_alias_map()


def find_csv_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.glob("*.csv") if path.is_file())


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype="string", keep_default_na=False)
    except UnicodeDecodeError:
        return pd.read_csv(path, dtype="string", keep_default_na=False, encoding="latin-1")


def _canonicalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for column in frame.columns:
        normalized = normalize_name(column)
        renamed[column] = ALIAS_MAP.get(normalized, normalized)
    frame = frame.rename(columns=renamed)

    canonical = pd.DataFrame(index=frame.index)
    for field in FIELD_ALIASES:
        matching = [frame[column] for column in frame.columns if column == field]
        if not matching:
            canonical[field] = ""
            continue
        combined = pd.concat(matching, axis=1).apply(_coalesce_field_values, axis=1)
        canonical[field] = combined

    frame = canonical

    if "media_urls" in frame.columns:
        media_urls = frame["media_urls"].apply(_flatten_text)
    else:
        media_urls = pd.Series([""] * len(frame), index=frame.index, dtype="string")

    media_type = frame.get("media_type")
    if media_type is None:
        frame["media_type"] = ""
        media_type = frame["media_type"]
    media_type = media_type.astype("string").str.lower()

    if "video_link" not in frame.columns:
        frame["video_link"] = ""
    if "image_link" not in frame.columns:
        frame["image_link"] = ""

    has_explicit_media_type = bool(media_type.astype(str).str.strip().ne("").any())
    if not has_explicit_media_type:
        frame["video_link"] = media_urls
        frame["image_link"] = ""
    else:
        frame.loc[media_type.str.contains("video", na=False), "video_link"] = media_urls
        frame.loc[media_type.str.contains("image|photo", na=False), "image_link"] = media_urls

    if "video_link" in frame and "media_urls" in frame.columns and frame["video_link"].astype(str).eq("").all():
        frame["video_link"] = media_urls

    if "ad_body" in frame and "ad_text" not in frame:
        frame["ad_text"] = frame["ad_body"]
    if "ad_text" in frame and "ad_body" not in frame:
        frame["ad_body"] = frame["ad_text"]

    if "ad_body" in frame:
        frame["ad_body"] = frame["ad_body"].apply(_flatten_text)
    if "ad_title" in frame:
        frame["ad_title"] = frame["ad_title"].apply(_flatten_text)

    for field in ["video_link", "image_link", "ad_link"]:
        if field in frame:
            frame[field] = frame[field].apply(_flatten_text)

    ordered = [field for field in FIELD_ALIASES]
    for field in ordered:
        if field not in frame:
            frame[field] = ""
    return frame[ordered]


def load_ads(input_dir: Path) -> pd.DataFrame:
    files = find_csv_files(input_dir)
    if not files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")

    frames = [_canonicalize_columns(_read_csv(path)) for path in files]
    ads = pd.concat(frames, ignore_index=True)
    ads = ads.fillna("").astype("string")
    ads["ad_id"] = ads["ad_id"].astype("string").str.strip()
    ads["page_id"] = ads["page_id"].astype("string").str.strip()
    ads = ads[ads["ad_id"] != ""].copy()
    if ads.empty:
        raise ValueError("CSV files do not contain any non-empty ad_id values")
    return ads.drop_duplicates(subset=["ad_id"], keep="last").reset_index(drop=True)
