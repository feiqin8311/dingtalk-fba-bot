import argparse
import importlib
import sys
import types
import unittest
from unittest.mock import patch


class SchedulerMainTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_runs_all_brands_in_order_every_monday(self) -> None:
        args = argparse.Namespace(env_file=".env", dry_run=False, today="", schedule=True, scope="all")
        captured: list[tuple[object, dict[str, object]]] = []
        scopes: list[str] = []

        for module_name in [
            "fba_alert.application",
            "fba_alert.dingtalk",
            "fba_alert.lingxing",
            "fba_alert.report",
            "fba_alert.runtime",
            "fba_alert.utils",
        ]:
            sys.modules.pop(module_name, None)

        sys.modules["fba_alert.application"] = types.SimpleNamespace(run_alert_job=object())
        sys.modules["fba_alert.dingtalk"] = types.SimpleNamespace(DingTalkNotifier=object())
        sys.modules["fba_alert.lingxing"] = types.SimpleNamespace(LingxingClient=object())
        sys.modules["fba_alert.report"] = types.SimpleNamespace(export_alert_report=object())
        sys.modules["fba_alert.runtime"] = types.SimpleNamespace(load_runtime_config=object())
        sys.modules["fba_alert.utils"] = types.SimpleNamespace(resolve_today=object())

        apscheduler_module = types.ModuleType("apscheduler")
        schedulers_module = types.ModuleType("apscheduler.schedulers")
        asyncio_module = types.ModuleType("apscheduler.schedulers.asyncio")
        asyncio_module.AsyncIOScheduler = object()
        sys.modules["apscheduler"] = apscheduler_module
        sys.modules["apscheduler.schedulers"] = schedulers_module
        sys.modules["apscheduler.schedulers.asyncio"] = asyncio_module

        main_module = importlib.import_module("fba_alert.main")
        main_module = importlib.reload(main_module)

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

        fake_config = types.SimpleNamespace(timezone="Asia/Shanghai")

        with patch.object(main_module, "load_runtime_config", return_value=fake_config), patch.object(
            main_module, "AsyncIOScheduler", return_value=FakeScheduler()
        ), patch.object(main_module.asyncio, "Event", return_value=FakeEvent()), patch.object(
            main_module, "run_once", new=fake_run_once
        ):
            result = await main_module.scheduler_main(args)
            await captured[0][0]()

        self.assertEqual(result, 0)
        self.assertEqual(scopes, ["all", "ezarc", "yplus"])
        self.assertEqual(len(captured), 1)
        _, kwargs = captured[0]
        self.assertEqual(kwargs["trigger"], "cron")
        self.assertEqual(kwargs["day_of_week"], "mon")
        self.assertEqual(kwargs["hour"], 9)
        self.assertEqual(kwargs["minute"], 0)
        self.assertEqual(kwargs["id"], "weekly_stock_alerts")


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


if __name__ == "__main__":
    unittest.main()
