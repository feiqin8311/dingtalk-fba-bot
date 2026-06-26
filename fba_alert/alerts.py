#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import date
from typing import Optional

from .models import AlertRecord
from .lingxing import InventorySnapshot
from .store_policies import get_store_policy
from .utils import calc_out_stock_days, safe_float, safe_int, unique_keep_order


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


def build_msku_reason_list(records: list[AlertRecord], level: str) -> list[str]:
    reason_map: dict[str, list[str]] = {}
    for item in records:
        if item.level != level:
            continue
        for msku in item.mskus:
            bucket = reason_map.setdefault(msku, [])
            for reason in item.reasons:
                if reason not in bucket:
                    bucket.append(reason)
    return [f"{msku}（命中{len(reasons)}条：{'；'.join(reasons)}）" for msku, reasons in reason_map.items()]


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


def apply_listing_contacts(records: list[AlertRecord], contact_map: dict[tuple[str, str], str]) -> None:
    for record in records:
        record.listing_contacts = contact_map.get((record.sid, record.asin), "")


def build_inventory_days(snapshot: InventorySnapshot, summary_daily_sales: float, today: date) -> tuple[int, int, str, int]:
    if summary_daily_sales <= 0:
        return -1, -1, "", -1

    fba_days = int(snapshot.fba_inventory / summary_daily_sales)
    fba_plus_days = int((snapshot.fba_inventory + snapshot.fba_inbound_inventory) / summary_daily_sales)
    out_stock_days = fba_days
    out_stock_date = ""
    if out_stock_days > 0:
        out_stock_date = date.fromordinal(today.toordinal() + out_stock_days).isoformat()
    return fba_days, fba_plus_days, out_stock_date, out_stock_days


def has_value(value: object) -> bool:
    return value not in (None, "")


def classify_record(
    item: dict,
    today: date,
    seller_map: dict[str, str],
    allowed_sids: set[str],
    inventory_snapshot_map: Optional[dict[tuple[str, str], InventorySnapshot]] = None,
) -> Optional[AlertRecord]:
    basic = item.get("basic_info") or {}
    suggest = item.get("suggest_info") or {}
    sales_info = item.get("sales_info") or {}
    ext_info = item.get("ext_info") or {}
    data = item.get("data") or {}
    amazon_quantity_info = data.get("amazon_quantity_info") or {}

    if safe_int(ext_info.get("restock_status")) == 1:
        return None

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
            fba_inventory = inventory_snapshot.fba_inventory
        if not has_value(summary_fba_inbound_inventory_raw):
            fba_inbound_inventory = inventory_snapshot.fba_inbound_inventory
        if not has_value(summary_fba_sellable_inventory_raw):
            fba_sellable_inventory = inventory_snapshot.fba_sellable_inventory
        if not has_value(summary_fba_transfer_reserved_inventory_raw):
            fba_transfer_reserved_inventory = inventory_snapshot.fba_transfer_reserved_inventory
        if not has_value(summary_fba_processing_inventory_raw):
            fba_processing_inventory = inventory_snapshot.fba_processing_inventory
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
    thresholds = get_store_policy(seller_name).alert_thresholds

    level = ""
    reasons: list[str] = []
    if fba_inventory == 0 and fba_inbound_inventory > 0:
        level = "C"
        reasons.append(f"FBA库存=0 且 FBA在途={fba_inbound_inventory}")
    else:
        if thresholds["a_fba_days"] is not None and 0 < fba_days <= thresholds["a_fba_days"]:
            reasons.append(f"可售天数(FBA)={fba_days}天")
        if thresholds["a_fba_plus_days"] is not None and 0 < fba_plus_days <= thresholds["a_fba_plus_days"]:
            reasons.append(f"可售天数(FBA+在途)={fba_plus_days}天")
        if thresholds["a_out_stock_days"] is not None and 0 < out_stock_days <= thresholds["a_out_stock_days"]:
            reasons.append(f"断货时间(天数)={out_stock_days}天")
        if reasons:
            level = "A"
        else:
            if thresholds["b_fba_days"] is not None and 0 < fba_days <= thresholds["b_fba_days"]:
                reasons.append(f"可售天数(FBA)={fba_days}天")
            if (
                thresholds["b_equal_out_stock_days"] is not None
                and 0 < fba_days <= thresholds["b_equal_out_stock_days"]
                and fba_days == out_stock_days
            ):
                reasons.append(f"可售天数(FBA)=断货时间(天数)={fba_days}天")
            if thresholds["b_fba_plus_days"] is not None and 0 < fba_plus_days <= thresholds["b_fba_plus_days"]:
                reasons.append(f"可售天数(FBA+在途)={fba_plus_days}天")
            if reasons:
                level = "B"

    if not level:
        return None

    return AlertRecord(
        level=level,
        reasons=unique_keep_order(reasons),
        asin=asin,
        sid=sid,
        seller_name=seller_name,
        node_type=safe_int(basic.get("node_type")),
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
        hash_id=hash_id,
    )


