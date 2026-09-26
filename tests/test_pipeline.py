from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from meta_ads_intelligence.csv_loader import load_ads
from meta_ads_intelligence.cloud_run_processing import (
    build_processing_batch,
    load_video_analysis_cache,
    merge_firestore_results,
    fetch_firestore_result,
    parse_firestore_payload,
    execute_cloud_run_job,
)
from meta_ads_intelligence.weekly_pipeline import build_weekly_latest_json, load_weekly_ads, run_weekly_pipeline, main
from meta_ads_intelligence.csv_loader import FIELD_ALIASES


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


class WeeklyOrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.current = self.root / "imports/current"
        self.current.mkdir(parents=True)
        self.latest = self.root / "latest.json"
        self.batch = self.root / "processing_input.json"
        self.cache = self.root / "cache.json"
        self.latest.write_text('{"ads": [{"ad_id": "old-week"}]}', encoding="utf-8")
        self.write_ads([
            {"ad_id": "cached", "video_url": "https://example.com/c.mp4"},
            {"ad_id": "new", "video_url": "https://example.com/n.mp4"},
            {"ad_id": "retry", "video_url": "https://example.com/r.mp4"},
            {"ad_id": "image", "image_url": "https://example.com/i.jpg"},
        ])
        self.cache.write_text(json.dumps({
            "cached": {"status": "success", "analysis": {"summary": "cached summary"}},
            "absent": {"status": "success", "analysis": {"summary": "old ad"}},
            "retry": {"status": "failed", "analysis": None},
        }), encoding="utf-8")

    def write_ads(self, rows):
        pd.DataFrame(rows).to_csv(self.current / "ads.csv", index=False)

    def run_pipeline(self, **kwargs):
        return run_weekly_pipeline(
            input_dir=self.current, latest_json_path=self.latest,
            processing_input_path=self.batch, cache_path=self.cache,
            **kwargs,
        )

    def payload(self, **changes):
        result = {"source": "meta_ads", "run_id": "run-1", "status": "completed", "items": [
            {"ad_id": "new", "analysis_status": "success", "video_analysis": {"summary": "new summary"}},
            {"ad_id": "retry", "analysis_status": "failed"},
        ]}
        result.update(changes)
        return result

    def test_disabled_pipeline_reuses_cache_retries_failed_and_replaces_week(self):
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job") as execute, patch(
            "meta_ads_intelligence.weekly_pipeline.fetch_firestore_result"
        ) as fetch, patch("meta_ads_intelligence.history.load_history", side_effect=AssertionError("History used")):
            latest = self.run_pipeline()
        execute.assert_not_called()
        fetch.assert_not_called()
        records = {row["ad_id"]: row for row in latest["ads"]}
        self.assertEqual(set(records), {"cached", "new", "retry", "image"})
        self.assertEqual(records["cached"]["video_analysis"], {"summary": "cached summary"})
        self.assertEqual(records["cached"]["analysis_status"], "success")
        self.assertEqual(latest["analyzed_video_ads"], 1)
        self.assertEqual(latest["total_video_ads"], 3)
        batch = json.loads(self.batch.read_text(encoding="utf-8"))
        self.assertEqual(batch["source"], "meta_ads")
        self.assertEqual([row["ad_id"] for row in batch["items"]], ["new", "retry"])
        self.assertEqual(set(batch["items"][0]), {"ad_id", "page_id", "page_name", "video_url", "ad_body", "ad_title"})
        self.assertEqual(json.loads(self.latest.read_text(encoding="utf-8")), latest)

    def test_one_execution_merges_new_results_without_erasing_cached_success(self):
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job") as execute, patch(
            "meta_ads_intelligence.weekly_pipeline.fetch_firestore_result", return_value={"payload_json": json.dumps(self.payload())}
        ) as fetch:
            latest = self.run_pipeline(cloud_run_enabled=True, processing_url="https://example.com/input.json", run_id="run-1")
        execute.assert_called_once()
        fetch.assert_called_once()
        self.assertEqual(execute.call_args.kwargs["job_name"], "competitors-report")
        self.assertEqual(latest["analyzed_video_ads"], 2)
        self.assertEqual(latest["failed_video_ads"], 1)
        cache = json.loads(self.cache.read_text(encoding="utf-8"))
        self.assertEqual(cache["new"]["analysis"]["summary"], "new summary")
        self.assertEqual(cache["retry"]["status"], "failed")
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job"):
            self.run_pipeline(prepare_only=True)
        self.assertEqual([r["ad_id"] for r in json.loads(self.batch.read_text())["items"]], ["retry"])

    def test_cloud_errors_still_write_current_report_without_exception_secrets(self):
        for error in [RuntimeError("private-secret"), FileNotFoundError("gcloud"), PermissionError("auth")]:
            with self.subTest(error=type(error).__name__), patch(
                "meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job", side_effect=error
            ), patch("meta_ads_intelligence.weekly_pipeline.fetch_firestore_result") as fetch:
                latest = self.run_pipeline(cloud_run_enabled=True, processing_url="url")
                fetch.assert_not_called()
                self.assertEqual(latest["total_ads"], 4)
                self.assertEqual(latest["analyzed_video_ads"], 1)
                self.assertEqual(latest["failed_video_ads"], 2)
                self.assertNotIn("private-secret", self.latest.read_text())

    def test_invalid_or_missing_firestore_results_still_write_current_report(self):
        for result in [None, {"payload_json": "bad json"}, self.payload(source="other"),
                       self.payload(run_id="other"), self.payload(status="processing")]:
            with self.subTest(result=result), patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job"), patch(
                "meta_ads_intelligence.weekly_pipeline.fetch_firestore_result", return_value=result
            ):
                latest = self.run_pipeline(cloud_run_enabled=True, processing_url="url", run_id="run-1")
                self.assertEqual(latest["total_ads"], 4)
                self.assertEqual(latest["failed_video_ads"], 2)

    def test_firestore_auth_failure_still_writes_report(self):
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job"), patch(
            "meta_ads_intelligence.weekly_pipeline.fetch_firestore_result", side_effect=PermissionError("secret")
        ):
            self.assertEqual(self.run_pipeline(cloud_run_enabled=True, processing_url="url")["total_ads"], 4)

    def test_no_pending_video_creates_no_batch_and_no_execution(self):
        for rows in [[{"ad_id": "image", "image_url": "https://example.com/i.jpg"}],
                     [{"ad_id": "cached", "video_url": "https://example.com/v.mp4"}]]:
            with self.subTest(rows=rows), patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job") as execute:
                self.write_ads(rows)
                self.run_pipeline(cloud_run_enabled=True, processing_url="url")
                self.assertFalse(self.batch.exists())
                execute.assert_not_called()

    def test_stale_batch_does_not_trigger_execution(self):
        self.batch.write_text('{"source":"meta_ads","items":[{"ad_id":"old"}]}')
        self.write_ads([{"ad_id": "image", "image_url": "image"}])
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job") as execute:
            self.run_pipeline(cloud_run_enabled=True, processing_url="old-url")
        execute.assert_not_called()

    def test_malformed_single_result_does_not_discard_successful_results(self):
        payload = self.payload()
        payload["items"].extend([None, {"ad_id": "retry", "analysis_status": "success", "video_analysis": "invalid"}])
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job"), patch(
            "meta_ads_intelligence.weekly_pipeline.fetch_firestore_result", return_value=payload
        ):
            latest = self.run_pipeline(cloud_run_enabled=True, processing_url="url", run_id="run-1")
        self.assertEqual(latest["analyzed_video_ads"], 2)
        self.assertEqual(latest["failed_video_ads"], 1)

    def test_generated_run_ids_are_unique(self):
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job") as execute, patch(
            "meta_ads_intelligence.weekly_pipeline.fetch_firestore_result", return_value=None
        ):
            self.run_pipeline(cloud_run_enabled=True, processing_url="same-url")
            self.run_pipeline(cloud_run_enabled=True, processing_url="same-url")
        first, second = [call.kwargs["run_id"] for call in execute.call_args_list]
        self.assertNotEqual(first, second)

    def test_no_csv_or_no_valid_ads_preserves_latest(self):
        previous = self.latest.read_bytes()
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(FileNotFoundError):
            run_weekly_pipeline(input_dir=empty, latest_json_path=self.latest)
        self.assertEqual(self.latest.read_bytes(), previous)
        self.write_ads([{"ad_id": ""}])
        with self.assertRaises(ValueError):
            self.run_pipeline()
        self.assertEqual(self.latest.read_bytes(), previous)

    def test_prepare_only_writes_batch_but_does_not_replace_report(self):
        previous = self.latest.read_bytes()
        with patch("meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job") as execute:
            result = self.run_pipeline(prepare_only=True, cloud_run_enabled=True, processing_url="url")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(self.latest.read_bytes(), previous)
        execute.assert_not_called()

    def test_main_uses_orchestration_defaults_and_cache_argument(self):
        with patch("sys.argv", ["weekly_pipeline", "--cache-path", "custom-cache.json"]), patch.dict(
            "os.environ", {}, clear=True
        ), patch("meta_ads_intelligence.weekly_pipeline.run_weekly_pipeline", return_value={}) as run:
            main()
        self.assertEqual(run.call_args.kwargs["input_dir"], Path("imports/current"))
        self.assertEqual(run.call_args.kwargs["cache_path"], Path("custom-cache.json"))

    def test_main_no_csv_exits_nonzero(self):
        with patch("sys.argv", ["weekly_pipeline"]), patch(
            "meta_ads_intelligence.weekly_pipeline.run_weekly_pipeline", side_effect=FileNotFoundError
        ), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 1)

    def test_all_caption_aliases(self):
        for alias in FIELD_ALIASES["ad_body"]:
            with self.subTest(alias=alias):
                self.write_ads([{"ad_id": "1", alias: '["مرحبا 😊", "سطر جديد"]'}])
                row = load_ads(self.current).iloc[0]
                self.assertEqual(row["ad_body"], "مرحبا 😊\nسطر جديد")
                self.assertEqual(row["ad_text"], row["ad_body"])

    def test_media_links_preserved_per_row_without_misclassifying_images(self):
        self.write_ads([
            {"ad_id": "1", "video_url": "explicit-video"},
            {"ad_id": "2", "media_urls": "fallback-video"},
            {"ad_id": "3", "media_type": "image", "media_urls": "fallback-image"},
            {"ad_id": "4", "image_url": "explicit-image"},
            {"ad_id": "5", "media_type": "video", "video_url": "keep-video", "media_urls": "other-video"},
        ])
        rows = load_ads(self.current).set_index("ad_id")
        self.assertEqual(rows.loc["1", "video_link"], "explicit-video")
        self.assertEqual(rows.loc["2", "video_link"], "fallback-video")
        self.assertEqual(rows.loc["3", "image_link"], "fallback-image")
        self.assertEqual(rows.loc["3", "video_link"], "")
        self.assertEqual(rows.loc["4", "image_link"], "explicit-image")
        self.assertEqual(rows.loc["5", "video_link"], "keep-video")

    def test_duplicate_across_files_keeps_last_and_ignores_outside_current(self):
        pd.DataFrame([{"ad_id": "new", "caption": "last"}]).to_csv(self.current / "z.csv", index=False)
        pd.DataFrame([{"ad_id": "outside"}]).to_csv(self.current.parent / "outside.csv", index=False)
        rows = load_weekly_ads(self.current).set_index("ad_id")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows.loc["new", "ad_body"], "last")

    def test_credentials_metadata_never_enter_json_artifacts(self):
        self.write_ads([{"ad_id": "new", "video_url": "url", "credentials": "secret-csv"}])
        payload = {"credentials": "secret-firestore", "payload_json": self.payload()}
        with patch.dict("os.environ", {"GOOGLE_APPLICATION_CREDENTIALS": "secret-path"}), patch(
            "meta_ads_intelligence.weekly_pipeline.execute_cloud_run_job"
        ), patch("meta_ads_intelligence.weekly_pipeline.fetch_firestore_result", return_value=payload):
            self.run_pipeline(cloud_run_enabled=True, processing_url="url", run_id="run-1")
        for path in (self.latest, self.batch, self.cache):
            self.assertNotIn("secret-", path.read_text(encoding="utf-8"))

    def test_legacy_run_still_generates_excel_and_history(self):
        from meta_ads_intelligence.pipeline import run
        report = run(self.current, self.root / "reports", self.root / "archive", scan_date="2026-09-26")
        self.assertTrue(report.exists())
        self.assertTrue((self.root / "archive/history.json").exists())


