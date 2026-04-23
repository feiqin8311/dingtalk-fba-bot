#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
import json
import os

from fba_alert.config import load_config
from fba_alert.lingxing import LingxingClient
from fba_alert.utils import load_env_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="手动查询领星月度汇率数据")
    parser.add_argument("--env-file", default=".env", help="env 文件路径，默认 .env")
    parser.add_argument("--date", default="2026-04", help="汇率月份，格式 YYYY-MM，默认 2026-04")
    parser.add_argument("--full", action="store_true", help="打印完整原始返回")
    parser.add_argument("--no-proxy", action="store_true", help="忽略系统代理环境变量")
    return parser.parse_args()


def clear_proxy_env() -> None:
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        os.environ.pop(key, None)


def build_sample(response: dict) -> dict:
    data = response.get("data") or []
    if not isinstance(data, list):
        return {
            "month": None,
            "total": response.get("total") or 0,
            "currencies": [],
        }

    return {
        "month": data[0].get("date") if data else None,
        "total": response.get("total") if response.get("total") is not None else len(data),
        "currencies": [
            {
                "code": item.get("code"),
                "icon": item.get("icon"),
                "name": item.get("name"),
                "rate_org": item.get("rate_org"),
                "my_rate": item.get("my_rate"),
                "update_time": item.get("update_time"),
            }
            for item in data
        ],
    }


async def main() -> None:
    args = parse_args()
    if args.no_proxy:
        clear_proxy_env()

    load_env_file(args.env_file)
    config = load_config()

    client = LingxingClient(config.lingxing)
    access_token = await client.fetch_access_token()
    req_body = {
        "date": args.date,
    }

    print(f"[debug] request_body={json.dumps(req_body, ensure_ascii=False)}")
    response = await client.request(
        access_token,
        "/erp/sc/routing/finance/currency/currencyMonth",
        "POST",
        req_body=req_body,
    )

    print(
        json.dumps(
            {
                "code": response.get("code"),
                "message": response.get("message") or response.get("msg"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(json.dumps(build_sample(response), ensure_ascii=False, indent=2))

    if args.full:
        print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
