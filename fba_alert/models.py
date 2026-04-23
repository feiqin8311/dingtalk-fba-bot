#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass


@dataclass
class AlertRecord:
    level: str
    reasons: list[str]
    asin: str
    sid: str
    seller_name: str
    node_type: int
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
    hash_id: str
