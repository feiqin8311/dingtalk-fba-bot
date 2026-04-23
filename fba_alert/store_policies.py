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

STORE_POLICIES = {
    "Libraton EU": StorePolicy(
        alert_thresholds=DEFAULT_ALERT_THRESHOLDS,
        notify_user_ids=[
            "17496925056054051",
            "17621342403159969",
            "17490880140202841",
        ],
    ),
    "Libraton EU-DE": StorePolicy(
        alert_thresholds=DEFAULT_ALERT_THRESHOLDS,
        notify_user_ids=[
            "17496925056054051",
            "17621342403159969",
            "17490880140202841",
        ],
        report_group_name="Libraton EU",
    ),
    "Libraton EU-UK": StorePolicy(
        alert_thresholds=DEFAULT_ALERT_THRESHOLDS,
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
