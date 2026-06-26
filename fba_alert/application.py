#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import inspect
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import time
from typing import Callable, Optional

from . import dingpan
from .alerts import (
    apply_listing_contacts,
    build_listing_contact_map,
    collapse_msku_variants,
    is_primary_msku,
    normalize_msku,
    parse_summary_items,
)
from .config import DingTalkConfig
from .models import AlertRecord
from .report import build_main_report_path, build_store_report_path, export_scoped_alert_report
from .scopes import AlertScope, resolve_scope_report_group_name, resolve_scope_sid_list
from .store_policies import (
    resolve_main_report_user_ids,
    resolve_sid_list,
    resolve_store_report_group_name,
    resolve_store_report_user_ids,
)
from .utils import safe_float, safe_int

INVENTORY_SNAPSHOT_CANDIDATE_THRESHOLD = 5
DINGPAN_FOLDER_CACHE_PATH = Path(".cache/fba_alert/dingpan-folders.json")
DINGPAN_BRAND_ROOT_FOLDER_IDS = {
    "EZARC": "225801991522",
    "YPLUS": "225802102609",
    "LIBRATON": "221392062127",
}
DINGPAN_BRAND_ROUTE_FOLDER_IDS = {
    ("EZARC", "北美"): "225835089569",
    ("EZARC", "汇总"): "225835089358",
    ("EZARC", "日本"): "225835130893",
    ("EZARC", "欧洲"): "225835084068",
    ("LIBRATON", "北美"): "225843424226",
    ("LIBRATON", "汇总"): "225843426167",
    ("LIBRATON", "日本"): "225843386198",
    ("LIBRATON", "欧洲"): "225843401936",
    ("YPLUS", "北美"): "225834954955",
    ("YPLUS", "汇总"): "225835002566",
    ("YPLUS", "日本"): "225834962366",
    ("YPLUS", "欧洲"): "225834869615",
}


@dataclass(frozen=True)
class AlertJobResult:
    fetched_count: int
    alert_count: int
    report_path: str
    sid_distribution: dict[str, int]


def count_sid_asin_pairs(sid_asin_map: dict[str, set[str]]) -> int:
    return sum(len(asin_set) for asin_set in sid_asin_map.values())


def build_summary_fetch_batches(scoped_sid_list: list[str], seller_map: dict[str, str]) -> list[tuple[list[str], int | None]]:
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
    _ = prelim_alerts, seller_map
    return build_sid_asin_map(items, allowed_sids)


def notify_report(
    report_path: str,
    notifier: Optional[object],
    user_ids: list[str],
    dry_run: bool,
    *,
    preview_url: str = "",
    title: str = "LIBRATON 库存预警报告",
) -> None:
    if dry_run:
        print(f"[notify] dry-run 模式，报表已生成: {report_path}")
        return
    if notifier is None:
        raise RuntimeError("非 dry-run 模式必须提供 notifier。")

    if preview_url:
        text = f"【{title}】\n请查看HTML诊断报告：{preview_url}"
        for user_id in user_ids:
            print(f"[notify] 发送钉盘链接: user_id={user_id} url={preview_url}")
            result = notifier.send_user_text(user_id, text)
            print(f"[send] user_id={user_id} result={json.dumps(result, ensure_ascii=False)}")
        return

    for user_id in user_ids:
        print(f"[notify] 发送钉钉文件: user_id={user_id}")
        result = notifier.send_user_file(user_id, report_path)
        print(f"[send] user_id={user_id} result={json.dumps(result, ensure_ascii=False)}")


