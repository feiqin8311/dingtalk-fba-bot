import asyncio
import tempfile
import unittest

from fba_alert.config import LingxingConfig
from fba_alert.lingxing import InventorySnapshot, LingxingClient, ListingRateLimitError, SourceListRateLimitError


def make_config() -> LingxingConfig:
    return LingxingConfig(
        api_host="http://example.com",
        app_id="app",
        app_secret="secret",
        token_url="http://example.com/token",
        token_request_key="app",
        ssl_verify=True,
        sid_list=["1448"],
        data_type=1,
        mode=0,
        page_size=50,
        listing_concurrency=3,
        source_list_concurrency=3,
        source_list_cache_enabled=False,
        source_list_cache_dir=".cache/fba_alert/source_list",
    )


class LingxingClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_context_manager_closes_underlying_http_session(self) -> None:
        client = LingxingClient(make_config())
        session = await client.http._get_session(None)

        async with client as managed_client:
            self.assertIs(managed_client, client)
            self.assertIs(await client.http._get_session(None), session)
            self.assertFalse(session.closed)

        self.assertTrue(session.closed)
        self.assertIsNone(client.http._session)

    async def test_fetch_seller_map_retries_rate_limited_response(self) -> None:
        client = LingxingClient(make_config())
        calls = 0

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
            return {"code": 0, "data": [{"sid": "1448", "name": "Libraton EU-DE"}]}

        client.request = fake_request  # type: ignore[method-assign]

        seller_map = await client.fetch_seller_map("token")

        self.assertEqual(seller_map, {"1448": "Libraton EU-DE"})
        self.assertEqual(calls, 2)

    async def test_fetch_summary_items_retries_rate_limited_response(self) -> None:
        client = LingxingClient(make_config())
        calls = 0

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
            return {
                "code": 0,
                "data": [{"basic_info": {"asin": "B001"}}],
                "total": 1,
            }

        client.request = fake_request  # type: ignore[method-assign]

        rows = await client.fetch_summary_items("token", ["1448"])

        self.assertEqual(rows, [{"basic_info": {"asin": "B001"}}])
        self.assertEqual(calls, 2)

    async def test_fetch_seller_map_raises_after_retry_budget_exhausted(self) -> None:
        client = LingxingClient(make_config())

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            return {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}

        client.request = fake_request  # type: ignore[method-assign]

        with self.assertRaisesRegex(RuntimeError, "店铺列表接口返回失败"):
            await client.fetch_seller_map("token")

    async def test_fetch_source_list_uses_cache_after_first_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = make_config()
            config.source_list_cache_enabled = True
            config.source_list_cache_dir = tmp_dir
            client = LingxingClient(config)
            calls = 0

            async def fake_request(
                access_token: str,
                route_name: str,
                method: str,
                req_params: dict | None = None,
                req_body: dict | None = None,
                **kwargs: object,
            ) -> dict:
                nonlocal calls
                calls += 1
                return {"code": 0, "data": {"source_list": [{"quantity": 5}]}}

            client.request = fake_request  # type: ignore[method-assign]

            rows1 = await client.fetch_source_list("token", "1448", "B001", "2")
            rows2 = await client.fetch_source_list("token", "1448", "B001", "2")

            self.assertEqual(rows1, [{"quantity": 5}])
            self.assertEqual(rows2, [{"quantity": 5}])
            self.assertEqual(calls, 1)

    async def test_fetch_source_list_retries_transient_connection_error_response(self) -> None:
        client = LingxingClient(make_config())
        calls = 0

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"code": "500", "msg": "请求连接异常,请稍后再试", "data": None}
            return {"code": 0, "data": {"source_list": [{"quantity": 5}]}}

        client.request = fake_request  # type: ignore[method-assign]

        rows = await client.fetch_source_list("token", "1448", "B001", "2")

        self.assertEqual(rows, [{"quantity": 5}])
        self.assertEqual(calls, 2)

    async def test_fetch_source_list_retries_transient_server_error_response(self) -> None:
        client = LingxingClient(make_config())
        calls = 0

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "code": "500",
                    "msg": "io.netty.util.IllegalReferenceCountException: refCnt: 0, decrement: 1",
                    "data": {
                        "throwable": "io.netty.util.IllegalReferenceCountException: refCnt: 0, decrement: 1",
                    },
                }
            return {"code": 0, "data": {"source_list": [{"quantity": 5}]}}

        client.request = fake_request  # type: ignore[method-assign]

        rows = await client.fetch_source_list("token", "1448", "B001", "2")

        self.assertEqual(rows, [{"quantity": 5}])
        self.assertEqual(calls, 2)

    async def test_fetch_inventory_snapshot_map_processes_pairs_concurrently(self) -> None:
        client = LingxingClient(make_config())
        max_in_flight = 0
        in_flight = 0

        async def fake_fetch_source_list(access_token: str, sid: str, asin: str, source_type: str) -> list[dict]:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            if source_type == "1":
                return [{"remark": {"afn_fulfillable_quantity": 1, "reserved_fc_transfers": 2, "reserved_fc_processing": 3}}]
            return [{"quantity": 4}]

        client.fetch_source_list = fake_fetch_source_list  # type: ignore[method-assign]

        snapshot_map = await client.fetch_inventory_snapshot_map(
            "token",
            {"1448": {"A1", "A2", "A3"}},
        )

        self.assertEqual(len(snapshot_map), 3)
        self.assertEqual(snapshot_map[("1448", "A1")], InventorySnapshot(1, 2, 3, 6, 4))
        self.assertGreater(max_in_flight, 1)

    async def test_fetch_inventory_snapshot_pair_fetches_type_1_and_type_2_sequentially(self) -> None:
        client = LingxingClient(make_config())
        max_in_flight = 0
        in_flight = 0

        async def fake_fetch_source_list(access_token: str, sid: str, asin: str, source_type: str) -> list[dict]:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            if source_type == "1":
                return [{"remark": {"afn_fulfillable_quantity": 1, "reserved_fc_transfers": 2, "reserved_fc_processing": 3}}]
            return [{"quantity": 4}]

        client.fetch_source_list = fake_fetch_source_list  # type: ignore[method-assign]

        pair, snapshot = await client._fetch_inventory_snapshot_pair(
            "token",
            "1448",
            "A1",
            asyncio.Semaphore(3),
        )

        self.assertEqual(pair, ("1448", "A1"))
        self.assertEqual(snapshot, InventorySnapshot(1, 2, 3, 6, 4))
        self.assertEqual(max_in_flight, 1)

    async def test_fetch_inventory_snapshot_map_retries_with_lower_concurrency_after_rate_limit(self) -> None:
        client = LingxingClient(make_config())
        current_in_flight = 0
        max_in_flight = 0

        async def fake_fetch_source_list(access_token: str, sid: str, asin: str, source_type: str) -> list[dict]:
            nonlocal current_in_flight, max_in_flight
            current_in_flight += 1
            max_in_flight = max(max_in_flight, current_in_flight)
            try:
                await asyncio.sleep(0.01)
                if current_in_flight > 1:
                    raise SourceListRateLimitError(
                        {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
                    )
                if source_type == "1":
                    return [{"remark": {"afn_fulfillable_quantity": 1, "reserved_fc_transfers": 2, "reserved_fc_processing": 3}}]
                return [{"quantity": 4}]
            finally:
                current_in_flight -= 1

        client.fetch_source_list = fake_fetch_source_list  # type: ignore[method-assign]

        snapshot_map = await client.fetch_inventory_snapshot_map(
            "token",
            {"1448": {"A1", "A2", "A3"}},
        )

        self.assertEqual(len(snapshot_map), 3)
        self.assertEqual(snapshot_map[("1448", "A1")], InventorySnapshot(1, 2, 3, 6, 4))
        self.assertGreater(max_in_flight, 1)

    async def test_fetch_listing_items_by_asins_processes_batches_concurrently(self) -> None:
        client = LingxingClient(make_config())
        max_in_flight = 0
        in_flight = 0

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return {"code": 0, "data": [{"asin": asin} for asin in req_body["search_value"]], "total": len(req_body["search_value"])}

        client.request = fake_request  # type: ignore[method-assign]

        rows = await client.fetch_listing_items_by_asins(
            "token",
            {"1448": {f"A{i}" for i in range(25)}},
        )

        self.assertEqual(len(rows), 25)
        self.assertGreater(max_in_flight, 1)

    async def test_fetch_inventory_snapshot_map_cancels_pending_tasks_before_retrying(self) -> None:
        client = LingxingClient(make_config())
        first_round_failed = False
        cancelled_pairs: list[str] = []

        async def fake_fetch_pair(
            access_token: str,
            sid: str,
            asin: str,
            semaphore: asyncio.Semaphore,
        ) -> tuple[tuple[str, str], InventorySnapshot]:
            nonlocal first_round_failed
            async with semaphore:
                try:
                    if asin == "A1" and not first_round_failed:
                        first_round_failed = True
                        raise SourceListRateLimitError(
                            {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
                        )
                    await asyncio.sleep(0.05)
                    return (sid, asin), InventorySnapshot(1, 2, 3, 6, 4)
                except asyncio.CancelledError:
                    cancelled_pairs.append(asin)
                    raise

        client._fetch_inventory_snapshot_pair = fake_fetch_pair  # type: ignore[method-assign]

        snapshot_map = await client.fetch_inventory_snapshot_map("token", {"1448": {"A1", "A2"}})

        self.assertEqual(set(snapshot_map), {("1448", "A1"), ("1448", "A2")})
        self.assertIn("A2", cancelled_pairs)

    async def test_fetch_listing_items_by_asins_cancels_pending_batches_before_retrying(self) -> None:
        client = LingxingClient(make_config())
        first_round_failed = False
        cancelled_batches: list[tuple[str, ...]] = []

        async def fake_fetch_listing_batch(
            access_token: str,
            sid: str,
            search_values: list[str],
            batch_no: int,
            semaphore: asyncio.Semaphore,
        ) -> list[dict]:
            nonlocal first_round_failed
            batch_key = tuple(search_values)
            async with semaphore:
                try:
                    if batch_no == 1 and not first_round_failed:
                        first_round_failed = True
                        raise ListingRateLimitError(
                            {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
                        )
                    await asyncio.sleep(0.05)
                    return [{"asin": asin} for asin in search_values]
                except asyncio.CancelledError:
                    cancelled_batches.append(batch_key)
                    raise

        client._fetch_listing_batch = fake_fetch_listing_batch  # type: ignore[method-assign]

        rows = await client.fetch_listing_items_by_asins("token", {"1448": {f"A{i}" for i in range(12)}})

        self.assertEqual(len(rows), 12)
        self.assertTrue(cancelled_batches)

    async def test_fetch_listing_items_by_asins_retries_rate_limited_batches(self) -> None:
        client = LingxingClient(make_config())
        calls = 0

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
            return {"code": 0, "data": [{"asin": asin} for asin in req_body["search_value"]], "total": len(req_body["search_value"])}

        client.request = fake_request  # type: ignore[method-assign]

        rows = await client.fetch_listing_items_by_asins(
            "token",
            {"1448": {"A1", "A2"}},
        )

        self.assertEqual(sorted(row["asin"] for row in rows), ["A1", "A2"])
        self.assertEqual(calls, 2)

    async def test_fetch_listing_items_by_asins_retries_with_lower_concurrency_after_rate_limit(self) -> None:
        client = LingxingClient(make_config())
        current_in_flight = 0
        max_in_flight = 0
        poisoned_batches: set[tuple[int, tuple[str, ...]]] = set()
        round_no = 0
        first_batch = tuple(sorted({f"A{i}" for i in range(25)})[:10])

        async def fake_request(
            access_token: str,
            route_name: str,
            method: str,
            req_params: dict | None = None,
            req_body: dict | None = None,
            **kwargs: object,
        ) -> dict:
            nonlocal current_in_flight, max_in_flight, poisoned_batches, round_no
            batch_key = tuple(req_body["search_value"])
            if batch_key == first_batch and current_in_flight == 0:
                round_no += 1
            current_in_flight += 1
            max_in_flight = max(max_in_flight, current_in_flight)
            await asyncio.sleep(0.01)
            poison_key = (round_no, batch_key)
            if round_no < 3 and current_in_flight > 1:
                poisoned_batches.add(poison_key)
                current_in_flight -= 1
                return {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
            if poison_key in poisoned_batches:
                current_in_flight -= 1
                return {"code": "3001008", "msg": "new requests too frequently. please request later.", "data": None}
            current_in_flight -= 1
            return {
                "code": 0,
                "data": [{"asin": asin} for asin in req_body["search_value"]],
                "total": len(req_body["search_value"]),
            }

        client.request = fake_request  # type: ignore[method-assign]

        rows = await client.fetch_listing_items_by_asins(
            "token",
            {"1448": {f"A{i}" for i in range(25)}},
        )

        self.assertEqual(len(rows), 25)
        self.assertGreater(max_in_flight, 1)


if __name__ == "__main__":
    unittest.main()
