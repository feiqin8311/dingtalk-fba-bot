#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .config import AppConfig, load_config
from .utils import load_env_file


def validate_runtime_config(config: AppConfig, dry_run: bool) -> None:
    print(f"[config] dry_run={dry_run}")
    print(f"[config] sid_list={config.lingxing.sid_list}")
    print(f"[config] lingxing_api_host={config.lingxing.api_host}")
    print(f"[config] data_type={config.lingxing.data_type} mode={config.lingxing.mode}")
    print(f"[config] timezone={config.timezone}")
    if not config.lingxing.sid_list:
        raise RuntimeError("缺少 LINGXING_SID_LIST")
    if dry_run:
        return
    print(
        f"[config] db={config.db.user}@{config.db.host}:{config.db.port}/{config.db.database}"
    )
    if not config.db.host or not config.db.user or not config.db.database:
        raise RuntimeError("缺少 DB_HOST / DB_USER / DB_NAME，无法写入 fact_bi_amazon_fba_metric")


def load_runtime_config(env_file: str, dry_run: bool) -> AppConfig:
    load_env_file(env_file)
    config = load_config()
    validate_runtime_config(config, dry_run)
    return config
