#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass

from .models import AlertRecord
from .utils import unique_keep_order


@dataclass(frozen=True)
class StorePolicy:
    alert_thresholds: dict[str, int | None]
    notify_user_ids: list[str]
    auto_include_sid: bool = False
    report_group_name: str | None = None


DEFAULT_ALERT_THRESHOLDS = {
    "a_fba_days": 14,
    "a_fba_plus_days": 60,
    "a_out_stock_days": 50,
    "b_fba_days": 30,
    "b_equal_out_stock_days": 60,
    "b_fba_plus_days": 75,
}

DEFAULT_STORE_POLICY = StorePolicy(
    alert_thresholds=DEFAULT_ALERT_THRESHOLDS,
    notify_user_ids=[],
    auto_include_sid=False,
)
MAIN_REPORT_USER_IDS = ["16063564311489688", "17331048354297047"]
EZARC_EU_USER_IDS = [
    "17506435638027211",
    "17585057805545058",
    "17633432685584853",
    "17800198373694159",
    "17465848709312615",
]
EZARC_NA_USER_IDS = [
    "290435484624363486",
    "01076420214327759759",
    "454365106138190421",
    "17427794048531392",
    "17750084401515036",
    "17403614178121993",
]
EZARC_JP_USER_IDS = ["17439904366695445"]

STORE_POLICIES = {
    "EZARC EU-BE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-DE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-ES": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-FR": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-IE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-IT": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-NL": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-PL": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-SE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-TR": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC EU-UK": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 55,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=EZARC_EU_USER_IDS,
    ),
    "EZARC NA-US": StorePolicy(
        alert_thresholds={
            "a_fba_days": 20,
            "a_fba_plus_days": 60,
            "a_out_stock_days": 45,
            "b_fba_days": 45,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 75,
        },
        notify_user_ids=EZARC_NA_USER_IDS,
    ),
    "EZARC NA-CA": StorePolicy(
        alert_thresholds={
            "a_fba_days": 20,
            "a_fba_plus_days": 60,
            "a_out_stock_days": 60,
            "b_fba_days": 45,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 80,
        },
        notify_user_ids=EZARC_NA_USER_IDS,
    ),
    "EZARC JP-JP": StorePolicy(
        alert_thresholds={
            "a_fba_days": 20,
            "a_fba_plus_days": 30,
            "a_out_stock_days": 50,
            "b_fba_days": None,
            "b_equal_out_stock_days": None,
            "b_fba_plus_days": None,
        },
        notify_user_ids=EZARC_JP_USER_IDS,
    ),
    "CBT-F Tools-JP": StorePolicy(
        alert_thresholds={
            "a_fba_days": 20,
            "a_fba_plus_days": 30,
            "a_out_stock_days": 50,
            "b_fba_days": None,
            "b_equal_out_stock_days": None,
            "b_fba_plus_days": None,
        },
        notify_user_ids=[],
    ),
    "YPLUS-EU-BE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-DE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-ES": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-FR": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-IE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-IT": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-NL": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-PL": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-SE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-TR": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-EU-UK": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 75,
            "a_out_stock_days": 60,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 75,
            "b_fba_plus_days": 90,
        },
        notify_user_ids=[
            "23210537641286444",
            "350843032936428602",
        ],
    ),
    "YPLUS-US-US": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 45,
            "a_out_stock_days": 30,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 45,
            "b_fba_plus_days": 60,
        },
        notify_user_ids=["17441633442965653"],
    ),
    "TrailFun-US": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 45,
            "a_out_stock_days": 30,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 45,
            "b_fba_plus_days": 60,
        },
        notify_user_ids=[],
    ),
    "YPLUS-US-CA": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 55,
            "a_out_stock_days": 45,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 70,
        },
        notify_user_ids=["395439341733212350"],
    ),
    "YPLUS-JP-JP": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": None,
            "a_out_stock_days": 40,
            "b_fba_days": None,
            "b_equal_out_stock_days": None,
            "b_fba_plus_days": None,
        },
        notify_user_ids=["395439341733212350"],
    ),
    "Libraton EU": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 65,
            "b_fba_days": 30,
            "b_equal_out_stock_days": None,
            "b_fba_plus_days": 80,
        },
        notify_user_ids=[
            "17496925056054051",
            "17621342403159969",
            "17490880140202841",
        ],
    ),
    "Libraton EU-DE": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 65,
            "b_fba_days": 30,
            "b_equal_out_stock_days": None,
            "b_fba_plus_days": 80,
        },
        notify_user_ids=[
            "17496925056054051",
            "17621342403159969",
            "17490880140202841",
        ],
        report_group_name="Libraton EU",
    ),
    "Libraton EU-UK": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 65,
            "a_out_stock_days": 65,
            "b_fba_days": 30,
            "b_equal_out_stock_days": None,
            "b_fba_plus_days": 80,
        },
        notify_user_ids=[
            "17496925056054051",
            "17621342403159969",
            "17490880140202841",
        ],
        report_group_name="Libraton EU",
    ),
    "Libraton NA-US": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 45,
            "a_out_stock_days": 30,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 45,
            "b_fba_plus_days": 60,
        },
        notify_user_ids=[
            "17489140420206931",
            "17490879808802516",
        ],
        auto_include_sid=True,
    ),
    "Libraton NA-CA": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": 55,
            "a_out_stock_days": 45,
            "b_fba_days": 30,
            "b_equal_out_stock_days": 60,
            "b_fba_plus_days": 70,
        },
        notify_user_ids=[
            "01364646263121664148",
        ],
        auto_include_sid=True,
    ),
    "Libraton JP-JP": StorePolicy(
        alert_thresholds={
            "a_fba_days": 14,
            "a_fba_plus_days": None,
            "a_out_stock_days": 40,
            "b_fba_days": None,
            "b_equal_out_stock_days": None,
            "b_fba_plus_days": None,
        },
        notify_user_ids=[
            "250755202726645853",
        ],
        auto_include_sid=True,
    ),
}


def get_store_policy(seller_name: str) -> StorePolicy:
    return STORE_POLICIES.get(seller_name.strip(), DEFAULT_STORE_POLICY)


def resolve_sid_list(sid_list: list[str], seller_map: dict[str, str]) -> list[str]:
    resolved = list(sid_list)
    for sid, seller_name in seller_map.items():
        if get_store_policy(seller_name).auto_include_sid:
            resolved.append(sid)
    return unique_keep_order(resolved)


def resolve_notify_user_ids(alerts: list[AlertRecord], fallback_user_ids: list[str]) -> list[str]:
    resolved: list[str] = []
    for alert in alerts:
        resolved.extend(get_store_policy(alert.seller_name).notify_user_ids)
    user_ids = unique_keep_order(resolved)
    if user_ids:
        return user_ids
    return fallback_user_ids


def resolve_main_report_user_ids(fallback_user_ids: list[str]) -> list[str]:
    _ = fallback_user_ids
    return MAIN_REPORT_USER_IDS


def resolve_store_report_group_name(seller_name: str) -> str:
    policy = get_store_policy(seller_name)
    return policy.report_group_name or seller_name.strip()


def resolve_store_report_user_ids(seller_name: str, fallback_user_ids: list[str]) -> list[str]:
    user_ids = unique_keep_order(get_store_policy(seller_name).notify_user_ids)
    if user_ids:
        return user_ids
    return fallback_user_ids
