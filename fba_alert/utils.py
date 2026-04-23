#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

try:
    import orjson

    def json_dumps(obj: Any) -> bytes:
        return orjson.dumps(obj, option=orjson.OPT_SORT_KEYS)

except ImportError:

    def json_dumps(obj: Any) -> bytes:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_env_file(env_path: str = ".env") -> None:
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def getenv_str(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or default).strip()


def getenv_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def getenv_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


def getenv_list(name: str, default: str = "") -> list[str]:
    raw = getenv_str(name, default)
    if not raw:
        return []
    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]


def unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_today(value: str) -> date:
    if value:
        return parse_date(value)
    return datetime.now().date()


def calc_out_stock_days(out_stock_date: str, today: date) -> int:
    if not out_stock_date:
        return 0
    target = parse_date(out_stock_date)
    if not target:
        return 0
    return (target - today).days