def upload_reports_to_dingpan(
    notifier: object,
    dingtalk_config: DingTalkConfig,
    main_report_path: str,
    alerts: list[AlertRecord],
    today: date,
    scope: AlertScope,
) -> dict[str, str]:
    """在钉盘建当天日期子文件夹，上传主表和各店铺分表。

    返回 {report_path: preview_url}。失败时返回空 dict 并打印错误，不阻塞消息发送。
    """
    if not dingtalk_config.dingpan_enabled:
        return {}

    try:
        access_token = notifier.get_access_token()
        union_id = dingtalk_config.dingpan_union_id
        if not union_id:
            union_id = dingpan.get_user_union_id(access_token, dingtalk_config.dingpan_user_id)
            print(f"[dingpan] 解析 union_id={union_id}")

        upload_paths: list[str] = []
        if scope in {AlertScope.ALL, AlertScope.EZARC_TEST, AlertScope.YPLUS_TEST}:
            upload_paths.append(main_report_path)
        if scope is AlertScope.ALL:
            store_report_paths = build_store_report_paths(main_report_path, alerts, today)
            for store_report_path in store_report_paths.values():
                if store_report_path not in upload_paths:
                    upload_paths.append(store_report_path)

        preview_url_map: dict[str, str] = {}
        for path_str in upload_paths:
            file_path = Path(path_str)
            if not file_path.exists():
                print(f"[dingpan] 跳过缺失文件: {file_path}")
                continue
            store_name = extract_store_name_from_report_path(file_path)
            route = build_dingpan_folder_route(file_path.name, store_name)
            route_parent_id = resolve_dingpan_route_parent_id(
                file_path.name,
                store_name,
                dingtalk_config.dingpan_parent_folder_id,
            )
            route_fully_resolved = route_parent_id in DINGPAN_BRAND_ROUTE_FOLDER_IDS.values()
            folder_names = [today.isoformat()] if route_fully_resolved else [*route, today.isoformat()]
            target_folder_id = ensure_dingpan_folder_route(
                access_token,
                space_id=dingtalk_config.dingpan_space_id,
                union_id=union_id,
                parent_id=route_parent_id,
                folder_names=folder_names,
                skip_lookup=route_fully_resolved,
            )
            print(f"[dingpan] 上传文件: {file_path.name}")
            try:
                result = dingpan.upload_file(
                    access_token,
                    space_id=dingtalk_config.dingpan_space_id,
                    union_id=union_id,
                    parent_id=target_folder_id,
                    file_path=file_path,
                )
            except RuntimeError as exc:
                if not is_parent_dentry_missing_error(exc):
                    raise
                invalidate_dingpan_folder_cache(
                    dingtalk_config.dingpan_space_id,
                    route_parent_id,
                    folder_names,
                )
                print(f"[dingpan] 目录缓存失效，重试上传: {file_path.name}")
                target_folder_id = ensure_dingpan_folder_route(
                    access_token,
                    space_id=dingtalk_config.dingpan_space_id,
                    union_id=union_id,
                    parent_id=route_parent_id,
                    folder_names=folder_names,
                    skip_lookup=route_fully_resolved,
                )
                result = dingpan.upload_file(
                    access_token,
                    space_id=dingtalk_config.dingpan_space_id,
                    union_id=union_id,
                    parent_id=target_folder_id,
                    file_path=file_path,
                )
            file_id = dingpan.extract_file_id(result["commit"])
            if not file_id:
                print(f"[dingpan] 上传成功但未拿到 file_id: {file_path.name}")
                continue
            preview_url_map[path_str] = dingpan.build_preview_url(
                dingtalk_config.dingpan_space_id, file_id
            )
            print(f"[dingpan] 预览链接: {file_path.name} -> {preview_url_map[path_str]}")
        return preview_url_map
    except Exception as exc:
        print(f"[dingpan] 上传失败，回退为附件直发: {exc!r}")
        return {}


