#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import time
from typing import Callable, Optional

from .alerts import apply_listing_contacts, build_listing_contact_map, parse_summary_items
from .models import AlertRecord
from .report import build_store_report_path, export_scoped_alert_report
from .scopes import AlertScope, resolve_scope_report_group_name, resolve_scope_sid_list
from .store_policies import (
    resolve_main_report_user_ids,
    resolve_sid_list,
    resolve_store_report_group_name,
    resolve_store_report_user_ids,
)

INVENTORY_SNAPSHOT_CANDIDATE_THRESHOLD = 5


@dataclass(frozen=True)
class AlertJobResult:
    fetched_count: int
    alert_count: int
    report_path: str
    sid_distribution: dict[str, int]


def count_sid_asin_pairs(sid_asin_map: dict[str, set[str]]) -> int:
    return sum(len(asin_set) for asin_set in sid_asin_map.values())

def build_sid_distribution(items: list[dict], allowed_sids: set[str]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for item in items:
        sid = str((item.get("basic_info") or {}).get("sid") or "").strip()
        if sid and sid in allowed_sids:
            distribution[sid] = distribution.get(sid, 0) + 1
    return distribution


def build_sid_asin_map(items: list[dict], allowed_sids: set[str]) -> dict[str, set[str]]:
    sid_asin_map: dict[str, set[str]] = {}
    for item in items:
        basic = item.get("basic_info") or {}
        sid = str(basic.get("sid") or "").strip()
        asin = str(basic.get("asin") or "").strip()
        if sid and asin and sid in allowed_sids:
            sid_asin_map.setdefault(sid, set()).add(asin)
    return sid_asin_map


def build_alert_sid_asin_map(alerts: list[AlertRecord]) -> dict[str, set[str]]:
    sid_asin_map: dict[str, set[str]] = {}
    for alert in alerts:
        sid_asin_map.setdefault(alert.sid, set()).add(alert.asin)
    return sid_asin_map


def build_missing_listing_contact_sid_asin_map(alerts: list[AlertRecord]) -> dict[str, set[str]]:
    sid_asin_map: dict[str, set[str]] = {}
    for alert in alerts:
        if alert.listing_contacts.strip():
            continue
        sid_asin_map.setdefault(alert.sid, set()).add(alert.asin)
    return sid_asin_map


async def refill_missing_listing_contacts(
    client: object,
    access_token: str,
    alerts: list[AlertRecord],
) -> None:
    sid_asin_map = build_missing_listing_contact_sid_asin_map(alerts)
    if not sid_asin_map:
        return

    fetch_listing_item_by_asin = getattr(client, "fetch_listing_item_by_asin", None)
    if not callable(fetch_listing_item_by_asin):
        return

    fallback_items: list[dict] = []
    for sid, asin_set in sid_asin_map.items():
        for asin in sorted(asin_set):
            rows = await fetch_listing_item_by_asin(access_token, sid, asin)
            fallback_items.extend(rows or [])

    if not fallback_items:
        return

    fallback_contact_map = build_listing_contact_map(fallback_items)
    apply_listing_contacts(alerts, fallback_contact_map)


def build_inventory_snapshot_candidate_sid_asin_map(
    items: list[dict],
    prelim_alerts: list[AlertRecord],
    allowed_sids: set[str],
    seller_map: dict[str, str],
) -> dict[str, set[str]]:
    _ = prelim_alerts
    _ = seller_map
    return build_sid_asin_map(items, allowed_sids)


def notify_report(report_path: str, notifier: Optional[object], user_ids: list[str], dry_run: bool) -> None:
    if dry_run:
        print(f"[notify] dry-run 模式，报表已生成: {report_path}")
        return
    if notifier is None:
        raise RuntimeError("非 dry-run 模式必须提供 notifier。")

    for user_id in user_ids:
        print(f"[notify] 发送钉钉文件: user_id={user_id}")
        result = notifier.send_user_file(user_id, report_path)
        print(f"[send] user_id={user_id} result={json.dumps(result, ensure_ascii=False)}")


def build_store_report_paths(report_path: str, alerts: list[AlertRecord], today: date) -> dict[str, str]:
    date_dir = Path(report_path).parent
    store_names = sorted({resolve_store_report_group_name(alert.seller_name) for alert in alerts})
    return {
        store_name: str(build_store_report_path(store_name, today, str(date_dir.parent)))
        for store_name in store_names
    }


def notify_store_reports(
    main_report_path: str,
    alerts: list[AlertRecord],
    today: date,
    notifier: Optional[object],
    fallback_user_ids: list[str],
    dry_run: bool,
) -> None:
    store_report_paths = build_store_report_paths(main_report_path, alerts, today)
    for store_name, store_report_path in store_report_paths.items():
        user_ids = resolve_store_report_user_ids(store_name, fallback_user_ids)
        print(
            "[notify] 店铺分表准备发送: "
            f"store={store_name} user_count={len(user_ids)} path={store_report_path}"
        )
        notify_report(store_report_path, notifier, user_ids, dry_run=dry_run)


async def run_alert_job(
    client: object,
    today: date,
    sid_list: list[str],
    exporter: Optional[Callable[[list[AlertRecord], date], str]] = None,
    notifier: Optional[object] = None,
    notify_user_ids: Optional[list[str]] = None,
    dry_run: bool = False,
    scope: str = "all",
) -> AlertJobResult:
    export_report = exporter or (lambda alerts, current_today: "")
    user_ids = notify_user_ids or []
    try:
        started_at = time.perf_counter()
        scope_value = AlertScope.parse(scope)
        access_token = await client.fetch_access_token()
        seller_map = await client.fetch_seller_map(access_token)
        effective_sid_list = resolve_sid_list(sid_list, seller_map)
        scoped_sid_list = resolve_scope_sid_list(scope_value, effective_sid_list, seller_map)
        allowed_sids = set(scoped_sid_list)
        summary_started_at = time.perf_counter()
        raw_items = await client.fetch_summary_items(access_token, scoped_sid_list)
        print(f"[perf] summary_fetch_seconds={time.perf_counter() - summary_started_at:.2f}")
        sid_distribution = build_sid_distribution(raw_items, allowed_sids)

        raw_filtered_count = sum(sid_distribution.values())
        print(f"[main] 原始返回中命中目标店铺的记录数: {raw_filtered_count}")
        print(f"[main] 目标店铺记录分布: {sid_distribution}")

        inventory_snapshot_candidate_sid_asin_map = build_inventory_snapshot_candidate_sid_asin_map(
            raw_items,
            [],
            allowed_sids,
            seller_map,
        )
        print(
            "[perf] source_list_candidates="
            f"{count_sid_asin_pairs(inventory_snapshot_candidate_sid_asin_map)} "
            f"sids={len(inventory_snapshot_candidate_sid_asin_map)}"
        )
        source_list_started_at = time.perf_counter()
        inventory_snapshot_map = await client.fetch_inventory_snapshot_map(access_token, inventory_snapshot_candidate_sid_asin_map)
        print(
            "[perf] source_list_fetch_seconds="
            f"{time.perf_counter() - source_list_started_at:.2f} "
            f"resolved_pairs={len(inventory_snapshot_map)}"
        )
        print("[main] 开始按规则筛选预警")
        final_classify_started_at = time.perf_counter()
        alerts = parse_summary_items(raw_items, today, seller_map, scoped_sid_list, inventory_snapshot_map)
        print(
            "[perf] final_classify_seconds="
            f"{time.perf_counter() - final_classify_started_at:.2f} alerts={len(alerts)}"
        )
        if alerts:
            listing_candidates = build_alert_sid_asin_map(alerts)
            print(
                "[perf] listing_candidates="
                f"{count_sid_asin_pairs(listing_candidates)} sids={len(listing_candidates)}"
            )
            listing_started_at = time.perf_counter()
            listing_items = await client.fetch_listing_items_by_asins(access_token, build_alert_sid_asin_map(alerts))
            print(
                "[perf] listing_fetch_seconds="
                f"{time.perf_counter() - listing_started_at:.2f} rows={len(listing_items)}"
            )
            contact_map = build_listing_contact_map(listing_items)
            apply_listing_contacts(alerts, contact_map)
            await refill_missing_listing_contacts(client, access_token, alerts)

        print(f"[info] fetched={len(raw_items)} alerts={len(alerts)} dry_run={dry_run}")
        if not alerts:
            print("[info] 未命中任何 A/B 级提醒。")
            print(f"[perf] total_run_seconds={time.perf_counter() - started_at:.2f}")
            return AlertJobResult(
                fetched_count=len(raw_items),
                alert_count=0,
                report_path="",
                sid_distribution=sid_distribution,
            )

        print("[main] 生成 Excel 报表")
        report_started_at = time.perf_counter()
        if scope_value is AlertScope.ALL:
            report_path = export_report(alerts, today)
        else:
            report_group_name = resolve_scope_report_group_name(scope_value)
            report_path = export_scoped_alert_report(alerts, today, report_group_name)
        print(f"[perf] report_export_seconds={time.perf_counter() - report_started_at:.2f}")
        if scope_value is AlertScope.ALL:
            notify_report(report_path, notifier, resolve_main_report_user_ids(user_ids), dry_run=dry_run)
            notify_store_reports(report_path, alerts, today, notifier, user_ids, dry_run=dry_run)
        else:
            report_group_name = resolve_scope_report_group_name(scope_value)
            notify_report(
                report_path,
                notifier,
                resolve_store_report_user_ids(report_group_name, user_ids),
                dry_run=dry_run,
            )
        print(f"[perf] total_run_seconds={time.perf_counter() - started_at:.2f}")
        return AlertJobResult(
            fetched_count=len(raw_items),
            alert_count=len(alerts),
            report_path=report_path,
            sid_distribution=sid_distribution,
        )
    except Exception as exc:
        print(f"[error] run_alert_job_failed error={exc!r}")
        raise
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            maybe_awaitable = close()
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable
