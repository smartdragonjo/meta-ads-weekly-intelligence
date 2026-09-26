from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from meta_ads_intelligence.csv_loader import load_ads
from meta_ads_intelligence.cloud_run_processing import (
    build_processing_batch,
    load_video_analysis_cache,
    merge_firestore_results,
)
from meta_ads_intelligence.weekly_pipeline import build_weekly_latest_json, load_weekly_ads


class WeeklyPipelineTest(unittest.TestCase):
    def test_merge_multiple_csvs_and_deduplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "imports" / "current"
            input_dir.mkdir(parents=True)
            pd.DataFrame([
                {"ad_id": "100", "page_id": "11", "competitor_name": "Alpha", "ad_text": "First", "video_url": "https://example.com/v1.mp4"},
                {"ad_id": "100", "page_id": "11", "competitor_name": "Alpha", "ad_text": "Updated", "video_url": "https://example.com/v2.mp4"},
                {"ad_id": "200", "page_id": "22", "competitor_name": "Beta", "ad_text": "Second", "image_url": "https://example.com/i.jpg"},
            ]).to_csv(input_dir / "one.csv", index=False)
            pd.DataFrame([
                {"ad_id": "300", "page_id": "33", "competitor_name": "Gamma", "primary text": "Third"},
            ]).to_csv(input_dir / "two.csv", index=False)

            ads = load_weekly_ads(input_dir)
            self.assertEqual(len(ads), 3)
            self.assertEqual(list(ads[ads["ad_id"] == "100"]["ad_body"])[0], "Updated")
            self.assertNotIn("first_seen", ads.columns)

    def test_caption_aliases_and_arabic_emoji_and_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "imports" / "current"
            input_dir.mkdir(parents=True)
            pd.DataFrame([
                {"ad_id": "500", "page_id": "55", "competitor_name": "Arabic", "ad_creative_body": '["مرحبا بالعالم 😊", "سطر جديد"]'},
                {"ad_id": "501", "page_id": "55", "competitor_name": "Arabic", "caption": "هذا نص\nعربي\n🙂"},
            ]).to_csv(input_dir / "caption.csv", index=False)

            ads = load_weekly_ads(input_dir)
            ad_body_map = {row["ad_id"]: row["ad_body"] for _, row in ads.iterrows()}
            self.assertEqual(ad_body_map["500"], "مرحبا بالعالم 😊\nسطر جديد")
            self.assertEqual(ad_body_map["501"], "هذا نص\nعربي\n🙂")

    def test_load_ads_ignores_empty_ad_id_and_handles_media_urls_without_media_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "imports" / "current"
            input_dir.mkdir(parents=True)
            pd.DataFrame([
                {"ad_id": "", "page_id": "1", "competitor_name": "Skip", "media_urls": "https://example.com/ignored.mp4"},
                {"ad_id": "910", "page_id": "1", "competitor_name": "Need", "media_urls": "https://example.com/video.mp4"},
            ]).to_csv(input_dir / "media.csv", index=False)

            ads = load_ads(input_dir)
            self.assertEqual(len(ads), 1)
            self.assertEqual(ads.iloc[0]["ad_id"], "910")
            self.assertEqual(ads.iloc[0]["video_link"], "https://example.com/video.mp4")

    def test_weekly_latest_json_has_no_historical_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "imports" / "current"
            input_dir.mkdir(parents=True)
            pd.DataFrame([
                {"ad_id": "701", "page_id": "77", "competitor_name": "Solo", "ad_text": "Weekly ad", "video_url": "https://example.com/v.mp4"},
            ]).to_csv(input_dir / "solo.csv", index=False)

            latest = build_weekly_latest_json(input_dir, root / "docs" / "data" / "latest.json", "2026-09-26")
            self.assertEqual(latest["scan_date"], "2026-09-26")
            self.assertEqual(latest["total_ads"], 1)
            self.assertNotIn("total_new_ads", latest)
            self.assertNotIn("first_seen", latest["ads"][0])
            self.assertNotIn("comparison_result", latest["ads"][0])

    def test_cache_success_blocks_resend_and_failed_allows_retry(self) -> None:
        cache = {"A1": {"status": "success", "analysis": {"summary": "ok"}}}
        self.assertTrue(load_video_analysis_cache(cache).get("A1", {}).get("status") == "success")
        self.assertEqual(build_processing_batch(pd.DataFrame([
            {"ad_id": "A1", "page_id": "p", "page_name": "Alpha", "video_url": "https://example.com/1.mp4", "ad_body": "Body"},
            {"ad_id": "A2", "page_id": "p", "page_name": "Alpha", "video_url": "https://example.com/2.mp4", "ad_body": "Body2"},
        ]), cache)["items"][0]["ad_id"], "A2")

    def test_batch_has_meta_ads_source_and_single_execution(self) -> None:
        batch = build_processing_batch(pd.DataFrame([
            {"ad_id": "A1", "page_id": "p", "page_name": "Alpha", "video_url": "https://example.com/1.mp4", "ad_body": "Body"},
            {"ad_id": "A2", "page_id": "p", "page_name": "Alpha", "video_url": "https://example.com/2.mp4", "ad_body": "Body2"},
        ]), {})
        self.assertEqual(batch["source"], "meta_ads")
        self.assertEqual(len(batch["items"]), 2)

    def test_merge_firestore_result_requires_matching_source_and_run_id(self) -> None:
        ads = pd.DataFrame([
            {"ad_id": "A1", "page_id": "p", "page_name": "Alpha", "video_url": "https://example.com/1.mp4", "ad_body": "Body"},
        ])
        payload = {
            "source": "meta_ads",
            "run_id": "run-9",
            "status": "completed",
            "items": [{"ad_id": "A1", "analysis_status": "success", "video_analysis": {"summary": "ok"}}],
        }
        merged = merge_firestore_results(ads, payload, "run-9")
        self.assertEqual(merged.iloc[0]["analysis_status"], "success")
        self.assertEqual(merged.iloc[0]["video_analysis"]["summary"], "ok")

        with self.assertRaises(ValueError):
            merge_firestore_results(ads, {"source": "other", "run_id": "run-9", "status": "completed", "items": []}, "run-9")

        with self.assertRaises(ValueError):
            merge_firestore_results(ads, {"source": "meta_ads", "run_id": "other", "status": "completed", "items": []}, "run-9")

    def test_cloud_run_disabled_causes_no_external_call(self) -> None:
        from unittest.mock import patch

        with patch("subprocess.run") as mocked_run:
            from meta_ads_intelligence.cloud_run_processing import execute_cloud_run_job
            result = execute_cloud_run_job(
                job_name="competitors-report",
                region="us-central1",
                project_id="demo-project",
                run_id="r-1",
                processing_url="https://example.com/input.json",
                enabled=False,
            )
            self.assertIsNone(result)
            mocked_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
