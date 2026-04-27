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
    parser = argparse.ArgumentParser(description="手动校对领星 getSummaryList 返回数据")
    parser.add_argument("--env-file", default=".env", help="env 文件路径，默认 .env")
    parser.add_argument("--offset", type=int, default=0, help="分页 offset，默认 0")
    parser.add_argument("--length", type=int, default=5, help="拉取条数，默认 5")
    parser.add_argument("--sid", action="append", default=[], help="指定 sid，可重复传入")
    parser.add_argument("--full", action="store_true", help="打印完整原始记录")
    parser.add_argument("--no-proxy", action="store_true", help="忽略系统代理环境变量")
    return parser.parse_args()


def clear_proxy_env() -> None:
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        os.environ.pop(key, None)


def build_sample(item: dict) -> dict:
    basic = item.get("basic_info") or {}
    suggest = item.get("suggest_info") or {}
    sales_info = item.get("sales_info") or {}
    amazon_quantity_info = item.get("amazon_quantity_info") or ((item.get("data") or {}).get("amazon_quantity_info") or {})

    return {
        "asin": basic.get("asin"),
        "sid": basic.get("sid"),
        "hash_id": basic.get("hash_id"),
        "msku_fnsku_list": basic.get("msku_fnsku_list"),
        "amazon_quantity_info": {
            "amazon_quantity_valid": amazon_quantity_info.get("amazon_quantity_valid"),
            "amazon_quantity_shipping": amazon_quantity_info.get("amazon_quantity_shipping"),
            "afn_fulfillable_quantity": amazon_quantity_info.get("afn_fulfillable_quantity"),
            "reserved_fc_transfers": amazon_quantity_info.get("reserved_fc_transfers"),
            "reserved_fc_processing": amazon_quantity_info.get("reserved_fc_processing"),
        },
        "suggest_info": {
            "available_sale_days_fba": suggest.get("available_sale_days_fba"),
            "fba_available_sale_days": suggest.get("fba_available_sale_days"),
            "out_stock_date": suggest.get("out_stock_date"),
            "estimated_sale_avg_quantity": suggest.get("estimated_sale_avg_quantity"),
        },
        "sales_info": {
            "sales_avg_7": sales_info.get("sales_avg_7"),
            "sales_avg_14": sales_info.get("sales_avg_14"),
            "sales_avg_30": sales_info.get("sales_avg_30"),
        },
    }


async def main() -> None:
    args = parse_args()
    if args.no_proxy:
        clear_proxy_env()

    load_env_file(args.env_file)
    config = load_config()
    sid_list = args.sid or config.lingxing.sid_list

    async with LingxingClient(config.lingxing) as client:
        access_token = await client.fetch_access_token()
        req_body = {
            "sid_list": sid_list,
            "data_type": config.lingxing.data_type,
            "mode": config.lingxing.mode,
            "offset": max(args.offset, 0),
            "length": max(args.length, 1),
        }

        print(f"[debug] request_body={json.dumps(req_body, ensure_ascii=False)}")
        response = await client.request(
            access_token,
            "/erp/sc/routing/restocking/analysis/getSummaryList",
            "POST",
            req_body=req_body,
        )

    items = response.get("data") or []

    print(
        json.dumps(
            {
                "code": response.get("code"),
                "total": response.get("total"),
                "requested_sids": sid_list,
                "count": len(items),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if not items:
        return

    for index, item in enumerate(items, start=1):
        print(f"[sample {index}]")
        print(json.dumps(build_sample(item), ensure_ascii=False, indent=2))

        if args.full:
            print(json.dumps(item, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
