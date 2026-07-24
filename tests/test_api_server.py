#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import AioHTTPTestCase

from fba_alert.api_server import AlertMode, JobStore, _parse_run_body, create_app
from fba_alert.application import AlertJobResult


class ParseRunBodyTests(unittest.TestCase):
    def test_self_requires_notify_user_ids(self) -> None:
        with self.assertRaises(ValueError):
            _parse_run_body({"scope": "us", "mode": "self"})

    def test_self_keeps_notify_user_ids(self) -> None:
        scope, mode, ids = _parse_run_body(
            {"scope": "us", "mode": "self", "notify_user_ids": ["u1", "u2"]}
        )
        self.assertEqual(scope, "us")
        self.assertEqual(mode, AlertMode.SELF)
        self.assertEqual(ids, ["u1", "u2"])

    def test_broadcast_clears_override_ids(self) -> None:
        scope, mode, ids = _parse_run_body(
            {"scope": "all", "mode": "broadcast", "notify_user_ids": ["u1"]}
        )
        self.assertEqual(scope, "all")
        self.assertEqual(mode, AlertMode.BROADCAST)
        self.assertEqual(ids, [])

    def test_rejects_bad_scope(self) -> None:
        with self.assertRaises(ValueError):
            _parse_run_body({"scope": "mars", "mode": "dry_run"})

    def test_upload_only_does_not_require_notify_user_ids(self) -> None:
        scope, mode, ids = _parse_run_body({"scope": "ezarc", "mode": "upload_only"})
        self.assertEqual(scope, "ezarc")
        self.assertEqual(mode, AlertMode.UPLOAD_ONLY)
        self.assertEqual(ids, [])


class ApiServerTests(AioHTTPTestCase):
    async def get_application(self):
        self.store = JobStore()
        return create_app(env_file=".env", api_token="test-token", store=self.store)

    async def test_health_no_auth(self) -> None:
        resp = await self.client.request("GET", "/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])

    async def test_run_requires_auth(self) -> None:
        resp = await self.client.request(
            "POST",
            "/v1/alerts/run",
            json={"scope": "us", "mode": "dry_run"},
        )
        self.assertEqual(resp.status, 401)

    async def test_run_self_without_user_ids_is_400(self) -> None:
        resp = await self.client.request(
            "POST",
            "/v1/alerts/run",
            json={"scope": "us", "mode": "self"},
            headers={"Authorization": "Bearer test-token"},
        )
        self.assertEqual(resp.status, 400)

    async def test_run_queues_job_and_completes(self) -> None:
        fake_result = AlertJobResult(
            fetched_count=10,
            alert_count=2,
            report_path="reports/x.xlsx",
            sid_distribution={"1": 10},
            preview_url="https://qr.dingtalk.com/page/yunpan?fileId=f1",
            preview_urls={"reports/x.xlsx": "https://qr.dingtalk.com/page/yunpan?fileId=f1"},
        )

        with patch("fba_alert.api_server.load_runtime_config") as load_cfg, patch(
            "fba_alert.api_server.LingxingClient"
        ), patch("fba_alert.api_server.DingTalkNotifier"), patch(
            "fba_alert.api_server.run_alert_job", new_callable=AsyncMock
        ) as run_job:
            load_cfg.return_value = type(
                "Cfg",
                (),
                {
                    "lingxing": type("L", (), {"sid_list": ["1"]})(),
                    "dingtalk": type("D", (), {"user_ids": ["default"]})(),
                },
            )()
            run_job.return_value = fake_result

            resp = await self.client.request(
                "POST",
                "/v1/alerts/run",
                json={
                    "scope": "us",
                    "mode": "self",
                    "notify_user_ids": ["asker-1"],
                },
                headers={"Authorization": "Bearer test-token"},
            )
            self.assertEqual(resp.status, 202)
            body = await resp.json()
            job_id = body["job_id"]
            self.assertEqual(body["status"], "queued")

            # Wait for background task
            for _ in range(50):
                job = await self.store.get(job_id)
                if job and job.status in {"done", "failed"}:
                    break
                await asyncio.sleep(0.02)

            job = await self.store.get(job_id)
            assert job is not None
            self.assertEqual(job.status, "done")
            self.assertEqual(job.result["alert_count"], 2)
            self.assertEqual(
                job.result["preview_url"],
                "https://qr.dingtalk.com/page/yunpan?fileId=f1",
            )

            get_resp = await self.client.request(
                "GET",
                f"/v1/alerts/jobs/{job_id}",
                headers={"Authorization": "Bearer test-token"},
            )
            self.assertEqual(get_resp.status, 200)
            get_body = await get_resp.json()
            self.assertEqual(get_body["status"], "done")
            self.assertEqual(
                get_body["result"]["preview_url"],
                "https://qr.dingtalk.com/page/yunpan?fileId=f1",
            )

            # self mode must pass override user ids into run_alert_job
            kwargs = run_job.await_args.kwargs
            self.assertEqual(kwargs["notify_user_override_ids"], ["asker-1"])
            self.assertEqual(kwargs["scope"], "us")
            self.assertFalse(kwargs["dry_run"])


if __name__ == "__main__":
    unittest.main()
