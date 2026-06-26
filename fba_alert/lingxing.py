#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import base64
import copy
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import aiohttp
from Crypto.Cipher import AES

from .config import LingxingConfig
from .utils import json_dumps, safe_int

BLOCK_SIZE = 16
SUMMARY_ROUTE = "/erp/sc/routing/restocking/analysis/getSummaryList"
SELLER_LIST_ROUTE = "/erp/sc/data/seller/lists"
LISTING_ROUTE = "/erp/sc/data/mws/listing"
SOURCE_LIST_ROUTE = "/erp/sc/routing/fbaSug/asin/getSourceList"


@dataclass(frozen=True)
class InventorySnapshot:
    fba_sellable_inventory: int
    fba_transfer_reserved_inventory: int
    fba_processing_inventory: int
    fba_inventory: int
    fba_inbound_inventory: int


class SourceListRateLimitError(RuntimeError):
    def __init__(self, resp: dict):
        super().__init__(f"SourceList 接口返回失败: {resp}")
        self.resp = resp


class ListingRateLimitError(RuntimeError):
    def __init__(self, resp: dict):
        super().__init__(f"Listing 接口返回失败: {resp}")
        self.resp = resp


def aggregate_inventory_snapshot(type_1_rows: list[dict], type_2_rows: list[dict]) -> InventorySnapshot:
    fba_sellable_inventory = 0
    fba_transfer_reserved_inventory = 0
    fba_processing_inventory = 0
    for row in type_1_rows:
        remark = row.get("remark") or {}
        fba_sellable_inventory += safe_int(remark.get("afn_fulfillable_quantity"))
        fba_transfer_reserved_inventory += safe_int(remark.get("reserved_fc_transfers"))
        fba_processing_inventory += safe_int(remark.get("reserved_fc_processing"))

    fba_inbound_inventory = sum(safe_int(row.get("quantity")) for row in type_2_rows)
    return InventorySnapshot(
        fba_sellable_inventory=fba_sellable_inventory,
        fba_transfer_reserved_inventory=fba_transfer_reserved_inventory,
        fba_processing_inventory=fba_processing_inventory,
        fba_inventory=fba_sellable_inventory + fba_transfer_reserved_inventory + fba_processing_inventory,
        fba_inbound_inventory=fba_inbound_inventory,
    )


def is_rate_limited_response(resp: dict) -> bool:
    code = str(resp.get("code") or "").strip()
    message = str(resp.get("msg") or resp.get("message") or "").strip().lower()
    return code == "3001008" or "too frequently" in message


def is_transient_connection_error_response(resp: dict) -> bool:
    code = str(resp.get("code") or "").strip()
    if code != "500":
        return False

    data = resp.get("data") or {}
    haystacks = [
        str(resp.get("msg") or "").strip().lower(),
        str(resp.get("message") or "").strip().lower(),
        str(resp.get("error_details") or "").strip().lower(),
        str(data.get("throwable") or "").strip().lower(),
    ]
    transient_markers = (
        "请求连接异常",
        "request connection exception",
        "网络错误",
        "illegalreferencecountexception",
    )
    return any(marker in haystack for marker in transient_markers for haystack in haystacks)


def is_source_list_rate_limited_response(resp: dict) -> bool:
    return is_rate_limited_response(resp)


def do_pad(text: str) -> str:
    return text + (BLOCK_SIZE - len(text) % BLOCK_SIZE) * chr(BLOCK_SIZE - len(text) % BLOCK_SIZE)


def aes_encrypt(key: str, data: str) -> str:
    cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
    result = cipher.encrypt(do_pad(data).encode("utf-8"))
    return base64.b64encode(result).decode("utf-8")


def md5_encrypt(text: str) -> str:
    md = hashlib.md5()
    md.update(text.encode("utf-8"))
    return md.hexdigest()


