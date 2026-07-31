#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass

from .utils import getenv_bool, getenv_int, getenv_list, getenv_str


@dataclass
class LingxingConfig:
    api_host: str
    app_id: str
    app_secret: str
    token_url: str
    token_request_key: str
    ssl_verify: bool
    sid_list: list[str]
    data_type: int
    mode: int
    page_size: int
    listing_concurrency: int
    source_list_concurrency: int
    source_list_cache_enabled: bool
    source_list_cache_dir: str


@dataclass
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class AppConfig:
    lingxing: LingxingConfig
    db: DbConfig
    timezone: str


def load_config() -> AppConfig:
    lingxing = LingxingConfig(
        api_host=getenv_str("LINGXING_API_HOST", "http://121.41.4.126:3188"),
        app_id=getenv_str("LINGXING_APP_ID", "ak_8CW3MktzhMfAS"),
        app_secret=getenv_str("LINGXING_APP_SECRET", "7tfj0N4Mg1JQ/AYJ0nonQw=="),
        token_url=getenv_str("LINGXING_TOKEN_URL", "http://121.41.4.126:3721/token"),
        token_request_key=getenv_str("LINGXING_TOKEN_REQUEST_KEY", getenv_str("LINGXING_APP_ID", "ak_8CW3MktzhMfAS")),
        ssl_verify=getenv_bool("LINGXING_SSL_VERIFY", True),
        sid_list=getenv_list("LINGXING_SID_LIST", "1448,1446"),
        data_type=getenv_int("LINGXING_DATA_TYPE", 2),
        mode=getenv_int("LINGXING_MODE", 0),
        page_size=min(max(getenv_int("LINGXING_PAGE_SIZE", 50), 1), 50),
        listing_concurrency=min(max(getenv_int("LINGXING_LISTING_CONCURRENCY", 2), 1), 20),
        source_list_concurrency=min(max(getenv_int("LINGXING_SOURCE_LIST_CONCURRENCY", 4), 1), 20),
        source_list_cache_enabled=getenv_bool("LINGXING_SOURCE_LIST_CACHE_ENABLED", True),
        source_list_cache_dir=getenv_str("LINGXING_SOURCE_LIST_CACHE_DIR", ".cache/fba_alert/source_list"),
    )
    db = DbConfig(
        host=getenv_str("DB_HOST", "127.0.0.1"),
        port=getenv_int("DB_PORT", 3306),
        user=getenv_str("DB_USER", "root"),
        password=getenv_str("DB_PASSWORD", ""),
        database=getenv_str("DB_NAME", "bi_amazon"),
    )
    return AppConfig(
        lingxing=lingxing,
        db=db,
        timezone=getenv_str("APP_TIMEZONE", "Asia/Shanghai"),
    )
