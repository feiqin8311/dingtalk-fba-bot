#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass


@dataclass
class MetricRecord:
    """FBA 原始指标行（写入 fact_bi_amazon_fba_metric，不含等级）。"""

    brand: str
    site: str
    store: str
    asin: str
    sid: str
    mskus: list[str]
    listing_contacts: str
    fba_plus_days: int
    fba_days: int
    fba_inventory: int
    fba_inbound_inventory: int
    fba_sellable_inventory: int
    fba_transfer_reserved_inventory: int
    fba_processing_inventory: int
    summary_daily_sales: float
    out_stock_date: str
    out_stock_days: int
    restock_status: int | None
    hash_id: str
