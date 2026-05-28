#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

from .application import run_alert_job
from .dingtalk import DingTalkNotifier
from .lingxing import LingxingClient
from .report import export_alert_report
from .runtime import load_runtime_config
from .utils import resolve_today


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="领星补货建议提醒脚本")
    parser.add_argument("--env-file", default=".env", help="env 文件路径，默认 .env")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不发送钉钉")
    parser.add_argument("--today", default="", help="手动指定今天日期，格式 YYYY-MM-DD")
    parser.add_argument("--schedule", action="store_true", help="常驻运行，每周一 09:00 自动执行")
    parser.add_argument(
        "--scope",
        default="all",
        choices=["all", "us", "ca", "jp", "eu"],
        help="预警范围：all/us/ca/jp/eu，默认 all",
    )
    parser.add_argument(
        "--notify-user-id",
        dest="notify_user_id",
        action="append",
        default=[],
        help="覆盖默认收件人，只发给指定钉钉 userId；可重复传入多个",
    )
    return parser.parse_args()


async def run_once(args: argparse.Namespace) -> int:
    print(f"[main] 加载 env 文件: {args.env_file}")
    config = load_runtime_config(args.env_file, args.dry_run)
    today = resolve_today(args.today)
    print(f"[main] 运行日期: {today.isoformat()}")

    notifier = None if args.dry_run else DingTalkNotifier(config.dingtalk)
    await run_alert_job(
        client=LingxingClient(config.lingxing),
        today=today,
        sid_list=config.lingxing.sid_list,
        exporter=export_alert_report,
        notifier=notifier,
        notify_user_ids=config.dingtalk.user_ids,
        notify_user_override_ids=args.notify_user_id,
        dry_run=args.dry_run,
        scope=args.scope,
        dingtalk_config=config.dingtalk,
    )
    return 0


async def scheduler_main(args: argparse.Namespace) -> int:
    print(f"[scheduler] 加载 env 文件: {args.env_file}")
    config = load_runtime_config(args.env_file, args.dry_run)
    timezone = ZoneInfo(config.timezone)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        partial(run_once, args),
        trigger="cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        id="weekly_libraton_stock_alert",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    print(f"[scheduler] 已启动，每周一 09:00 执行，时区={config.timezone}")
    await asyncio.Event().wait()
    return 0


def main() -> int:
    args = parse_args()
    if args.schedule:
        return asyncio.run(scheduler_main(args))
    return asyncio.run(run_once(args))


if __name__ == "__main__":
    raise SystemExit(main())
