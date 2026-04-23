#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from enum import Enum


class AlertScope(str, Enum):
    ALL = "all"
    US = "us"
    CA = "ca"
    JP = "jp"
    EU = "eu"

    @classmethod
    def parse(cls, value: str) -> "AlertScope":
        normalized = (value or cls.ALL.value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unsupported alert scope: {value}") from exc


SCOPE_SELLER_NAMES = {
    AlertScope.US: {"Libraton NA-US"},
    AlertScope.CA: {"Libraton NA-CA"},
    AlertScope.JP: {"Libraton JP-JP"},
    AlertScope.EU: {"Libraton EU-DE", "Libraton EU-UK"},
}
SCOPE_REPORT_GROUP_NAMES = {
    AlertScope.US: "Libraton NA-US",
    AlertScope.CA: "Libraton NA-CA",
    AlertScope.JP: "Libraton JP-JP",
    AlertScope.EU: "Libraton EU",
}


def resolve_scope_seller_names(scope: AlertScope, seller_map: dict[str, str]) -> set[str]:
    if scope is AlertScope.ALL:
        return set(seller_map.values())
    return set(SCOPE_SELLER_NAMES[scope])


def resolve_scope_sid_list(scope: AlertScope, base_sid_list: list[str], seller_map: dict[str, str]) -> list[str]:
    if scope is AlertScope.ALL:
        return list(base_sid_list)
    target_sellers = resolve_scope_seller_names(scope, seller_map)
    resolved = [sid for sid, seller_name in seller_map.items() if seller_name in target_sellers]
    if not resolved:
        raise RuntimeError(f"scope={scope.value} 未匹配到任何店铺 SID")
    return resolved


def resolve_scope_report_group_name(scope: AlertScope) -> str:
    if scope is AlertScope.ALL:
        raise ValueError("all scope does not have a scoped report group")
    return SCOPE_REPORT_GROUP_NAMES[scope]
