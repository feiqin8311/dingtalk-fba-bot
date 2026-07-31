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
from .application import run_ingest_job
from .lingxing import LingxingClient
from .runtime import load_runtime_config
from .utils import resolve_today


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FBA 库存指标入库（写 fact_bi_amazon_fba_metric）")
    parser.add_argument("--env-file", default=".env", help="env 文件路径，默认 .env")
    parser.add_argument("--dry-run", action="store_true", help="只拉取并打印，不写库")
    parser.add_argument("--today", default="", help="手动指定业务日，格式 YYYY-MM-DD")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="常驻：工作日 09:00 入库；同进程监听 HTTP API",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="与 --schedule 合用时不启 HTTP API",
    )
    parser.add_argument(
        "--api-host",
        default=os.getenv("FBA_ALERT_API_HOST", "0.0.0.0"),
        help="HTTP API bind host",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=int(os.getenv("FBA_ALERT_API_PORT", "8090")),
        help="HTTP API port",
    )
    parser.add_argument(
        "--scope",
        default="libraton",
        choices=["libraton", "all", "us", "ca", "jp", "eu", "ezarc", "yplus", "ezarc-test", "yplus-test"],
        help="入库范围，默认 libraton（all 为兼容别名）",
    )
    return parser.parse_args()


async def run_once(args: argparse.Namespace) -> int:
    print(f"[main] 加载 env 文件: {args.env_file}")
    config = load_runtime_config(args.env_file, args.dry_run)
    today = resolve_today(args.today)
    print(f"[main] 运行日期: {today.isoformat()} scope={args.scope}")

    await run_ingest_job(
        client=LingxingClient(config.lingxing),
        today=today,
        sid_list=config.lingxing.sid_list,
        db_config=config.db,
        scope=args.scope,
        dry_run=args.dry_run,
    )
    return 0


async def run_scheduled_ingest(args: argparse.Namespace) -> None:
    scopes = ("libraton", "ezarc", "yplus")
    for index, scope in enumerate(scopes):
        try:
            await run_once(argparse.Namespace(**{**vars(args), "scope": scope}))
        except Exception as exc:
            print(f"[scheduler] scope={scope} failed, continue: {exc!r}")
        if index < len(scopes) - 1:
            await asyncio.sleep(10)


async def start_http_api(env_file: str, host: str, port: int) -> web.AppRunner:
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
    config = load_runtime_config(args.env_file, True)
    timezone = ZoneInfo(config.timezone)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        partial(run_scheduled_ingest, args),
        trigger="cron",
        day_of_week="mon-fri",
        hour=9,
        minute=0,
        id="weekday_fba_metric_ingest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    print(
        f"[scheduler] 已启动，工作日 09:00 依次入库 Libraton/EZARC/YPLUS；时区={config.timezone}"
    )

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
