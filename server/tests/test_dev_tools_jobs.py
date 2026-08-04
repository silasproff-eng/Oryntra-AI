from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import pandas as pd

from backend import pattern_lab
from backend.routes import dev_tools


class DevToolJobStateTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        dev_tools.CACHE_WARM_JOBS.clear()
        dev_tools.PATTERN_LAB_JOBS.clear()
        dev_tools.VAI_TRAIN_JOBS.clear()

    async def test_terminal_pattern_stop_returns_existing_job(self):
        from backend.pattern_lab_jobs import status_path, write_status
        job = {"job_id": "done-test", "status": "done", "result_available": False}
        write_status(job["job_id"], job)
        try:
            stopped = await dev_tools.pattern_lab_stop(job["job_id"])
            self.assertEqual(stopped["status"], "done")
        finally:
            status_path(job["job_id"]).unlink(missing_ok=True)

    async def test_pattern_lab_start_launches_isolated_worker(self):
        from backend.pattern_lab_jobs import request_path, status_path
        request = dev_tools.PatternLabRequest(
            tickers=["AAPL"], universe_mode="manual", max_tests_per_ticker=3,
            engine_modes=["official", "v8"], bootstrap_samples=0,
        )
        with patch.object(dev_tools, "launch_pattern_lab_worker", return_value=43210):
            job = await dev_tools.pattern_lab_start(request)
        try:
            self.assertEqual(job["worker_pid"], 43210)
            self.assertEqual(job["status"], "running")
            self.assertTrue(request_path(job["job_id"]).exists())
            self.assertTrue(status_path(job["job_id"]).exists())
        finally:
            request_path(job["job_id"]).unlink(missing_ok=True)
            status_path(job["job_id"]).unlink(missing_ok=True)

    async def test_cache_warm_reports_failure_when_every_ticker_fails(self):
        job = {
            "job_id": "cache-failure", "status": "queued", "tickers": ["BAD1", "BAD2"],
            "period": "1y", "delay_seconds": 0, "max_cache_gb": 10, "finished_at": None,
            "total": 2, "completed": 0, "stored_bars": 0, "current_ticker": None,
            "results": [], "errors": [], "db_size_bytes": 0,
        }
        with (
            patch.object(dev_tools, "fetch_ticker_data", side_effect=ValueError("provider unavailable")),
            patch.object(dev_tools, "get_ohlcv_cache_size_bytes", return_value=0),
        ):
            await dev_tools._run_cache_warm_job(job)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["completed"], 2)
        self.assertEqual(len(job["errors"]), 2)

    async def test_cache_warm_reports_partial(self):
        job = {
            "job_id": "cache-partial", "status": "queued", "tickers": ["GOOD", "BAD"],
            "period": "1y", "delay_seconds": 0, "max_cache_gb": 10, "finished_at": None,
            "total": 2, "completed": 0, "stored_bars": 0, "current_ticker": None,
            "results": [], "errors": [], "db_size_bytes": 0,
        }
        history = pd.DataFrame([{"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100}])
        with (
            patch.object(dev_tools, "fetch_ticker_data", side_effect=[{"history": history, "provider": "test"}, ValueError("provider unavailable")]),
            patch.object(dev_tools, "store_ohlcv_bars", return_value=1),
            patch.object(dev_tools, "get_ohlcv_cache_size_bytes", return_value=0),
        ):
            await dev_tools._run_cache_warm_job(job)
        self.assertEqual(job["status"], "partial")
        self.assertEqual(len(job["results"]), 1)
        self.assertEqual(len(job["errors"]), 1)


class BackgroundTaskRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_background_task_is_retained_until_completion(self):
        release = asyncio.Event()
        async def worker():
            await release.wait()
            return "done"
        task = dev_tools._start_background_task(worker())
        self.assertIn(task, dev_tools.BACKGROUND_TASKS)
        release.set()
        self.assertEqual(await task, "done")
        await asyncio.sleep(0)
        self.assertNotIn(task, dev_tools.BACKGROUND_TASKS)


class PatternLabFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_cache_fails_clearly_without_api(self):
        async def empty_history(_ticker, _period, _data_source):
            return pd.DataFrame(), "local_cache_empty", False
        request = {
            "tickers": ["AAPL"], "universe_mode": "manual", "period": "1y",
            "data_source": "cache_only", "engine_modes": ["official", "v8"],
            "min_history": 90, "max_tests_per_ticker": 3, "bootstrap_samples": 0,
        }
        with (
            patch.object(pattern_lab, "cached_tickers", return_value=[]),
            patch.object(pattern_lab, "_load_history", empty_history),
            patch.object(pattern_lab, "get_ohlcv_cache_size_bytes", return_value=0),
        ):
            result = await pattern_lab.run_pattern_lab(request)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["cache"]["api_fetches"], 0)
        self.assertIn("warm the local cache", result["message"])


if __name__ == "__main__":
    unittest.main()

