#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
import os
from functools import partial

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

from .api_server import create_app
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
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="常驻运行：工作日 09:00 自动执行；仅周一发送钉钉消息，并在同一进程监听 HTTP API",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="与 --schedule 合用时不启 HTTP API（默认 schedule 会启）",
    )
    parser.add_argument(
        "--api-host",
        default=os.getenv("FBA_ALERT_API_HOST", "0.0.0.0"),
        help="HTTP API bind host（默认 FBA_ALERT_API_HOST 或 0.0.0.0）",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=int(os.getenv("FBA_ALERT_API_PORT", "8090")),
        help="HTTP API port（默认 FBA_ALERT_API_PORT 或 8090）",
    )
    parser.add_argument(
        "--scope",
        default="all",
        choices=["all", "us", "ca", "jp", "eu", "ezarc", "yplus", "ezarc-test", "yplus-test"],
        help="预警范围：all/us/ca/jp/eu/ezarc/yplus/ezarc-test/yplus-test，默认 all",
    )
    parser.add_argument("--upload-only", action="store_true", help="只上传钉盘，不发送任何钉钉消息")
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
        upload_only=args.upload_only,
        dingtalk_config=config.dingtalk,
    )
    return 0


async def run_scheduled_alerts(args: argparse.Namespace) -> None:
    upload_only = args.upload_only or resolve_today(args.today).weekday() != 0
    scopes = ("all", "ezarc", "yplus")
    for index, scope in enumerate(scopes):
        try:
            await run_once(argparse.Namespace(**{**vars(args), "scope": scope, "upload_only": upload_only}))
        except Exception as exc:
            # Keep remaining brands running when one scope dies (e.g. Lingxing 3001008).
            print(f"[scheduler] scope={scope} failed, continue: {exc!r}")
        if index < len(scopes) - 1:
            # Cool down between brands to reduce back-to-back rate limits.
            await asyncio.sleep(10)


async def start_http_api(env_file: str, host: str, port: int) -> web.AppRunner:
    """Start aiohttp API in the current event loop (same process as scheduler)."""
    token = os.getenv("FBA_ALERT_API_TOKEN", "").strip()
    if not token:
        print("[api] WARNING: FBA_ALERT_API_TOKEN is empty; authenticated routes will 503")
    app = create_app(env_file=env_file, api_token=token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    print(f"[api] listening on {host}:{port} (same process as scheduler)")
    return runner


async def scheduler_main(args: argparse.Namespace) -> int:
    print(f"[scheduler] 加载 env 文件: {args.env_file}")
    config = load_runtime_config(args.env_file, args.dry_run)
    timezone = ZoneInfo(config.timezone)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        partial(run_scheduled_alerts, args),
        trigger="cron",
        day_of_week="mon-fri",
        hour=9,
        minute=0,
        id="weekday_stock_alerts",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    print(f"[scheduler] 已启动，工作日 09:00 依次执行 Libraton/EZARC/YPLUS；仅周一发送钉钉消息，时区={config.timezone}")

    api_runner: web.AppRunner | None = None
    if not args.no_api:
        api_runner = await start_http_api(args.env_file, args.api_host, args.api_port)
    else:
        print("[api] disabled via --no-api")

    try:
        await asyncio.Event().wait()
    finally:
        if api_runner is not None:
            await api_runner.cleanup()
    return 0


def main() -> int:
    args = parse_args()
    if args.schedule:
        return asyncio.run(scheduler_main(args))
    return asyncio.run(run_once(args))


if __name__ == "__main__":
    raise SystemExit(main())
