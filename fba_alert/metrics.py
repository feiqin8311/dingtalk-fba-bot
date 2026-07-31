#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""从领星 summary + SourceList 抽出原始指标（不判 A/B/C）。"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .models import MetricRecord
from .utils import calc_out_stock_days, safe_float, safe_int, unique_keep_order

_SITE_RE = re.compile(r"(?:-|\s)(US|CA|UK|DE|FR|IT|ES|NL|SE|PL|BE|IE|TR|JP|MX)\b", re.I)


def is_primary_msku(msku: str) -> bool:
    value = normalize_msku(msku).lower()
    if not value:
        return False
    return not value.startswith("amzn.gr.")


def normalize_msku(msku: str) -> str:
    return (msku or "").strip().rstrip(",").strip()


def collapse_msku_variants(mskus: list[str]) -> list[str]:
    ordered = unique_keep_order([normalize_msku(msku) for msku in mskus if normalize_msku(msku)])
    canonical_lower = {msku.lower() for msku in ordered}
    result: list[str] = []
    for msku in ordered:
        lowered = msku.lower()
        if lowered.endswith("-m") and lowered[:-2] in canonical_lower:
            continue
        result.append(msku)
    return result


def resolve_brand(store: str) -> str:
    text = (store or "").strip()
    upper = text.upper()
    if upper.startswith("EZARC") or upper.startswith("CBT-F") or "CBT-F" in upper:
        return "EZARC"
    if upper.startswith("YPLUS") or upper.startswith("TRAILFUN"):
        return "YPLUS"
    if upper.startswith("LIBRATON"):
        return "LIBRATON"
    return ""


def resolve_site(store: str) -> str:
    text = (store or "").strip()
    upper = text.upper()
    if "汇总" in text and "JP" in upper:
        return "JP"
    match = _SITE_RE.search(text)
    if match:
        return match.group(1).upper()
    if " JP" in f" {upper}" or upper.endswith("JP"):
        return "JP"
    if "EU" in upper:
        return "EU"
    return ""


def format_restock_status(status: int | None) -> str:
    if status == 0:
        return "正常补货"
    if status == 1:
        return "暂不补货"
    return ""


def format_msku_text(mskus: list[str]) -> str:
    return "、".join(sorted(unique_keep_order([normalize_msku(m) for m in mskus if normalize_msku(m)])))


def has_value(value: object) -> bool:
    return value not in (None, "")


def build_inventory_days(snapshot: object, summary_daily_sales: float, today: date) -> tuple[int, int, str, int]:
    if summary_daily_sales <= 0:
        return -1, -1, "", -1
    fba_inventory = safe_int(getattr(snapshot, "fba_inventory", 0))
    fba_inbound = safe_int(getattr(snapshot, "fba_inbound_inventory", 0))
    fba_days = int(fba_inventory / summary_daily_sales)
    fba_plus_days = int((fba_inventory + fba_inbound) / summary_daily_sales)
    out_stock_days = fba_days
    out_stock_date = ""
    if out_stock_days > 0:
        out_stock_date = date.fromordinal(today.toordinal() + out_stock_days).isoformat()
    return fba_days, fba_plus_days, out_stock_date, out_stock_days


