#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP facade：触发 FBA 指标入库。

  python -m fba_alert.main --schedule

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
from typing import Any, Optional

from aiohttp import web

from .application import IngestJobResult, run_ingest_job
from .lingxing import LingxingClient
from .runtime import load_runtime_config
from .scopes import AlertScope
from .utils import resolve_today


@dataclass
class JobRecord:
    job_id: str
    status: str  # queued | running | done | failed
    created_at: float
    scope: str
    dry_run: bool = False
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, scope: str, dry_run: bool) -> JobRecord:
        job = JobRecord(
            job_id=str(uuid.uuid4()),
            status="queued",
            created_at=time.time(),
            scope=scope,
            dry_run=dry_run,
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


def _result_to_dict(result: IngestJobResult) -> dict[str, Any]:
    return {
        "fetched_count": result.fetched_count,
        "metric_count": result.metric_count,
        "written_count": result.written_count,
        "sid_distribution": result.sid_distribution,
        "brands": result.brands,
    }


def _job_to_dict(job: JobRecord) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "created_at": job.created_at,
        "scope": job.scope,
        "dry_run": job.dry_run,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result": job.result,
        "error": job.error,
    }


def create_app(*, env_file: str = ".env", api_token: str = "") -> web.Application:
    store = JobStore()
    token = (api_token or "").strip()

    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        if request.path in {"/healthz", "/readyz"}:
            return await handler(request)
        if not token:
            return web.json_response({"error": "FBA_ALERT_API_TOKEN not configured"}, status=503)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.json_response({"error": "missing bearer token"}, status=401)
        provided = auth[len("Bearer ") :].strip()
        if not secrets.compare_digest(provided, token):
            return web.json_response({"error": "invalid token"}, status=401)
        return await handler(request)

    async def healthz(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def run_job(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        scope = str((body or {}).get("scope") or "libraton").strip().lower()
        try:
            AlertScope.parse(scope)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        dry_run = bool((body or {}).get("dry_run") or str((body or {}).get("mode") or "").lower() == "dry_run")

        job = await store.create(scope=scope, dry_run=dry_run)

        async def _worker() -> None:
            await store.update(job.job_id, status="running", started_at=time.time())
            try:
                config = load_runtime_config(env_file, dry_run)
                result = await run_ingest_job(
                    client=LingxingClient(config.lingxing),
                    today=resolve_today(""),
                    sid_list=config.lingxing.sid_list,
                    db_config=config.db,
                    scope=scope,
                    dry_run=dry_run,
                )
                await store.update(
                    job.job_id,
                    status="done",
                    finished_at=time.time(),
                    result=_result_to_dict(result),
                )
            except Exception as exc:
                await store.update(
                    job.job_id,
                    status="failed",
                    finished_at=time.time(),
                    error=repr(exc),
                )

        asyncio.create_task(_worker())
        return web.json_response(_job_to_dict(job), status=202)

    async def get_job(request: web.Request) -> web.Response:
        job = await store.get(request.match_info["job_id"])
        if not job:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(_job_to_dict(job))

    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/readyz", healthz)
    app.router.add_post("/v1/alerts/run", run_job)  # 兼容旧路径
    app.router.add_post("/v1/metrics/ingest", run_job)
    app.router.add_get("/v1/alerts/jobs/{job_id}", get_job)
    app.router.add_get("/v1/metrics/jobs/{job_id}", get_job)
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="FBA metric ingest API")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--host", default=os.getenv("FBA_ALERT_API_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FBA_ALERT_API_PORT", "8090")))
    args = parser.parse_args()
    token = os.getenv("FBA_ALERT_API_TOKEN", "").strip()
    app = create_app(env_file=args.env_file, api_token=token)
    web.run_app(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
