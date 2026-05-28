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
    print(f"[config] dingtalk_user_count={len(config.dingtalk.user_ids)}")
    if not config.dingtalk.user_ids:
        raise RuntimeError("缺少 DINGTALK_USER_IDS，无法发送钉钉消息。")
    if not config.dingtalk.app_key or not config.dingtalk.app_secret or not config.dingtalk.robot_code:
        raise RuntimeError("缺少钉钉企业应用配置: DINGTALK_APP_KEY / DINGTALK_APP_SECRET / DINGTALK_ROBOT_CODE")
    if config.dingtalk.dingpan_enabled:
        print(
            f"[config] dingpan_enabled space_id={config.dingtalk.dingpan_space_id} "
            f"parent_folder_id={config.dingtalk.dingpan_parent_folder_id}"
        )
        if not config.dingtalk.dingpan_space_id or not config.dingtalk.dingpan_parent_folder_id:
            raise RuntimeError(
                "钉盘上传已启用但缺少 DINGTALK_DINGPAN_SPACE_ID / DINGTALK_DINGPAN_PARENT_FOLDER_ID"
            )
        if not config.dingtalk.dingpan_union_id and not config.dingtalk.dingpan_user_id:
            raise RuntimeError(
                "钉盘上传已启用但缺少 DINGTALK_DINGPAN_UNION_ID 或 DINGTALK_DINGPAN_USER_ID"
            )


def load_runtime_config(env_file: str, dry_run: bool) -> AppConfig:
    load_env_file(env_file)
    config = load_config()
    validate_runtime_config(config, dry_run)
    return config
