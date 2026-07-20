#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import urllib.error
import urllib.request
from typing import Optional

from .config import DingTalkConfig


class DingTalkNotifier:
    def __init__(self, config: DingTalkConfig):
        self.config = config
        self._token_cache: Optional[tuple[str, float]] = None

    def get_access_token(self) -> str:
        if self._token_cache and time.time() < self._token_cache[1] - 60:
            return self._token_cache[0]

        payload = {"appKey": self.config.app_key, "appSecret": self.config.app_secret}
        result = self._post_json(f"{self.config.api_base_url.rstrip('/')}/v1.0/oauth2/accessToken", payload)
        token = result.get("accessToken") or result.get("access_token")
        if not token:
            raise RuntimeError(f"获取钉钉 accessToken 失败: {result}")
        expires_in = int(result.get("expireIn") or result.get("expires_in") or 7200)
        self._token_cache = (token, time.time() + expires_in)
        return token

    def send_user_text(self, user_id: str, text: str) -> dict:
        payload = {
            "robotCode": self.config.robot_code,
            "userIds": [user_id],
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}, ensure_ascii=False),
        }
        token = self.get_access_token()
        headers = {"x-acs-dingtalk-access-token": token}
        return self._post_json(f"{self.config.api_base_url.rstrip('/')}/v1.0/robot/oToMessages/batchSend", payload, headers=headers)

    def send_user_markdown(self, user_id: str, title: str, text: str) -> dict:
        payload = {
            "robotCode": self.config.robot_code,
            "userIds": [user_id],
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({"title": title, "text": text}, ensure_ascii=False),
        }
        token = self.get_access_token()
        headers = {"x-acs-dingtalk-access-token": token}
        return self._post_json(f"{self.config.api_base_url.rstrip('/')}/v1.0/robot/oToMessages/batchSend", payload, headers=headers)

    @staticmethod
    def _post_json(url: str, payload: dict, headers: Optional[dict] = None) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"钉钉请求失败: {exc.code} {exc.reason}. {detail}") from exc
        return json.loads(body) if body else {}