def ensure_dingpan_folder_route(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    parent_id: str,
    folder_names: list[str],
    skip_lookup: bool = False,
) -> str:
    cache = load_dingpan_folder_cache()
    cache_key = build_dingpan_folder_cache_key(space_id, parent_id, folder_names)
    cached_folder_id = cache.get(cache_key)
    if cached_folder_id:
        print(f"[dingpan] 复用本地缓存目录: {' / '.join(folder_names)} ({cached_folder_id})")
        return cached_folder_id

    current_parent_id = parent_id
    for folder_name in folder_names:
        if skip_lookup:
            created = dingpan.create_folder(
                access_token,
                space_id=space_id,
                union_id=union_id,
                parent_id=current_parent_id,
                name=folder_name,
            )
            dentry = created.get("dentry") or {}
            folder_id = str(dentry.get("id") or dentry.get("uuid") or dentry.get("dentryUuid") or "")
            if not folder_id:
                raise RuntimeError(f"created child folder missing id: {folder_name}")
            folder = {"id": folder_id, "name": folder_name, "created": True, "dentry": dentry}
            print(f"[dingpan] 已创建日期子文件夹: {folder_name} ({folder_id})")
        else:
            folder = dingpan.ensure_child_folder(
                access_token,
                space_id=space_id,
                union_id=union_id,
                parent_id=current_parent_id,
                folder_name=folder_name,
            )
        current_parent_id = str(folder["id"])
    cache[cache_key] = current_parent_id
    save_dingpan_folder_cache(cache)
    return current_parent_id


def build_dingpan_folder_cache_key(space_id: str, parent_id: str, folder_names: list[str]) -> str:
    return f"{space_id}:{parent_id}:{'/'.join(folder_names)}"


def is_parent_dentry_missing_error(exc: RuntimeError) -> bool:
    message = str(exc)
    return "parentDentry not exist" in message


def load_dingpan_folder_cache() -> dict[str, str]:
    if not DINGPAN_FOLDER_CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(DINGPAN_FOLDER_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in raw.items()
        if str(key).strip() and str(value).strip()
    }


def save_dingpan_folder_cache(cache: dict[str, str]) -> None:
    DINGPAN_FOLDER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DINGPAN_FOLDER_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def invalidate_dingpan_folder_cache(space_id: str, parent_id: str, folder_names: list[str]) -> None:
    cache = load_dingpan_folder_cache()
    cache_key = build_dingpan_folder_cache_key(space_id, parent_id, folder_names)
    if cache.pop(cache_key, None) is None:
        return
    save_dingpan_folder_cache(cache)


def extract_store_name_from_report_path(report_path: Path) -> str:
    if report_path.parent.parent.name == "reports":
        return ""
    return report_path.parent.name


def resolve_dingpan_brand_name(report_file_name: str, store_name: str) -> str:
    upper_file_name = report_file_name.upper()
    upper_store_name = store_name.upper()

    if "EZARC" in upper_file_name or "EZARC" in upper_store_name:
        return "EZARC"
    if "YPLUS" in upper_file_name or "YPLUS" in upper_store_name:
        return "YPLUS"
    return "LIBRATON"


def resolve_dingpan_brand_root_id(report_file_name: str, store_name: str, fallback_parent_id: str) -> str:
    brand_name = resolve_dingpan_brand_name(report_file_name, store_name)
    return DINGPAN_BRAND_ROOT_FOLDER_IDS.get(brand_name, fallback_parent_id)


def resolve_dingpan_route_parent_id(report_file_name: str, store_name: str, fallback_parent_id: str) -> str:
    brand_name = resolve_dingpan_brand_name(report_file_name, store_name)
    route_name = build_dingpan_folder_route(report_file_name, store_name)[0]
    return DINGPAN_BRAND_ROUTE_FOLDER_IDS.get(
        (brand_name, route_name),
        resolve_dingpan_brand_root_id(report_file_name, store_name, fallback_parent_id),
    )


