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
class DingTalkConfig:
    api_base_url: str
    app_key: str
    app_secret: str
    robot_code: str
    user_ids: list[str]
    dingpan_enabled: bool
    dingpan_space_id: str
    dingpan_parent_folder_id: str
    dingpan_user_id: str
    dingpan_union_id: str


@dataclass
class AppConfig:
    lingxing: LingxingConfig
    dingtalk: DingTalkConfig
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
        data_type=getenv_int("LINGXING_DATA_TYPE", 1),
        mode=getenv_int("LINGXING_MODE", 0),
        page_size=min(max(getenv_int("LINGXING_PAGE_SIZE", 50), 1), 50),
        listing_concurrency=min(max(getenv_int("LINGXING_LISTING_CONCURRENCY", 2), 1), 20),
        source_list_concurrency=min(max(getenv_int("LINGXING_SOURCE_LIST_CONCURRENCY", 4), 1), 20),
        source_list_cache_enabled=getenv_bool("LINGXING_SOURCE_LIST_CACHE_ENABLED", True),
        source_list_cache_dir=getenv_str("LINGXING_SOURCE_LIST_CACHE_DIR", ".cache/fba_alert/source_list"),
    )
    dingtalk = DingTalkConfig(
        api_base_url=getenv_str("DINGTALK_API_BASE_URL", "https://api.dingtalk.com"),
        app_key=getenv_str("DINGTALK_APP_KEY"),
        app_secret=getenv_str("DINGTALK_APP_SECRET"),
        robot_code=getenv_str("DINGTALK_ROBOT_CODE"),
        user_ids=getenv_list("DINGTALK_USER_IDS"),
        dingpan_enabled=getenv_bool("DINGTALK_DINGPAN_ENABLED", True),
        dingpan_space_id=getenv_str("DINGTALK_DINGPAN_SPACE_ID", "28859011990"),
        dingpan_parent_folder_id=getenv_str("DINGTALK_DINGPAN_PARENT_FOLDER_ID", "221392062127"),
        dingpan_user_id=getenv_str("DINGTALK_DINGPAN_USER_ID"),
        dingpan_union_id=getenv_str("DINGTALK_DINGPAN_UNION_ID"),
    )
    return AppConfig(
        lingxing=lingxing,
        dingtalk=dingtalk,
        timezone=getenv_str("APP_TIMEZONE", "Asia/Shanghai"),
    )
