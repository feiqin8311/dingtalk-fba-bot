#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""拉领星 → 抽出原始指标 → 写入 fact_bi_amazon_fba_metric。不再判级 / Excel / 钉钉。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .config import DbConfig
from .db import replace_metrics_for_day
from .metrics import (
    apply_listing_contacts,
    build_listing_contact_map,
    merge_ezarc_jp_metrics,
    parse_metric_items,
)
from .models import MetricRecord
from .scopes import AlertScope, resolve_scope_sid_list
from .store_policies import resolve_sid_list


@dataclass(frozen=True)
class IngestJobResult:
    fetched_count: int
    metric_count: int
    written_count: int
    sid_distribution: dict[str, int]
    brands: list[str]


def count_sid_asin_pairs(sid_asin_map: dict[str, set[str]]) -> int:
    return sum(len(asin_set) for asin_set in sid_asin_map.values())


def build_summary_fetch_batches(
    scoped_sid_list: list[str], seller_map: dict[str, str]
) -> list[tuple[list[str], int | None]]:
    libraton_sids: list[str] = []
    other_sids: list[str] = []
    for sid in scoped_sid_list:
        seller_name = seller_map.get(sid, "").strip()
        if seller_name.startswith("Libraton "):
            libraton_sids.append(sid)
        else:
            other_sids.append(sid)

    batches: list[tuple[list[str], int | None]] = []
    if libraton_sids:
        batches.append((libraton_sids, 1))
    if other_sids:
        batches.append((other_sids, None))
    return batches


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


def build_metric_sid_asin_map(metrics: list[MetricRecord]) -> dict[str, set[str]]:
    sid_asin_map: dict[str, set[str]] = {}
    for row in metrics:
        if row.sid and row.asin:
            sid_asin_map.setdefault(row.sid, set()).add(row.asin)
    return sid_asin_map


def build_missing_listing_contact_sid_asin_map(metrics: list[MetricRecord]) -> dict[str, set[str]]:
    sid_asin_map: dict[str, set[str]] = {}
    for row in metrics:
        if (row.listing_contacts or "").strip():
            continue
        if row.sid and row.asin:
            sid_asin_map.setdefault(row.sid, set()).add(row.asin)
    return sid_asin_map


async def refill_missing_listing_contacts(
    client: object,
    access_token: str,
    metrics: list[MetricRecord],
) -> None:
    sid_asin_map = build_missing_listing_contact_sid_asin_map(metrics)
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
    apply_listing_contacts(metrics, build_listing_contact_map(fallback_items))


def ensure_ezarc_jp_inventory_candidates(
    sid_asin_map: dict[str, set[str]],
    items: list[dict],
    allowed_sids: set[str],
    seller_map: dict[str, str],
    scope: AlertScope,
) -> dict[str, set[str]]:
    if scope not in {AlertScope.EZARC, AlertScope.EZARC_TEST}:
        return sid_asin_map
    result = {sid: set(asins) for sid, asins in sid_asin_map.items()}
    jp_sellers = {"EZARC JP-JP", "CBT-F Tools-JP"}
    for item in items:
        basic = item.get("basic_info") or {}
        sid = str(basic.get("sid") or "").strip()
        asin = str(basic.get("asin") or "").strip()
        if not sid or not asin or sid not in allowed_sids:
            continue
        if seller_map.get(sid) in jp_sellers:
            result.setdefault(sid, set()).add(asin)
    return result


def brands_for_scope(scope: AlertScope, metrics: list[MetricRecord]) -> list[str]:
    if scope in {AlertScope.EZARC, AlertScope.EZARC_TEST}:
        return ["EZARC"]
    if scope in {AlertScope.YPLUS, AlertScope.YPLUS_TEST}:
        return ["YPLUS"]
    if scope is AlertScope.LIBRATON or scope in {AlertScope.US, AlertScope.CA, AlertScope.JP, AlertScope.EU}:
        brands = sorted({(m.brand or "").strip().upper() for m in metrics if (m.brand or "").strip()})
        return brands or ["LIBRATON"]
    brands = sorted({(m.brand or "").strip().upper() for m in metrics if (m.brand or "").strip()})
    return brands


