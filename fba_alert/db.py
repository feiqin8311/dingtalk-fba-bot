#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""写入 bi_amazon.fact_bi_amazon_fba_metric。"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Sequence

import pymysql

from .config import DbConfig
from .metrics import format_msku_text, format_restock_status
from .models import MetricRecord


def connect(config: DbConfig):
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _out_stock_date(value: str) -> Optional[str]:
    text = (value or "").strip()
    return text[:10] if text else None


def metric_to_row(createdate: date, record: MetricRecord) -> tuple[Any, ...]:
    return (
        createdate.isoformat(),
        record.brand or "",
        record.site or "",
        record.store or "",
        format_msku_text(record.mskus),
        record.asin or "",
        record.listing_contacts or "",
        record.summary_daily_sales,
        record.fba_inventory,
        record.fba_days,
        record.fba_inbound_inventory,
        record.fba_plus_days,
        _out_stock_date(record.out_stock_date),
        record.out_stock_days,
        record.fba_sellable_inventory,
        record.fba_transfer_reserved_inventory,
        record.fba_processing_inventory,
        format_restock_status(record.restock_status),
    )


INSERT_SQL = """
INSERT INTO fact_bi_amazon_fba_metric (
    createdate, brand, site, store, msku, asin, listing_contacts,
    daily_sales, fba_inventory, fba_days, fba_inbound, fba_plus_days,
    out_stock_date, out_stock_days, fba_sellable, fba_transfer, fba_processing,
    restock_status
) VALUES (
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s
)
"""


def _dedupe_identical_pk_rows(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """主键 (createdate, store, asin, msku, restock_status) 完全相同则留最后一条。"""
    by_pk: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    for row in rows:
        # createdate, brand, site, store, msku, asin, listing_contacts, ... restock_status
        by_pk[(row[0], row[3], row[5], row[4], row[17])] = row
    return list(by_pk.values())


def replace_metrics_for_day(
    config: DbConfig,
    createdate: date,
    records: Sequence[MetricRecord],
    *,
    brands: Optional[Sequence[str]] = None,
) -> int:
    """同日按 brand 覆盖写入。brands 为空则覆盖当天全部 brand。"""
    brand_list = sorted({str(b).strip().upper() for b in (brands or []) if str(b).strip()})
    rows = _dedupe_identical_pk_rows([metric_to_row(createdate, r) for r in records])
    conn = connect(config)
    try:
        with conn.cursor() as cur:
            if brand_list:
                placeholders = ", ".join(["%s"] * len(brand_list))
                cur.execute(
                    f"DELETE FROM fact_bi_amazon_fba_metric WHERE createdate = %s AND brand IN ({placeholders})",
                    (createdate.isoformat(), *brand_list),
                )
            else:
                cur.execute(
                    "DELETE FROM fact_bi_amazon_fba_metric WHERE createdate = %s",
                    (createdate.isoformat(),),
                )
            if rows:
                cur.executemany(INSERT_SQL, rows)
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
