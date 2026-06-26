#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

BASE_STORAGE_URL = "https://api.dingtalk.com/v1.0/storage/spaces"
OAPI_USER_GET_URL = "https://oapi.dingtalk.com/topapi/v2/user/get"


def _json_response(resp: requests.Response, *, label: str) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{label}: HTTP {resp.status_code}, non-json: {resp.text[:300]}") from exc
    if not resp.ok:
        raise RuntimeError(f"{label}: HTTP {resp.status_code}: {data}")
    return data


def _storage_url(space_id: str, path: str) -> str:
    return f"{BASE_STORAGE_URL}/{space_id}/{path.lstrip('/')}"


def _storage_request(
    method: str,
    *,
    access_token: str,
    space_id: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 30,
    label: str,
) -> dict[str, Any]:
    resp = requests.request(
        method,
        _storage_url(space_id, path),
        params=params,
        headers={
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json",
        },
        json=json_body,
        timeout=timeout,
    )
    return _json_response(resp, label=label)


def get_user_union_id(access_token: str, user_id: str) -> str:
    """通过钉钉 OAPI 把 userId 换成 unionId（钉盘存储接口需要 unionId）。

    asin-monitor 的实现验证了 v1.0 access_token 可直接用于 OAPI v2/user/get，
    不需要重新走 oapi gettoken。
    """
    resp = requests.post(
        OAPI_USER_GET_URL,
        params={"access_token": access_token},
        json={"userid": user_id},
        timeout=20,
    )
    data = _json_response(resp, label="oapi user/get")
    union_id = (data.get("result") or {}).get("unionid") or (data.get("result") or {}).get("union_id")
    if not union_id:
        raise RuntimeError(f"unionid missing: {data}")
    return union_id