def extract_metric_record(
    item: dict,
    today: date,
    seller_map: dict[str, str],
    allowed_sids: set[str],
    inventory_snapshot_map: Optional[dict[tuple[str, str], object]] = None,
) -> Optional[MetricRecord]:
    basic = item.get("basic_info") or {}
    suggest = item.get("suggest_info") or {}
    ext_info = item.get("ext_info") or {}
    data = item.get("data") or {}
    amazon_quantity_info = data.get("amazon_quantity_info") or {}

    asin = (basic.get("asin") or "").strip()
    hash_id = (basic.get("hash_id") or "").strip()
    sid = str(basic.get("sid") or "").strip()
    if not asin or not hash_id:
        return None
    if sid not in allowed_sids:
        return None

    inventory_snapshot = (inventory_snapshot_map or {}).get((sid, asin))
    mskus = collapse_msku_variants(
        [
            normalize_msku(str(row.get("msku") or ""))
            for row in (basic.get("msku_fnsku_list") or [])
            if is_primary_msku(str(row.get("msku") or ""))
        ]
    )
    summary_daily_sales = round(safe_float(suggest.get("estimated_sale_avg_quantity")), 2)
    summary_fba_inventory_raw = amazon_quantity_info.get("amazon_quantity_valid")
    summary_fba_inbound_inventory_raw = amazon_quantity_info.get("amazon_quantity_shipping")
    summary_fba_sellable_inventory_raw = amazon_quantity_info.get("afn_fulfillable_quantity")
    summary_fba_transfer_reserved_inventory_raw = amazon_quantity_info.get("reserved_fc_transfers")
    summary_fba_processing_inventory_raw = amazon_quantity_info.get("reserved_fc_processing")
    summary_fba_plus_days = safe_int(suggest.get("fba_available_sale_days"))
    summary_fba_days = safe_int(suggest.get("available_sale_days_fba"))
    summary_out_stock_date = str(suggest.get("out_stock_date") or "").strip()
    summary_out_stock_days = calc_out_stock_days(summary_out_stock_date, today)
    restock_status_raw = ext_info.get("restock_status")
    restock_status = None if restock_status_raw in (None, "") else safe_int(restock_status_raw)

    fba_plus_days = summary_fba_plus_days
    fba_days = summary_fba_days
    fba_inventory = safe_int(summary_fba_inventory_raw)
    fba_inbound_inventory = safe_int(summary_fba_inbound_inventory_raw)
    fba_sellable_inventory = safe_int(summary_fba_sellable_inventory_raw)
    fba_transfer_reserved_inventory = safe_int(summary_fba_transfer_reserved_inventory_raw)
    fba_processing_inventory = safe_int(summary_fba_processing_inventory_raw)
    out_stock_date = summary_out_stock_date
    out_stock_days = summary_out_stock_days

    if inventory_snapshot is not None:
        if not has_value(summary_fba_inventory_raw):
            fba_inventory = safe_int(getattr(inventory_snapshot, "fba_inventory", 0))
        if not has_value(summary_fba_inbound_inventory_raw):
            fba_inbound_inventory = safe_int(getattr(inventory_snapshot, "fba_inbound_inventory", 0))
        if not has_value(summary_fba_sellable_inventory_raw):
            fba_sellable_inventory = safe_int(getattr(inventory_snapshot, "fba_sellable_inventory", 0))
        if not has_value(summary_fba_transfer_reserved_inventory_raw):
            fba_transfer_reserved_inventory = safe_int(
                getattr(inventory_snapshot, "fba_transfer_reserved_inventory", 0)
            )
        if not has_value(summary_fba_processing_inventory_raw):
            fba_processing_inventory = safe_int(getattr(inventory_snapshot, "fba_processing_inventory", 0))
        if not has_value(suggest.get("available_sale_days_fba")) or not has_value(suggest.get("fba_available_sale_days")):
            fallback_fba_days, fallback_fba_plus_days, fallback_out_stock_date, fallback_out_stock_days = build_inventory_days(
                inventory_snapshot,
                summary_daily_sales,
                today,
            )
            if fallback_fba_days >= 0:
                if not has_value(suggest.get("available_sale_days_fba")):
                    fba_days = fallback_fba_days
                if not has_value(suggest.get("fba_available_sale_days")):
                    fba_plus_days = fallback_fba_plus_days
                if not has_value(suggest.get("out_stock_date")):
                    out_stock_date = fallback_out_stock_date
                    out_stock_days = fallback_out_stock_days

    seller_name = seller_map.get(sid, sid)
    brand = resolve_brand(seller_name)
    site = resolve_site(seller_name)
    return MetricRecord(
        brand=brand,
        site=site,
        store=seller_name,
        asin=asin,
        sid=sid,
        mskus=mskus,
        listing_contacts="",
        fba_plus_days=fba_plus_days,
        fba_days=fba_days,
        fba_inventory=fba_inventory,
        fba_inbound_inventory=fba_inbound_inventory,
        fba_sellable_inventory=fba_sellable_inventory,
        fba_transfer_reserved_inventory=fba_transfer_reserved_inventory,
        fba_processing_inventory=fba_processing_inventory,
        summary_daily_sales=summary_daily_sales,
        out_stock_date=out_stock_date,
        out_stock_days=out_stock_days,
        restock_status=restock_status,
        hash_id=hash_id,
    )


