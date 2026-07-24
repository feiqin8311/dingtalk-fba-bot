#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thin HTTP facade over run_alert_job for YidaLab (and other callers).

Production (one process with weekly cron):

  python -m fba_alert.main --schedule

Standalone API only (debug / no cron):

  python -m fba_alert.api_server --host 0.0.0.0 --port 8090

Auth: Authorization: Bearer <FBA_ALERT_API_TOKEN>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from aiohttp import web

from .application import AlertJobResult, run_alert_job
from .dingtalk import DingTalkNotifier
from .lingxing import LingxingClient
from .report import export_alert_report
from .runtime import load_runtime_config
from .scopes import AlertScope
from .utils import resolve_today


class AlertMode(str, Enum):
    SELF = "self"
    BROADCAST = "broadcast"
    DRY_RUN = "dry_run"
    UPLOAD_ONLY = "upload_only"

    @classmethod
    def parse(cls, value: str) -> "AlertMode":
        normalized = (value or cls.SELF.value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(
                f"unsupported mode: {value}; expected self|broadcast|dry_run|upload_only"
            ) from exc


@dataclass
class JobRecord:
    job_id: str
    status: str  # queued | running | done | failed
    created_at: float
    scope: str
    mode: str
    notify_user_ids: list[str] = field(default_factory=list)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class JobStore:
    """In-memory job table. Enough for single-process API; swap for Redis if multi-instance."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, scope: str, mode: str, notify_user_ids: list[str]) -> JobRecord:
        job = JobRecord(
            job_id=str(uuid.uuid4()),
            status="queued",
            created_at=time.time(),
            scope=scope,
            mode=mode,
            notify_user_ids=list(notify_user_ids),
        )
        async with self._lock:
            self._jobs[job.job_id] = job
        return job

    async def get(self, job_id: str) -> Optional[JobRecord]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields: Any) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in fields.items():
                setattr(job, key, value)


def _result_to_dict(result: AlertJobResult) -> dict[str, Any]:
    preview_urls = result.preview_urls or {}
    return {
        "fetched_count": result.fetched_count,
        "alert_count": result.alert_count,
        "report_path": result.report_path,
        "sid_distribution": result.sid_distribution,
        # Same shape as YidaLab dingpan delivery so callers can show the link in chat.
        "preview_url": result.preview_url or "",
        "preview_urls": preview_urls,
    }


def _job_to_dict(job: JobRecord) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "scope": job.scope,
        "mode": job.mode,
        "notify_user_ids": job.notify_user_ids,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result": job.result,
        "error": job.error,
    }


def _check_auth(request: web.Request, token: str) -> None:
    if not token:
        raise web.HTTPServiceUnavailable(text="FBA_ALERT_API_TOKEN is not configured")
    header = request.headers.get("Authorization", "")
    expected = f"Bearer {token}"
    # secrets.compare_digest requires equal length; pad-safe check via secrets
    provided = header if header.startswith("Bearer ") else ""
    if not provided or not secrets.compare_digest(provided, expected):
        raise web.HTTPUnauthorized(text="unauthorized")


def _parse_run_body(body: dict[str, Any]) -> tuple[str, AlertMode, list[str]]:
    scope_raw = str(body.get("scope") or "all").strip().lower()
    # Validate scope early via enum
    AlertScope.parse(scope_raw)

    mode = AlertMode.parse(str(body.get("mode") or AlertMode.SELF.value))
    raw_ids = body.get("notify_user_ids") or []
    if isinstance(raw_ids, str):
        notify_user_ids = [raw_ids.strip()] if raw_ids.strip() else []
    elif isinstance(raw_ids, list):
        notify_user_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
    else:
        raise ValueError("notify_user_ids must be a string or list of strings")

    if mode is AlertMode.SELF and not notify_user_ids:
        raise ValueError("mode=self requires notify_user_ids (injected by YidaLab server)")

    if mode is AlertMode.BROADCAST and notify_user_ids:
        # Broadcast uses store_policies matrix; ignore client overrides for safety clarity
        notify_user_ids = []

    return scope_raw, mode, notify_user_ids


async def _execute_job(
    store: JobStore,
    job_id: str,
    *,
    env_file: str,
    scope: str,
    mode: AlertMode,
    notify_user_ids: list[str],
) -> None:
    await store.update(job_id, status="running", started_at=time.time())
    dry_run = mode is AlertMode.DRY_RUN
    upload_only = mode is AlertMode.UPLOAD_ONLY
    override_ids = notify_user_ids if mode is AlertMode.SELF else []

    try:
        config = load_runtime_config(env_file, dry_run)
        today = resolve_today("")
        notifier = None if dry_run else DingTalkNotifier(config.dingtalk)
        result = await run_alert_job(
            client=LingxingClient(config.lingxing),
            today=today,
            sid_list=config.lingxing.sid_list,
            exporter=export_alert_report,
            notifier=notifier,
            notify_user_ids=config.dingtalk.user_ids,
            notify_user_override_ids=override_ids,
            dry_run=dry_run,
            scope=scope,
            upload_only=upload_only,
            dingtalk_config=config.dingtalk,
        )
        await store.update(
            job_id,
            status="done",
            finished_at=time.time(),
            result=_result_to_dict(result),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 — surface any job failure to caller
        await store.update(
            job_id,
            status="failed",
            finished_at=time.time(),
            result=None,
            error=str(exc),
        )


def create_app(
    *,
    env_file: str = ".env",
    api_token: Optional[str] = None,
    store: Optional[JobStore] = None,
) -> web.Application:
    token = api_token if api_token is not None else os.getenv("FBA_ALERT_API_TOKEN", "").strip()
    job_store = store or JobStore()
    app = web.Application()
    # aiohttp AppKey avoids NotAppKeyWarning on app[key]
    KEY_ENV = web.AppKey("env_file", str)
    KEY_TOKEN = web.AppKey("api_token", str)
    KEY_STORE = web.AppKey("job_store", JobStore)
    app[KEY_ENV] = env_file
    app[KEY_TOKEN] = token
    app[KEY_STORE] = job_store

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "service": "dingtalk-fba-bot-api"})

    async def run_alert(request: web.Request) -> web.Response:
        _check_auth(request, request.app[KEY_TOKEN])
        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise web.HTTPBadRequest(text=f"invalid json: {exc}") from exc
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="body must be a JSON object")

        try:
            scope, mode, notify_user_ids = _parse_run_body(body)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc

        store_: JobStore = request.app[KEY_STORE]
        job = await store_.create(scope, mode.value, notify_user_ids)
        asyncio.create_task(
            _execute_job(
                store_,
                job.job_id,
                env_file=request.app[KEY_ENV],
                scope=scope,
                mode=mode,
                notify_user_ids=notify_user_ids,
            )
        )
        return web.json_response(_job_to_dict(job), status=202)

    async def get_job(request: web.Request) -> web.Response:
        _check_auth(request, request.app[KEY_TOKEN])
        job_id = request.match_info["job_id"]
        store_: JobStore = request.app[KEY_STORE]
        job = await store_.get(job_id)
        if not job:
            raise web.HTTPNotFound(text="job not found")
        return web.json_response(_job_to_dict(job))

    app.router.add_get("/health", health)
    app.router.add_post("/v1/alerts/run", run_alert)
    app.router.add_get("/v1/alerts/jobs/{job_id}", get_job)
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="dingtalk-fba-bot HTTP API")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--host", default=os.getenv("FBA_ALERT_API_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("FBA_ALERT_API_PORT", "8090")),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.getenv("FBA_ALERT_API_TOKEN", "").strip()
    if not token:
        print("[api] WARNING: FBA_ALERT_API_TOKEN is empty; all requests will 503")
    app = create_app(env_file=args.env_file, api_token=token)
    print(f"[api] listening on {args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
