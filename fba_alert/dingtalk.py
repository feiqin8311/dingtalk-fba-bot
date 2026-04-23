#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
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

    def send_user_file(self, user_id: str, file_path: str) -> dict:
        token = self.get_access_token()
        media_id = self._upload_message_file(file_path, token)
        payload = {
            "robotCode": self.config.robot_code,
            "userIds": [user_id],
            "msgKey": "sampleFile",
            "msgParam": json.dumps(
                {
                    "mediaId": media_id,
                    "fileName": os.path.basename(file_path),
                    "fileType": self._guess_file_type(file_path),
                },
                ensure_ascii=False,
            ),
        }
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

    @staticmethod
    def _post_raw(url: str, data: bytes, headers: dict) -> dict:
        req = urllib.request.Request(url, data=data, method="POST")
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"钉钉请求失败: {exc.code} {exc.reason}. {detail}") from exc
        return json.loads(body) if body else {}

    @staticmethod
    def _build_multipart_formdata(field_name: str, file_path: str) -> tuple[str, bytes]:
        boundary = uuid.uuid4().hex
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(file_path, "rb") as handle:
            file_data = handle.read()

        lines = []
        lines.append(f"--{boundary}\r\n".encode("utf-8"))
        lines.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        lines.append(file_data)
        lines.append(b"\r\n")
        lines.append(f"--{boundary}--\r\n".encode("utf-8"))
        return boundary, b"".join(lines)

    def _upload_message_file(self, file_path: str, token: str) -> str:
        url = f"{self.config.api_base_url.rstrip('/')}/v1.0/robot/messageFiles/upload"
        boundary, body = self._build_multipart_formdata("media", file_path)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "x-acs-dingtalk-access-token": token,
        }
        try:
            result = self._post_raw(url, body, headers)
            media_id = result.get("media_id") or result.get("mediaId")
            if media_id:
                return media_id
        except Exception:
            pass
        return self._upload_media_legacy(file_path, token)

    def _upload_media_legacy(self, file_path: str, token: str) -> str:
        query = urllib.parse.urlencode({"access_token": token, "type": "file"})
        url = f"https://oapi.dingtalk.com/media/upload?{query}"
        boundary, body = self._build_multipart_formdata("media", file_path)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        result = self._post_raw(url, body, headers)
        media_id = result.get("media_id") or result.get("mediaId")
        if not media_id:
            raise RuntimeError(f"上传钉钉文件失败: {result}")
        return media_id

    @staticmethod
    def _guess_file_type(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {".xls", ".xlsx", ".xlsm"}:
            return "xls"
        if ext == ".pdf":
            return "pdf"
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp"}:
            return "image"
        if ext in {".txt", ".log"}:
            return "txt"
        return "file"
