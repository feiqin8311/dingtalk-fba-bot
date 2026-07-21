import argparse
import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, patch


class SchedulerMainTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_runs_all_brands_in_order_every_monday(self) -> None:
        from fba_alert import main as main_module

        args = argparse.Namespace(
            env_file=".env",
            dry_run=False,
            today="",
            schedule=True,
            scope="all",
            no_api=False,
            api_host="0.0.0.0",
            api_port=8090,
            notify_user_id=[],
            upload_only=False,
        )
        captured: list[tuple[object, dict[str, object]]] = []
        scopes: list[str] = []
        api_started: list[tuple[str, str, int]] = []

        class FakeScheduler:
            def add_job(self, func, **kwargs) -> None:
                captured.append((func, kwargs))

            def start(self) -> None:
                return None

        class FakeEvent:
            async def wait(self) -> None:
                return None

        async def fake_run_once(scoped_args: argparse.Namespace) -> int:
            scopes.append(scoped_args.scope)
            return 0

        async def fake_start_http_api(env_file: str, host: str, port: int):
            api_started.append((env_file, host, port))

            class Runner:
                async def cleanup(self) -> None:
                    return None

            return Runner()

        fake_config = type("Cfg", (), {"timezone": "Asia/Shanghai"})()

        with patch.object(main_module, "load_runtime_config", return_value=fake_config), patch.object(
            main_module, "AsyncIOScheduler", return_value=FakeScheduler()
        ), patch.object(main_module.asyncio, "Event", return_value=FakeEvent()), patch.object(
            main_module, "run_once", new=fake_run_once
        ), patch.object(main_module, "start_http_api", new=fake_start_http_api):
            result = await main_module.scheduler_main(args)
            await captured[0][0]()

        self.assertEqual(result, 0)
        self.assertEqual(scopes, ["all", "ezarc", "yplus"])
        self.assertEqual(len(captured), 1)
        self.assertEqual(api_started, [(".env", "0.0.0.0", 8090)])
        _, kwargs = captured[0]
        self.assertEqual(kwargs["trigger"], "cron")
        self.assertEqual(kwargs["day_of_week"], "mon")
        self.assertEqual(kwargs["hour"], 9)
        self.assertEqual(kwargs["minute"], 0)
        self.assertEqual(kwargs["id"], "weekly_stock_alerts")

    async def test_scheduler_skips_api_when_no_api(self) -> None:
        from fba_alert import main as main_module

        args = argparse.Namespace(
            env_file=".env",
            dry_run=False,
            today="",
            schedule=True,
            scope="all",
            no_api=True,
            api_host="0.0.0.0",
            api_port=8090,
            notify_user_id=[],
            upload_only=False,
        )

        class FakeScheduler:
            def add_job(self, func, **kwargs) -> None:
                return None

            def start(self) -> None:
                return None

        class FakeEvent:
            async def wait(self) -> None:
                return None

        started: list[bool] = []

        async def fake_start_http_api(*_a, **_k):
            started.append(True)
            return None

        fake_config = type("Cfg", (), {"timezone": "Asia/Shanghai"})()
        with patch.object(main_module, "load_runtime_config", return_value=fake_config), patch.object(
            main_module, "AsyncIOScheduler", return_value=FakeScheduler()
        ), patch.object(main_module.asyncio, "Event", return_value=FakeEvent()), patch.object(
            main_module, "start_http_api", new=fake_start_http_api
        ):
            result = await main_module.scheduler_main(args)

        self.assertEqual(result, 0)
        self.assertEqual(started, [])


class ParseArgsTests(unittest.TestCase):
    def test_parse_args_accepts_brand_scopes(self) -> None:
        from fba_alert.main import parse_args

        with patch.object(sys, "argv", ["prog", "--scope", "ezarc"]):
            ezarc_args = parse_args()
        with patch.object(sys, "argv", ["prog", "--scope", "yplus"]):
            yplus_args = parse_args()

        self.assertEqual(ezarc_args.scope, "ezarc")
        self.assertEqual(yplus_args.scope, "yplus")

    def test_parse_args_reads_notify_user_id_override(self) -> None:
        from fba_alert.main import parse_args

        with patch.object(
            sys,
            "argv",
            ["prog", "--scope", "us", "--notify-user-id", "user-1", "--notify-user-id", "user-2"],
        ):
            args = parse_args()

        self.assertEqual(args.scope, "us")
        self.assertEqual(args.notify_user_id, ["user-1", "user-2"])

    def test_parse_args_schedule_api_flags(self) -> None:
        from fba_alert.main import parse_args

        with patch.object(sys, "argv", ["prog", "--schedule", "--no-api", "--api-port", "9001"]):
            args = parse_args()
        self.assertTrue(args.schedule)
        self.assertTrue(args.no_api)
        self.assertEqual(args.api_port, 9001)


if __name__ == "__main__":
    unittest.main()