def list_dentries(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    parent_id: str,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    next_token = ""
    items: list[dict[str, Any]] = []
    while True:
        params: dict[str, Any] = {
            "unionId": union_id,
            "parentId": parent_id,
            "maxResults": max_results,
        }
        if next_token:
            params["nextToken"] = next_token
        data = _storage_request(
            "GET",
            access_token=access_token,
            space_id=space_id,
            path="dentries",
            params=params,
            timeout=30,
            label="list dentries",
        )
        dentries = data.get("dentries") or []
        if isinstance(dentries, dict):
            dentries = [dentries]
        items.extend(entry for entry in dentries if isinstance(entry, dict))
        next_token = str(data.get("nextToken") or "").strip()
        if not next_token:
            break
    return items


def find_child_folder(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    parent_id: str,
    name: str,
) -> dict[str, Any] | None:
    for entry in list_dentries(
        access_token,
        space_id=space_id,
        union_id=union_id,
        parent_id=parent_id,
    ):
        if str(entry.get("type", "")).upper() != "FOLDER":
            continue
        if str(entry.get("name", "")).strip() != name:
            continue
        return entry
    return None


def create_folder(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    parent_id: str,
    name: str,
) -> dict[str, Any]:
    return _storage_request(
        "POST",
        access_token=access_token,
        space_id=space_id,
        path=f"dentries/{quote(parent_id, safe='')}/folders",
        params={"unionId": union_id},
        json_body={"name": name},
        timeout=30,
        label="create folder",
    )


def ensure_child_folder(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    parent_id: str,
    folder_name: str,
) -> dict[str, Any]:
    """在 parent 下确保有名为 folder_name 的子文件夹，存在则复用。"""
    existing = find_child_folder(
        access_token,
        space_id=space_id,
        union_id=union_id,
        parent_id=parent_id,
        name=folder_name,
    )
    if existing:
        folder_id = str(existing.get("id") or existing.get("uuid") or existing.get("dentryUuid") or "")
        if not folder_id:
            raise RuntimeError(f"existing child folder missing id: {existing}")
        print(f"[dingpan] 复用已存在子文件夹: {folder_name} ({folder_id})")
        return {"id": folder_id, "name": folder_name, "created": False, "dentry": existing}

    try:
        created = create_folder(
            access_token,
            space_id=space_id,
            union_id=union_id,
            parent_id=parent_id,
            name=folder_name,
        )
        dentry = created.get("dentry") or {}
        folder_id = str(dentry.get("id") or dentry.get("uuid") or dentry.get("dentryUuid") or "")
        if folder_id:
            print(f"[dingpan] 已创建日期子文件夹: {folder_name} ({folder_id})")
            return {"id": folder_id, "name": folder_name, "created": True, "dentry": dentry}
    except Exception as exc:
        print(f"[dingpan] 创建子文件夹失败，回退查找: {exc}")
    raise RuntimeError(f"unable to ensure child folder: {folder_name}")


def _query_upload_info(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    name: str,
    size: int,
    parent_id: str,
) -> dict[str, Any]:
    return _storage_request(
        "POST",
        access_token=access_token,
        space_id=space_id,
        path="files/uploadInfos/query",
        params={"unionId": union_id},
        json_body={
            "protocol": "HEADER_SIGNATURE",
            "multipart": False,
            "fileName": name,
            "fileSize": size,
            "parentId": parent_id,
        },
        timeout=30,
        label="uploadInfos/query",
    )


def _put_to_oss(oss_url: str, headers: dict[str, str], file_path: Path) -> None:
    with file_path.open("rb") as f:
        resp = requests.put(oss_url, data=f, headers=headers, timeout=120)
    if not resp.ok:
        raise RuntimeError(f"OSS PUT failed: HTTP {resp.status_code} {resp.text[:300]}")


def _commit_dentry(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    upload_key: str,
    name: str,
    parent_id: str,
) -> dict[str, Any]:
    return _storage_request(
        "POST",
        access_token=access_token,
        space_id=space_id,
        path="files/commit",
        params={"unionId": union_id},
        json_body={
            "uploadKey": upload_key,
            "name": name,
            "parentId": parent_id,
        },
        timeout=30,
        label="files/commit",
    )


def upload_file(
    access_token: str,
    *,
    space_id: str,
    union_id: str,
    parent_id: str,
    file_path: Path,
    name: str | None = None,
) -> dict[str, Any]:
    """三步上传：query uploadInfo → PUT OSS → commit dentry。"""
    upload_name = name or file_path.name
    info = _query_upload_info(
        access_token,
        space_id=space_id,
        union_id=union_id,
        name=upload_name,
        size=file_path.stat().st_size,
        parent_id=parent_id,
    )
    upload_key = info.get("uploadKey")
    header_info = info.get("headerSignatureInfo") or {}
    resource_urls = header_info.get("resourceUrls") or []
    oss_headers = header_info.get("headers") or {}
    if not upload_key or not resource_urls:
        raise RuntimeError(f"unexpected uploadInfos/query response: {info}")
    _put_to_oss(resource_urls[0], oss_headers, file_path)
    commit = _commit_dentry(
        access_token,
        space_id=space_id,
        union_id=union_id,
        upload_key=upload_key,
        name=upload_name,
        parent_id=parent_id,
    )
    return {"upload_info": info, "commit": commit, "name": upload_name}


def extract_file_id(commit: dict[str, Any]) -> str:
    dentry = commit.get("dentry") or {}
    if isinstance(dentry, dict):
        for key in ("id", "uuid", "dentryUuid"):
            value = dentry.get(key)
            if value:
                return str(value)
    for key in ("id", "uuid", "dentryUuid"):
        value = commit.get(key)
        if value:
            return str(value)
    return ""


def build_preview_url(space_id: str, file_id: str, file_type: str = "file") -> str:
    return (
        "https://qr.dingtalk.com/page/yunpan?"
        f"route=previewDentry&spaceId={quote(space_id)}&fileId={quote(file_id)}&type={quote(file_type)}"
    )