def parse_summary_items(
    items: list[dict],
    today: date,
    seller_map: dict[str, str],
    sid_list: list[str],
    inventory_snapshot_map: Optional[dict[tuple[str, str], InventorySnapshot]] = None,
) -> list[AlertRecord]:
    records: list[AlertRecord] = []
    seen_hash_ids: set[str] = set()
    allowed_sids = set(sid_list)
    for item in items:
        record = classify_record(item, today, seller_map, allowed_sids, inventory_snapshot_map)
        if record and record.hash_id not in seen_hash_ids:
            seen_hash_ids.add(record.hash_id)
            records.append(record)
    records.sort(key=lambda row: (row.level, row.out_stock_days if row.out_stock_days > 0 else 10**9, row.fba_days, row.asin))
    return records


def build_message(alerts: list[AlertRecord], today: date, sid_list: list[str], seller_map: dict[str, str]) -> str:
    title = "LIBRATON库存预警（欧洲）"
    ordered_sellers: list[tuple[str, str]] = []
    seen_sids: set[str] = set()
    for item in alerts:
        if item.sid not in seen_sids:
            seen_sids.add(item.sid)
            ordered_sellers.append((item.sid, item.seller_name))

    for sid in sid_list:
        if sid not in seen_sids:
            ordered_sellers.append((sid, seller_map.get(sid, sid)))

    lines = [f"## {title}", f"> 日期：{today.isoformat()}", ""]
    for index, (sid, seller_name) in enumerate(ordered_sellers, start=1):
        seller_alerts = [item for item in alerts if item.sid == sid]
        a_mskus = unique_keep_order([msku for item in seller_alerts if item.level == "A" for msku in item.mskus])
        b_mskus = unique_keep_order([msku for item in seller_alerts if item.level == "B" for msku in item.mskus])
        c_mskus = unique_keep_order([msku for item in seller_alerts if item.level == "C" for msku in item.mskus])
        a_reason_list = build_msku_reason_list(seller_alerts, "A")
        b_reason_list = build_msku_reason_list(seller_alerts, "B")
        c_reason_list = build_msku_reason_list(seller_alerts, "C")
        lines.append(f"### 店铺{index}：{seller_name}")
        lines.append(f"- A级提醒 MSKU（{len(a_mskus)}）：{', '.join(a_mskus) if a_mskus else '无'}")
        lines.append(f"- A级命中规则：{'，'.join(a_reason_list) if a_reason_list else '无'}")
        lines.append(f"- B级提醒 MSKU（{len(b_mskus)}）：{', '.join(b_mskus) if b_mskus else '无'}")
        lines.append(f"- B级命中规则：{'，'.join(b_reason_list) if b_reason_list else '无'}")
        lines.append(f"- C级提醒 MSKU（{len(c_mskus)}）：{', '.join(c_mskus) if c_mskus else '无'}")
        lines.append(f"- C级命中规则：{'，'.join(c_reason_list) if c_reason_list else '无'}")
        lines.append("")
    return "\n".join(lines)