async def run_ingest_job(
    client: object,
    today: date,
    sid_list: list[str],
    db_config: DbConfig,
    *,
    scope: str = "libraton",
    dry_run: bool = False,
) -> IngestJobResult:
    try:
        started_at = time.perf_counter()
        scope_value = AlertScope.parse(scope)
        access_token = await client.fetch_access_token()
        seller_map = await client.fetch_seller_map(access_token)
        effective_sid_list = resolve_sid_list(sid_list, seller_map)
        scoped_sid_list = resolve_scope_sid_list(scope_value, effective_sid_list, seller_map)
        allowed_sids = set(scoped_sid_list)

        summary_started_at = time.perf_counter()
        raw_items: list[dict] = []
        for batch_sid_list, batch_data_type in build_summary_fetch_batches(scoped_sid_list, seller_map):
            raw_items.extend(
                await client.fetch_summary_items(
                    access_token,
                    batch_sid_list,
                    data_type=batch_data_type,
                )
            )
        print(f"[perf] summary_fetch_seconds={time.perf_counter() - summary_started_at:.2f}")
        sid_distribution = build_sid_distribution(raw_items, allowed_sids)
        print(f"[main] 目标店铺记录分布: {sid_distribution}")

        inventory_snapshot_candidate_sid_asin_map = build_sid_asin_map(raw_items, allowed_sids)
        inventory_snapshot_candidate_sid_asin_map = ensure_ezarc_jp_inventory_candidates(
            inventory_snapshot_candidate_sid_asin_map,
            raw_items,
            allowed_sids,
            seller_map,
            scope_value,
        )
        print(
            "[perf] source_list_candidates="
            f"{count_sid_asin_pairs(inventory_snapshot_candidate_sid_asin_map)} "
            f"sids={len(inventory_snapshot_candidate_sid_asin_map)}"
        )
        source_list_started_at = time.perf_counter()
        inventory_snapshot_map = await client.fetch_inventory_snapshot_map(
            access_token, inventory_snapshot_candidate_sid_asin_map
        )
        print(
            "[perf] source_list_fetch_seconds="
            f"{time.perf_counter() - source_list_started_at:.2f} "
            f"resolved_pairs={len(inventory_snapshot_map)}"
        )

        metrics = parse_metric_items(raw_items, today, seller_map, scoped_sid_list, inventory_snapshot_map)
        metrics = merge_ezarc_jp_metrics(
            raw_items,
            metrics,
            today,
            seller_map,
            allowed_sids,
            inventory_snapshot_map,
            enabled=scope_value in {AlertScope.EZARC, AlertScope.EZARC_TEST},
        )

        if metrics:
            listing_candidates = build_metric_sid_asin_map(metrics)
            print(
                "[perf] listing_candidates="
                f"{count_sid_asin_pairs(listing_candidates)} sids={len(listing_candidates)}"
            )
            listing_started_at = time.perf_counter()
            listing_items = await client.fetch_listing_items_by_asins(access_token, listing_candidates)
            print(
                "[perf] listing_fetch_seconds="
                f"{time.perf_counter() - listing_started_at:.2f} rows={len(listing_items)}"
            )
            apply_listing_contacts(metrics, build_listing_contact_map(listing_items))
            await refill_missing_listing_contacts(client, access_token, metrics)

        brands = brands_for_scope(scope_value, metrics)
        written = 0
        if dry_run:
            print(f"[db] dry-run 跳过写入 metrics={len(metrics)} brands={brands}")
        else:
            write_started = time.perf_counter()
            written = replace_metrics_for_day(db_config, today, metrics, brands=brands)
            print(
                f"[db] wrote={written} brands={brands} "
                f"seconds={time.perf_counter() - write_started:.2f}"
            )


        print(
            f"[info] fetched={len(raw_items)} metrics={len(metrics)} "
            f"written={written} dry_run={dry_run}"
        )
        print(f"[perf] total_run_seconds={time.perf_counter() - started_at:.2f}")
        return IngestJobResult(
            fetched_count=len(raw_items),
            metric_count=len(metrics),
            written_count=written,
            sid_distribution=sid_distribution,
            brands=brands,
        )
    except Exception as exc:
        print(f"[error] run_ingest_job_failed error={exc!r}")
        raise
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            maybe_awaitable = close()
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable


# 兼容旧名（测试 / 外部若仍 import）
run_alert_job = run_ingest_job
AlertJobResult = IngestJobResult