def parse_metric_items(
    items: list[dict],
    today: date,
    seller_map: dict[str, str],
    sid_list: list[str],
    inventory_snapshot_map: Optional[dict[tuple[str, str], object]] = None,
) -> list[MetricRecord]:
    records: list[MetricRecord] = []
    seen_hash_ids: set[str] = set()
    allowed_sids = set(sid_list)
    for item in items:
        record = extract_metric_record(item, today, seller_map, allowed_sids, inventory_snapshot_map)
        if record and record.hash_id not in seen_hash_ids:
            seen_hash_ids.add(record.hash_id)
            records.append(record)
    return records


def build_listing_contact_map(items: list[dict]) -> dict[tuple[str, str], str]:
    contact_map: dict[tuple[str, str], list[str]] = {}
    for item in items:
        sid = str(item.get("sid") or "").strip()
        asin = str(item.get("asin") or "").strip()
        if not sid or not asin:
            continue
        key = (sid, asin)
        bucket = contact_map.setdefault(key, [])
        for principal in item.get("principal_info") or []:
            name = str((principal or {}).get("principal_name") or "").strip()
            if name and name not in bucket:
                bucket.append(name)
    return {key: ", ".join(names) for key, names in contact_map.items()}


def apply_listing_contacts(records: list[MetricRecord], contact_map: dict[tuple[str, str], str]) -> None:
    for record in records:
        record.listing_contacts = contact_map.get((record.sid, record.asin), record.listing_contacts or "")