class CloudContractTest(unittest.TestCase):
    def payload(self):
        return {"source": "meta_ads", "run_id": "r", "status": "completed", "items": []}

    def test_firestore_fetch_extracts_string_and_dict_payload_with_mock_client(self):
        firestore = MagicMock()
        document = firestore.Client.return_value.collection.return_value.document.return_value.get.return_value
        document.exists = True
        for payload in [self.payload(), json.dumps(self.payload())]:
            with self.subTest(payload=payload), patch.dict("sys.modules", {
                "google": MagicMock(), "google.cloud": MagicMock(firestore=firestore), "google.cloud.firestore": firestore
            }):
                document.to_dict.return_value = {"payload_json": payload, "metadata": "ignored"}
                self.assertEqual(fetch_firestore_result(project_id="test", run_id="r"), self.payload())
        firestore.Client.return_value.collection.assert_called_with("meta_ads_processing_results")
        firestore.Client.return_value.collection.return_value.document.assert_called_with("r")

    def test_rejects_invalid_contracts(self):
        for payload in [{"payload_json": "broken"}, {"payload_json": []},
                        dict(self.payload(), source="other"), dict(self.payload(), run_id="other"),
                        dict(self.payload(), status="running"), dict(self.payload(), items={})]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_firestore_payload(payload, "r")

    def test_execution_uses_only_runtime_overrides_once(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as run:
            execute_cloud_run_job(job_name="competitors-report", region="test-region", project_id="test-project",
                                  run_id="r", processing_url="https://raw.githubusercontent.com/repo/sha/input.json")
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["gcloud", "run", "jobs", "execute", "competitors-report"])
        self.assertIn("--wait", command)
        self.assertIn("--region", command)
        self.assertIn("--project", command)
        overrides = command[command.index("--update-env-vars") + 1]
        self.assertIn("PROCESSING_SOURCE=meta_ads", overrides)
        self.assertIn("META_ADS_RUN_ID=r", overrides)
        self.assertIn("META_ADS_INPUT_URL=https://raw.githubusercontent.com/", overrides)
        self.assertIn("META_ADS_RESULT_COLLECTION=meta_ads_processing_results", overrides)

    def test_wrong_job_or_missing_config_never_executes(self):
        for job, project, region in [("other-job", "p", "r"), ("competitors-report", "", "r"), ("competitors-report", "p", "")]:
            with self.subTest(job=job, project=project, region=region), patch("subprocess.run") as run:
                with self.assertRaises(ValueError):
                    execute_cloud_run_job(job_name=job, region=region, project_id=project, run_id="r", processing_url="url")
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