def build_dingpan_folder_route(report_file_name: str, store_name: str) -> list[str]:
    upper_store_name = store_name.upper()
    if not store_name:
        return ["汇总"]
    if "JP" in upper_store_name:
        return ["日本"]
    if "EU" in upper_store_name:
        return ["欧洲"]
    if "NA" in upper_store_name or "US" in upper_store_name or "CA" in upper_store_name:
        return ["北美"]
    return ["汇总"]


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
    preview_url_map: Optional[dict[str, str]] = None,
) -> None:
    store_report_paths = build_store_report_paths(main_report_path, alerts, today)
    preview_url_map = preview_url_map or {}
    for store_name, store_report_path in store_report_paths.items():
        user_ids = resolve_store_report_user_ids(store_name, fallback_user_ids)
        print(
            "[notify] 店铺分表准备发送: "
            f"store={store_name} user_count={len(user_ids)} path={store_report_path}"
        )
        notify_report(
            store_report_path,
            notifier,
            user_ids,
            dry_run=dry_run,
            preview_url=preview_url_map.get(store_report_path, ""),
            title=f"LIBRATON 库存预警 - {store_name}",
        )


def resolve_delivery_user_ids(
    fallback_user_ids: list[str],
    override_user_ids: list[str],
) -> list[str]:
    if override_user_ids:
        return override_user_ids
    return fallback_user_ids


def export_total_report(
    exporter: Callable[..., str],
    alerts: list[AlertRecord],
    today: date,
    *,
    include_store_reports: bool = True,
    main_report_name: str = "LIBRATON库存预警",
) -> str:
    parameters = inspect.signature(exporter).parameters.values()
    accepts_keyword_args = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    accepts_named_options = "include_store_reports" in inspect.signature(exporter).parameters
    if accepts_keyword_args or accepts_named_options:
        return exporter(
            alerts,
            today,
            include_store_reports=include_store_reports,
            main_report_name=main_report_name,
        )
    return exporter(alerts, today)


def merge_ezarc_test_jp_alerts(alerts: list[AlertRecord], today: date, scope: AlertScope) -> list[AlertRecord]:
    return alerts


def ensure_ezarc_test_jp_inventory_candidates(
    sid_asin_map: dict[str, set[str]],
    items: list[dict],
    allowed_sids: set[str],
    seller_map: dict[str, str],
    scope: AlertScope,
) -> dict[str, set[str]]:
    if scope is not AlertScope.EZARC_TEST:
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


