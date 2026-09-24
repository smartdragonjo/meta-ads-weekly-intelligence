from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


FIELD_ALIASES = {
    "ad_id": ["ad_id", "ad id", "adid", "معرف الإعلان", "رقم الإعلان"],
    "page_id": ["page_id", "page id", "pageid", "معرف الصفحة", "معرّف الصفحة"],
    "competitor_name": ["competitor", "competitor_name", "page name", "page_name", "اسم المنافس", "اسم الصفحة"],
    "ad_text": ["ad text", "ad_text", "body", "primary text", "text", "نص الإعلان"],
    "ad_title": ["ad title", "ad_title", "headline", "title", "عنوان الإعلان"],
    "start_date": ["start date", "start_date", "ad start date", "تاريخ بدء الإعلان"],
    "status": ["status", "ad status", "حالة الإعلان"],
    "ad_type": ["ad type", "type", "نوع الإعلان"],
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


def _build_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for field, names in FIELD_ALIASES.items():
        for name in names:
            aliases[normalize_name(name)] = field
    return aliases


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
    if "media_urls" in frame:
        media_type = frame.get("media_type", "").astype("string").str.lower()
        media_urls = frame["media_urls"].astype("string")
        frame.loc[media_type.str.contains("video", na=False), "video_link"] = media_urls
        frame.loc[media_type.str.contains("image|photo", na=False), "image_link"] = media_urls
    for field in FIELD_ALIASES:
        if field not in frame:
            frame[field] = ""
    return frame[list(FIELD_ALIASES)]


def load_ads(input_dir: Path) -> pd.DataFrame:
    files = find_csv_files(input_dir)
    if not files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")

    frames = [_canonicalize_columns(_read_csv(path)) for path in files]
    ads = pd.concat(frames, ignore_index=True)
    ads = ads.fillna("").astype("string")
    ads["ad_id"] = ads["ad_id"].str.strip()
    ads["page_id"] = ads["page_id"].str.strip()
    ads = ads[ads["ad_id"] != ""].copy()
    if ads.empty:
        raise ValueError("CSV files do not contain any non-empty ad_id values")
    return ads.drop_duplicates(subset=["ad_id"], keep="last").reset_index(drop=True)