class HttpClient:
    def __init__(self, default_timeout: int = 30):
        self.default_timeout = default_timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.BaseConnector] = None

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        self._connector = None

    async def _get_session(self, ssl: Any) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session

        proxy_url = os.getenv("LINGXING_PROXY")
        if proxy_url and proxy_url.startswith("socks5://") and not proxy_url.startswith("socks5h://"):
            proxy_url = "socks5h" + proxy_url[len("socks5") :]

        self._connector = None
        if proxy_url:
            try:
                from aiohttp_socks import ProxyConnector

                self._connector = ProxyConnector.from_url(proxy_url, verify_ssl=ssl is not False)
            except ImportError as exc:
                raise RuntimeError("需要安装 aiohttp_socks 才能使用 SOCKS 代理: pip install aiohttp_socks") from exc

        self._session = aiohttp.ClientSession(connector=self._connector, trust_env=True)
        return self._session

    async def request(
        self,
        method: str,
        req_url: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        headers: Optional[dict] = None,
        **kwargs: Any,
    ) -> dict:
        timeout = kwargs.pop("timeout", self.default_timeout)
        ssl = kwargs.pop("ssl", None)
        retries = int(kwargs.pop("retries", 3))
        data = json_dumps(json_body) if json_body else None

        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                session = await self._get_session(ssl)
                async with session.request(
                    method=method,
                    url=req_url,
                    params=params,
                    data=data,
                    timeout=timeout,
                    headers=headers,
                    ssl=ssl,
                    **kwargs,
                ) as resp:
                    body_text = await resp.text()
                    if resp.status != 200:
                        raise ValueError(f"Response error, status code: {resp.status}, body: {body_text}")
                    return json_module_loads(body_text)
            except (aiohttp.ClientPayloadError, aiohttp.ClientConnectionError, asyncio.TimeoutError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if attempt >= retries:
                    break
                await asyncio.sleep(min(attempt, 3))

        raise RuntimeError(f"领星请求失败，已重试 {retries} 次: {last_error}") from last_error


def json_module_loads(text: str) -> dict:
    if not text:
        return {}
    return json.loads(text)


class Signer:
    @classmethod
    def generate_sign(cls, encrypt_key: str, request_params: dict) -> str:
        canonical_querystring = cls.format_params(request_params)
        md5_str = md5_encrypt(canonical_querystring).upper()
        return aes_encrypt(encrypt_key, md5_str)

    @classmethod
    def format_params(cls, request_params: Union[None, dict] = None) -> str:
        if not request_params or not isinstance(request_params, dict):
            return ""

        canonical_strs = []
        for key in sorted(request_params.keys()):
            value = request_params[key]
            if value == "":
                continue
            if isinstance(value, (dict, list)):
                canonical_strs.append(f"{key}={json_dumps(value).decode('utf-8')}")
            else:
                canonical_strs.append(f"{key}={value}")
        return "&".join(canonical_strs)


class LingxingClient:
    def __init__(self, config: LingxingConfig):
        self.config = config
        self.http = HttpClient()
        self.request_kwargs = {} if config.ssl_verify else {"ssl": False}
        self._source_list_cache: dict[tuple[str, str, str], list[dict]] = {}

    async def __aenter__(self) -> "LingxingClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self.http.close()

    async def fetch_access_token(self) -> str:
        print(f"[lingxing] 获取 access_token: url={self.config.token_url}")
        ssl = None if self.config.ssl_verify else False
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                self.config.token_url,
                json={"api_key": self.config.token_request_key},
                ssl=ssl,
            ) as resp:
                token_resp = await resp.json()
        access_token = token_resp.get("access_token")
        if not access_token:
            raise RuntimeError(f"获取领星 access_token 失败: {token_resp}")
        print("[lingxing] access_token 获取成功")
        return access_token

    async def request(
        self,
        access_token: str,
        route_name: str,
        method: str,
        req_params: Optional[dict] = None,
        req_body: Optional[dict] = None,
        **kwargs: Any,
    ) -> dict:
        req_url = self.config.api_host + route_name
        headers = kwargs.pop("headers", {})

        req_params = req_params or {}
        gen_sign_params = copy.deepcopy(req_body) if req_body else {}
        if req_params:
            gen_sign_params.update(req_params)

        sign_params = {
            "app_key": self.config.app_id,
            "access_token": access_token,
            "timestamp": f"{int(time.time())}",
        }
        gen_sign_params.update(sign_params)
        sign = Signer.generate_sign(self.config.app_id, gen_sign_params)
        sign_params["sign"] = sign
        req_params.update(sign_params)

        if req_body and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        merged_kwargs = {**self.request_kwargs, **kwargs}
        return await self.http.request(
            method,
            req_url,
            params=req_params,
            headers=headers,
            json_body=req_body,
            **merged_kwargs,
        )

    async def request_with_rate_limit_retry(
        self,
        access_token: str,
        route_name: str,
        method: str,
        req_params: Optional[dict] = None,
        req_body: Optional[dict] = None,
        retries: int = 3,
        **kwargs: Any,
    ) -> dict:
        resp: dict = {}
        for attempt in range(1, retries + 1):
            resp = await self.request(
                access_token,
                route_name,
                method,
                req_params=req_params,
                req_body=req_body,
                **kwargs,
            )
            if safe_int(resp.get("code")) == 0:
                return resp
            if (is_rate_limited_response(resp) or is_transient_connection_error_response(resp)) and attempt < retries:
                await asyncio.sleep(attempt)
                continue
            return resp
        return resp

    async def fetch_seller_map(self, access_token: str) -> dict[str, str]:
        print("[lingxing] 查询店铺列表")
        resp = await self.request_with_rate_limit_retry(access_token, SELLER_LIST_ROUTE, "GET")
        if safe_int(resp.get("code")) != 0:
            raise RuntimeError(f"店铺列表接口返回失败: {resp}")
        mapping: dict[str, str] = {}
        for seller in resp.get("data") or []:
            sid = str(seller.get("sid") or "").strip()
            name = str(seller.get("name") or "").strip()
            if sid and name:
                mapping[sid] = name
        print(f"[lingxing] 店铺映射完成: {mapping}")
        return mapping

    async def fetch_summary_items(
        self,
        access_token: str,
        sid_list: Optional[list[str]] = None,
        data_type: Optional[int] = None,
    ) -> list[dict]:
        all_rows: list[dict] = []
        offset = 0
        total = None
        page_no = 0
        effective_sid_list = sid_list or self.config.sid_list
        effective_data_type = self.config.data_type if data_type is None else data_type

        while total is None or offset < total:
            page_no += 1
            print(f"[lingxing] 拉取补货建议: page={page_no} offset={offset} length={self.config.page_size}")
            req_body = {
                "sid_list": effective_sid_list,
                "data_type": effective_data_type,
                "mode": self.config.mode,
                "offset": offset,
                "length": self.config.page_size,
            }
            if page_no == 1:
                print(f"[lingxing] 请求体: {req_body}")
            resp = await self.request_with_rate_limit_retry(access_token, SUMMARY_ROUTE, "POST", req_body=req_body)
            if safe_int(resp.get("code")) != 0:
                raise RuntimeError(f"领星接口返回失败: {resp}")
            data = resp.get("data") or []
            total = safe_int(resp.get("total"))
            if not data:
                print(f"[lingxing] page={page_no} 无数据，结束")
                break
            all_rows.extend(data)
            offset += len(data)
            print(f"[lingxing] page={page_no} 返回={len(data)} total={total} 累计={len(all_rows)}")
            if len(data) < self.config.page_size:
                break

        print(f"[lingxing] 补货建议拉取完成: total_rows={len(all_rows)}")
        return all_rows

    async def fetch_listing_items_by_asins(self, access_token: str, sid_asin_map: dict[str, set[str]]) -> list[dict]:
        last_error: Optional[ListingRateLimitError] = None
        for concurrency in self._listing_concurrency_levels():
            semaphore = asyncio.Semaphore(concurrency)
            tasks = []
            for sid, asin_set in sid_asin_map.items():
                asins = sorted(asin for asin in asin_set if asin)
                for index in range(0, len(asins), 10):
                    search_values = asins[index : index + 10]
                    if search_values:
                        tasks.append(self._fetch_listing_batch(access_token, sid, search_values, index // 10 + 1, semaphore))
            try:
                all_rows: list[dict] = []
                for rows in await self._gather_with_cancellation(tasks):
                    all_rows.extend(rows)
                print(f"[lingxing] Listing 拉取完成: total_rows={len(all_rows)}")
                return all_rows
            except ListingRateLimitError as exc:
                last_error = exc
                if concurrency <= 1:
                    break
                print(f"[lingxing] Listing 遇到限流，降低并发后重试: concurrency={concurrency} -> next")
                await asyncio.sleep(1)
        if last_error is not None:
            raise last_error
        print("[lingxing] Listing 拉取完成: total_rows=0")
        return []

    async def _fetch_listing_batch(
        self,
        access_token: str,
        sid: str,
        search_values: list[str],
        batch_no: int,
        semaphore: asyncio.Semaphore,
    ) -> list[dict]:
        async with semaphore:
            rows: list[dict] = []
            offset = 0
            page_no = 0
            total = None
            while total is None or offset < total:
                page_no += 1
                req_body = {
                    "sid": sid,
                    "is_delete": 0,
                    "search_field": "asin",
                    "search_value": search_values,
                    "exact_search": 1,
                    "offset": offset,
                    "length": 1000,
                }
                print(
                    "[lingxing] 拉取 Listing: "
                    f"sid={sid} batch={batch_no} page={page_no} "
                    f"offset={offset} asins={search_values}"
                )
                resp = await self.request_with_rate_limit_retry(access_token, LISTING_ROUTE, "POST", req_body=req_body)
                if safe_int(resp.get("code")) != 0:
                    if is_rate_limited_response(resp):
                        raise ListingRateLimitError(resp)
                    raise RuntimeError(f"Listing 接口返回失败: {resp}")
                data = resp.get("data") or []
                total = safe_int(resp.get("total"))
                if not data:
                    break
                rows.extend(data)
                offset += len(data)
                if len(data) < 1000:
                    break
            return rows

    async def fetch_source_list(self, access_token: str, sid: str, asin: str, source_type: str) -> list[dict]:
        cache_key = (sid, asin, str(source_type))
        cached_rows = self._load_source_list_cache(cache_key)
        if cached_rows is not None:
            return cached_rows

        req_body = {
            "sid": safe_int(sid),
            "asin": asin,
            "type": str(source_type),
            "mode": str(self.config.mode),
        }
        print(f"[lingxing] 拉取 SourceList: sid={sid} asin={asin} type={source_type}")
        resp = await self.request_with_rate_limit_retry(access_token, SOURCE_LIST_ROUTE, "POST", req_body=req_body)
        if safe_int(resp.get("code")) != 0:
            if is_source_list_rate_limited_response(resp):
                raise SourceListRateLimitError(resp)
            raise RuntimeError(f"SourceList 接口返回失败: {resp}")
        data = resp.get("data") or {}
        rows = data.get("source_list") or []
        self._store_source_list_cache(cache_key, rows)
        return rows

    def _load_source_list_cache(self, cache_key: tuple[str, str, str]) -> Optional[list[dict]]:
        if cache_key in self._source_list_cache:
            return self._source_list_cache[cache_key]
        if not self.config.source_list_cache_enabled:
            return None

        cache_path = self._build_source_list_cache_path(cache_key)
        if not cache_path.exists():
            return None
        rows = json.loads(cache_path.read_text(encoding="utf-8"))
        self._source_list_cache[cache_key] = rows
        return rows

    def _store_source_list_cache(self, cache_key: tuple[str, str, str], rows: list[dict]) -> None:
        self._source_list_cache[cache_key] = rows
        if not self.config.source_list_cache_enabled:
            return
        cache_path = self._build_source_list_cache_path(cache_key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def _build_source_list_cache_path(self, cache_key: tuple[str, str, str]) -> Path:
        sid, asin, source_type = cache_key
        cache_date = datetime.now().date().isoformat()
        file_name = f"{sid}-{asin}-{source_type}-mode{self.config.mode}.json"
        return Path(self.config.source_list_cache_dir) / cache_date / file_name

    def _source_list_concurrency_levels(self) -> list[int]:
        levels = [self.config.source_list_concurrency]
        if self.config.source_list_concurrency > 2:
            levels.append(2)
        if self.config.source_list_concurrency > 1:
            levels.append(1)
        return levels

    def _listing_concurrency_levels(self) -> list[int]:
        levels = [self.config.listing_concurrency]
        if self.config.listing_concurrency > 2:
            levels.append(2)
        if self.config.listing_concurrency > 1:
            levels.append(1)
        return levels

    async def _gather_with_cancellation(self, coroutines: list[Any]) -> list[Any]:
        tasks = [asyncio.create_task(coro) for coro in coroutines]
        try:
            return await asyncio.gather(*tasks)
        except Exception:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def fetch_inventory_snapshot_map(self, access_token: str, sid_asin_map: dict[str, set[str]]) -> dict[tuple[str, str], InventorySnapshot]:
        last_error: Optional[SourceListRateLimitError] = None
        for concurrency in self._source_list_concurrency_levels():
            semaphore = asyncio.Semaphore(concurrency)
            tasks = []
            for sid, asin_set in sid_asin_map.items():
                for asin in sorted(asin for asin in asin_set if asin):
                    tasks.append(self._fetch_inventory_snapshot_pair(access_token, sid, asin, semaphore))
            try:
                snapshot_map = dict(await self._gather_with_cancellation(tasks))
                print(f"[lingxing] SourceList 库存汇总完成: total_pairs={len(snapshot_map)}")
                return snapshot_map
            except SourceListRateLimitError as exc:
                last_error = exc
                if concurrency <= 1:
                    break
                print(f"[lingxing] SourceList 遇到限流，降低并发后重试: concurrency={concurrency} -> next")
                await asyncio.sleep(1)
        if last_error is not None:
            raise last_error
        print("[lingxing] SourceList 库存汇总完成: total_pairs=0")
        return {}

    async def _fetch_inventory_snapshot_pair(
        self,
        access_token: str,
        sid: str,
        asin: str,
        semaphore: asyncio.Semaphore,
    ) -> tuple[tuple[str, str], InventorySnapshot]:
        async with semaphore:
            type_1_rows = await self.fetch_source_list(access_token, sid, asin, "1")
            type_2_rows = await self.fetch_source_list(access_token, sid, asin, "2")
        return (sid, asin), aggregate_inventory_snapshot(type_1_rows, type_2_rows)