def merge_ezarc_jp_metrics(
    raw_items: list[dict],
    metrics: list[MetricRecord],
    today: date,
    seller_map: dict[str, str],
    allowed_sids: set[str],
    inventory_snapshot_map: dict[tuple[str, str], object],
    *,
    enabled: bool,
) -> list[MetricRecord]:
    """EZARC 日本两店按 ASIN 汇总为「EZARC JP 汇总」指标行（不判级）。"""
    if not enabled:
        return metrics

    jp_sellers = {"EZARC JP-JP", "CBT-F Tools-JP"}
    merged = [row for row in metrics if row.store not in jp_sellers]
    jp_bucket: dict[str, list[dict]] = {}

    for item in raw_items:
        basic = item.get("basic_info") or {}
        sid = str(basic.get("sid") or "").strip()
        asin = str(basic.get("asin") or "").strip()
        seller_name = seller_map.get(sid, sid)
        if sid not in allowed_sids or seller_name not in jp_sellers or not asin:
            continue

        suggest = item.get("suggest_info") or {}
        ext_info = item.get("ext_info") or {}
        restock_status_raw = ext_info.get("restock_status")
        restock_status = None if restock_status_raw in (None, "") else safe_int(restock_status_raw)
        amazon_quantity_info = ((item.get("data") or {}).get("amazon_quantity_info") or {})
        inventory_snapshot = inventory_snapshot_map.get((sid, asin))
        if inventory_snapshot is None:
            fba_inventory = safe_int(amazon_quantity_info.get("amazon_quantity_valid"))
            fba_inbound_inventory = safe_int(amazon_quantity_info.get("amazon_quantity_shipping"))
            fba_sellable_inventory = safe_int(amazon_quantity_info.get("afn_fulfillable_quantity"))
            fba_transfer_reserved_inventory = safe_int(amazon_quantity_info.get("reserved_fc_transfers"))
            fba_processing_inventory = safe_int(amazon_quantity_info.get("reserved_fc_processing"))
        else:
            fba_inventory = safe_int(getattr(inventory_snapshot, "fba_inventory", 0))
            fba_inbound_inventory = safe_int(getattr(inventory_snapshot, "fba_inbound_inventory", 0))
            fba_sellable_inventory = safe_int(getattr(inventory_snapshot, "fba_sellable_inventory", 0))
            fba_transfer_reserved_inventory = safe_int(
                getattr(inventory_snapshot, "fba_transfer_reserved_inventory", 0)
            )
            fba_processing_inventory = safe_int(getattr(inventory_snapshot, "fba_processing_inventory", 0))

        mskus = collapse_msku_variants(
            [
                normalize_msku(str(row.get("msku") or ""))
                for row in (basic.get("msku_fnsku_list") or [])
                if is_primary_msku(str(row.get("msku") or ""))
            ]
        )
        jp_bucket.setdefault(asin, []).append(
            {
                "asin": asin,
                "sid": sid,
                "mskus": mskus,
                "summary_daily_sales": round(safe_float(suggest.get("estimated_sale_avg_quantity")), 2),
                "fba_inventory": fba_inventory,
                "fba_inbound_inventory": fba_inbound_inventory,
                "fba_sellable_inventory": fba_sellable_inventory,
                "fba_transfer_reserved_inventory": fba_transfer_reserved_inventory,
                "fba_processing_inventory": fba_processing_inventory,
                "restock_status": restock_status,
            }
        )

    for asin, items in jp_bucket.items():
        total_daily_sales = round(sum(item["summary_daily_sales"] for item in items), 2)
        total_fba_inventory = sum(item["fba_inventory"] for item in items)
        total_fba_inbound_inventory = sum(item["fba_inbound_inventory"] for item in items)
        total_fba_sellable_inventory = sum(item["fba_sellable_inventory"] for item in items)
        total_fba_transfer_reserved_inventory = sum(item["fba_transfer_reserved_inventory"] for item in items)
        total_fba_processing_inventory = sum(item["fba_processing_inventory"] for item in items)
        fba_days = int(total_fba_inventory / total_daily_sales) if total_daily_sales > 0 else 0
        fba_plus_days = (
            int((total_fba_inventory + total_fba_inbound_inventory) / total_daily_sales) if total_daily_sales > 0 else 0
        )
        out_stock_days = fba_days
        out_stock_date = ""
        if out_stock_days > 0:
            out_stock_date = date.fromordinal(today.toordinal() + out_stock_days).isoformat()
        first = items[0]
        restock_status = 1 if any(item["restock_status"] == 1 for item in items) else 0
        merged_mskus = unique_keep_order([msku for item in items for msku in item["mskus"]])
        store = "EZARC JP 汇总"
        merged.append(
            MetricRecord(
                brand="EZARC",
                site="JP",
                store=store,
                asin=asin,
                sid=str(first["sid"]),
                mskus=merged_mskus,
                listing_contacts="",
                fba_plus_days=fba_plus_days,
                fba_days=fba_days,
                fba_inventory=total_fba_inventory,
                fba_inbound_inventory=total_fba_inbound_inventory,
                fba_sellable_inventory=total_fba_sellable_inventory,
                fba_transfer_reserved_inventory=total_fba_transfer_reserved_inventory,
                fba_processing_inventory=total_fba_processing_inventory,
                summary_daily_sales=total_daily_sales,
                out_stock_date=out_stock_date,
                out_stock_days=out_stock_days,
                restock_status=restock_status,
                hash_id=f"ezarc-jp-{asin}",
            )
        )

    merged.sort(key=lambda row: (row.store, row.asin))
    return merged