def merge_ezarc_test_jp_alerts(
    raw_items: list[dict],
    alerts: list[AlertRecord],
    today: date,
    scope: AlertScope,
    seller_map: dict[str, str],
    allowed_sids: set[str],
    inventory_snapshot_map: dict[tuple[str, str], object],
) -> list[AlertRecord]:
    if scope is not AlertScope.EZARC_TEST:
        return alerts

    jp_sellers = {"EZARC JP-JP", "CBT-F Tools-JP"}
    merged = [alert for alert in alerts if alert.seller_name not in jp_sellers]
    jp_bucket: dict[str, list[dict]] = {}

    for item in raw_items:
        basic = item.get("basic_info") or {}
        sid = str(basic.get("sid") or "").strip()
        asin = str(basic.get("asin") or "").strip()
        seller_name = seller_map.get(sid, sid)
        if sid not in allowed_sids or seller_name not in jp_sellers or not asin:
            continue

        suggest = item.get("suggest_info") or {}
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
            fba_transfer_reserved_inventory = safe_int(getattr(inventory_snapshot, "fba_transfer_reserved_inventory", 0))
            fba_processing_inventory = safe_int(getattr(inventory_snapshot, "fba_processing_inventory", 0))

        mskus = collapse_msku_variants(
            [
                normalize_msku(str(row.get("msku") or ""))
                for row in (basic.get("msku_fnsku_list") or [])
                if is_primary_msku(str(row.get("msku") or ""))
            ]
        )
        for msku in mskus:
            jp_bucket.setdefault(msku, []).append(
                {
                    "asin": asin,
                    "sid": sid,
                    "node_type": safe_int(basic.get("node_type")),
                    "summary_daily_sales": round(safe_float(suggest.get("estimated_sale_avg_quantity")), 2),
                    "fba_inventory": fba_inventory,
                    "fba_inbound_inventory": fba_inbound_inventory,
                    "fba_sellable_inventory": fba_sellable_inventory,
                    "fba_transfer_reserved_inventory": fba_transfer_reserved_inventory,
                    "fba_processing_inventory": fba_processing_inventory,
                }
            )

    for msku, items in jp_bucket.items():
        total_daily_sales = round(sum(item["summary_daily_sales"] for item in items), 2)
        total_fba_inventory = sum(item["fba_inventory"] for item in items)
        total_fba_inbound_inventory = sum(item["fba_inbound_inventory"] for item in items)
        total_fba_sellable_inventory = sum(item["fba_sellable_inventory"] for item in items)
        total_fba_transfer_reserved_inventory = sum(item["fba_transfer_reserved_inventory"] for item in items)
        total_fba_processing_inventory = sum(item["fba_processing_inventory"] for item in items)
        fba_days = int(total_fba_inventory / total_daily_sales) if total_daily_sales > 0 else 0
        fba_plus_days = int((total_fba_inventory + total_fba_inbound_inventory) / total_daily_sales) if total_daily_sales > 0 else 0
        out_stock_days = fba_days
        out_stock_date = ""
        if out_stock_days > 0:
            out_stock_date = date.fromordinal(today.toordinal() + out_stock_days).isoformat()

        reasons: list[str] = []
        level = ""
        if total_fba_inventory == 0 and total_fba_inbound_inventory > 0:
            level = "C"
            reasons.append(f"FBA库存=0 且 FBA在途={total_fba_inbound_inventory}")
        else:
            if 0 < fba_days <= 20:
                reasons.append(f"可售天数(FBA)={fba_days}天")
            if 0 < fba_plus_days <= 30:
                reasons.append(f"可售天数(FBA+在途)={fba_plus_days}天")
            if 0 < out_stock_days <= 50:
                reasons.append(f"断货时间(天数)={out_stock_days}天")
            if reasons:
                level = "A"
        if not level:
            continue

        first = items[0]
        merged.append(
            AlertRecord(
                level=level,
                reasons=reasons,
                asin=str(first["asin"]),
                sid=str(first["sid"]),
                seller_name="EZARC JP 汇总",
                node_type=safe_int(first["node_type"]),
                mskus=[msku],
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
                hash_id=f"ezarc-jp-{msku}",
            )
        )

    merged.sort(key=lambda row: (row.seller_name, row.level, row.out_stock_days if row.out_stock_days > 0 else 10**9, row.asin))
    return merged


