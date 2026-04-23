import asyncio
import tempfile
import unittest

from fba_alert.config import LingxingConfig
from fba_alert.lingxing import InventorySnapshot, LingxingClient


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


if __name__ == "__main__":
    unittest.main()