async def run_alert_job(
    client: object,
    today: date,
    sid_list: list[str],
    exporter: Optional[Callable[[list[AlertRecord], date], str]] = None,
    notifier: Optional[object] = None,
    notify_user_ids: Optional[list[str]] = None,
    notify_user_override_ids: Optional[list[str]] = None,
    dry_run: bool = False,
    scope: str = "all",
    upload_only: bool = False,
    dingtalk_config: Optional[DingTalkConfig] = None,
) -> AlertJobResult:
    export_report = exporter or (lambda alerts, current_today: "")
    user_ids = notify_user_ids or []
    override_user_ids = notify_user_override_ids or []
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

        raw_filtered_count = sum(sid_distribution.values())
        print(f"[main] 原始返回中命中目标店铺的记录数: {raw_filtered_count}")
        print(f"[main] 目标店铺记录分布: {sid_distribution}")

        prelim_alerts = parse_summary_items(raw_items, today, seller_map, scoped_sid_list)
        inventory_snapshot_candidate_sid_asin_map = build_inventory_snapshot_candidate_sid_asin_map(
            raw_items,
            prelim_alerts,
            allowed_sids,
            seller_map,
        )
        inventory_snapshot_candidate_sid_asin_map = ensure_ezarc_test_jp_inventory_candidates(
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
        inventory_snapshot_map = await client.fetch_inventory_snapshot_map(access_token, inventory_snapshot_candidate_sid_asin_map)
        print(
            "[perf] source_list_fetch_seconds="
            f"{time.perf_counter() - source_list_started_at:.2f} "
            f"resolved_pairs={len(inventory_snapshot_map)}"
        )
        print("[main] 开始按规则筛选预警")
        final_classify_started_at = time.perf_counter()
        alerts = parse_summary_items(raw_items, today, seller_map, scoped_sid_list, inventory_snapshot_map)
        alerts = merge_ezarc_test_jp_alerts(
            raw_items,
            alerts,
            today,
            scope_value,
            seller_map,
            allowed_sids,
            inventory_snapshot_map,
        )
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
        if scope_value is AlertScope.EZARC_TEST:
            report_path = export_total_report(
                export_report,
                alerts,
                today,
                include_store_reports=False,
                main_report_name="EZARC库存预警测试",
            )
        elif scope_value is AlertScope.YPLUS_TEST:
            report_path = export_total_report(
                export_report,
                alerts,
                today,
                include_store_reports=False,
                main_report_name="YPLUS库存预警测试",
            )
        elif scope_value is AlertScope.ALL:
            report_path = export_total_report(export_report, alerts, today)
        else:
            report_group_name = resolve_scope_report_group_name(scope_value)
            report_path = export_scoped_alert_report(alerts, today, report_group_name)
        print(f"[perf] report_export_seconds={time.perf_counter() - report_started_at:.2f}")

        preview_url_map: dict[str, str] = {}
        if not dry_run and notifier is not None and dingtalk_config is not None and dingtalk_config.dingpan_enabled:
            print("[main] 上传报表到钉盘日期子文件夹")
            dingpan_started_at = time.perf_counter()
            preview_url_map = upload_reports_to_dingpan(
                notifier,
                dingtalk_config,
                report_path,
                alerts,
                today,
                scope_value,
            )
            print(f"[perf] dingpan_upload_seconds={time.perf_counter() - dingpan_started_at:.2f}")

        if upload_only:
            print("[notify] upload-only 模式，跳过所有消息发送")
        elif scope_value is AlertScope.EZARC_TEST:
            notify_report(
                report_path,
                notifier,
                [],
                dry_run=dry_run,
                preview_url=preview_url_map.get(report_path, ""),
                title="EZARC 库存预警测试 - 总表",
            )
        elif scope_value is AlertScope.YPLUS_TEST:
            notify_report(
                report_path,
                notifier,
                [],
                dry_run=dry_run,
                preview_url=preview_url_map.get(report_path, ""),
                title="YPLUS 库存预警测试 - 总表",
            )
        elif scope_value is AlertScope.ALL:
            main_report_user_ids = resolve_delivery_user_ids(
                resolve_main_report_user_ids(user_ids),
                override_user_ids,
            )
            notify_report(
                report_path,
                notifier,
                main_report_user_ids,
                dry_run=dry_run,
                preview_url=preview_url_map.get(report_path, ""),
                title="LIBRATON 库存预警 - 总表",
            )
            if override_user_ids:
                print("[notify] 检测到 --notify-user-id override，跳过店铺分表分发，仅发送总表")
            else:
                notify_store_reports(
                    report_path,
                    alerts,
                    today,
                    notifier,
                    user_ids,
                    dry_run=dry_run,
                    preview_url_map=preview_url_map,
                )
        else:
            report_group_name = resolve_scope_report_group_name(scope_value)
            scoped_user_ids = resolve_delivery_user_ids(
                resolve_store_report_user_ids(report_group_name, user_ids),
                override_user_ids,
            )
            notify_report(
                report_path,
                notifier,
                scoped_user_ids,
                dry_run=dry_run,
                preview_url=preview_url_map.get(report_path, ""),
                title=f"LIBRATON 库存预警 - {report_group_name}",
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
