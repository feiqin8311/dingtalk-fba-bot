from dataclasses import dataclass
from datetime import date
import asyncio
import unittest

from fba_alert.application import (
    AlertJobResult,
    build_inventory_snapshot_candidate_sid_asin_map,
    count_sid_asin_pairs,
    run_alert_job,
)
from fba_alert.lingxing import InventorySnapshot
from tests.factories import make_summary_item


@dataclass
class FakeLingxingClient:
    seller_map: dict[str, str]
    raw_items: list[dict]
    inventory_snapshot_map: dict[tuple[str, str], InventorySnapshot]
    listing_items: list[dict]
    listing_items_fallback: dict[tuple[str, str], dict] | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def fetch_access_token(self) -> str:
        self.calls.append(("fetch_access_token", None))
        return "token"

    async def fetch_seller_map(self, access_token: str) -> dict[str, str]:
        self.calls.append(("fetch_seller_map", access_token))
        return self.seller_map

    async def fetch_summary_items(self, access_token: str, sid_list: list[str] | None = None) -> list[dict]:
        self.calls.append(("fetch_summary_items", tuple(sid_list or [])))
        return self.raw_items

    async def fetch_inventory_snapshot_map(
        self,
        access_token: str,
        sid_asin_map: dict[str, set[str]],
    ) -> dict[tuple[str, str], InventorySnapshot]:
        self.calls.append(("fetch_inventory_snapshot_map", sid_asin_map))
        return self.inventory_snapshot_map

    async def fetch_listing_items_by_asins(
        self,
        access_token: str,
        sid_asin_map: dict[str, set[str]],
    ) -> list[dict]:
        self.calls.append(("fetch_listing_items_by_asins", sid_asin_map))
        return self.listing_items

    async def fetch_listing_item_by_asin(
        self,
        access_token: str,
        sid: str,
        asin: str,
    ) -> list[dict]:
        self.calls.append(("fetch_listing_item_by_asin", (sid, asin)))
        fallback_items = self.listing_items_fallback or {}
        item = fallback_items.get((sid, asin))
        return [item] if item else []


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_user_file(self, user_id: str, report_path: str) -> dict:
        self.sent.append((user_id, report_path))
        return {"ok": True, "user_id": user_id}


class ApplicationTests(unittest.TestCase):
    def test_count_sid_asin_pairs_sums_unique_pairs(self) -> None:
        self.assertEqual(count_sid_asin_pairs({"1448": {"A1", "A2"}, "1444": {"B1"}}), 3)

    def test_build_inventory_snapshot_candidate_sid_asin_map_includes_all_allowed_asins(self) -> None:
        alert_item = make_summary_item(asin="B001", hash_id="hash-alert", sid="1448", fba_days=6)
        low_stock_item = make_summary_item(
            asin="B002",
            hash_id="hash-low-stock",
            sid="1448",
            fba_plus_days=120,
            fba_days=90,
            out_stock_date="2026-08-20",
            amazon_quantity_valid=20,
            amazon_quantity_shipping=4,
            afn_fulfillable_quantity=3,
            reserved_fc_transfers=1,
            reserved_fc_processing=1,
        )
        normal_item = make_summary_item(
            asin="B003",
            hash_id="hash-normal",
            sid="1448",
            fba_plus_days=120,
            fba_days=90,
            out_stock_date="2026-08-20",
            amazon_quantity_valid=20,
            amazon_quantity_shipping=0,
            afn_fulfillable_quantity=10,
            reserved_fc_transfers=5,
            reserved_fc_processing=2,
        )

        prelim_alerts = asyncio.run(
            _build_prelim_alerts_for_test([alert_item, low_stock_item, normal_item])
        )

        sid_asin_map = build_inventory_snapshot_candidate_sid_asin_map(
            [alert_item, low_stock_item, normal_item],
            prelim_alerts,
            {"1448"},
            {"1448": "店铺A"},
        )

        self.assertEqual(sid_asin_map, {"1448": {"B001", "B002", "B003"}})

    def test_build_inventory_snapshot_candidate_sid_asin_map_keeps_allowed_jp_jp_asins(self) -> None:
        a_level_item = make_summary_item(
            asin="J001",
            hash_id="hash-jp-a",
            sid="1457",
            fba_plus_days=100,
            fba_days=10,
            out_stock_date="2026-08-20",
            amazon_quantity_valid=30,
            amazon_quantity_shipping=0,
            afn_fulfillable_quantity=20,
            reserved_fc_transfers=5,
            reserved_fc_processing=5,
        )
        c_level_candidate_item = make_summary_item(
            asin="J002",
            hash_id="hash-jp-c",
            sid="1457",
            fba_plus_days=100,
            fba_days=90,
            out_stock_date="2026-08-20",
            amazon_quantity_valid=1,
            amazon_quantity_shipping=4,
            afn_fulfillable_quantity=0,
            reserved_fc_transfers=0,
            reserved_fc_processing=1,
        )

        prelim_alerts = asyncio.run(
            _build_prelim_alerts_for_test(
                [a_level_item, c_level_candidate_item],
                {"1457": "Libraton JP-JP"},
                ["1457"],
            )
        )

        sid_asin_map = build_inventory_snapshot_candidate_sid_asin_map(
            [a_level_item, c_level_candidate_item],
            prelim_alerts,
            {"1457"},
            {"1457": "Libraton JP-JP"},
        )

        self.assertEqual(sid_asin_map, {"1457": {"J001", "J002"}})

    def test_run_alert_job_returns_summary_without_alerts(self) -> None:
        client = FakeLingxingClient(
            seller_map={"1448": "店铺A"},
            raw_items=[],
            inventory_snapshot_map={},
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1448"],
                dry_run=True,
            )
        )

        self.assertEqual(
            result,
            AlertJobResult(
                fetched_count=0,
                alert_count=0,
                report_path="",
                sid_distribution={},
            ),
        )

    def test_run_alert_job_builds_report_and_sends_file(self) -> None:
        item = make_summary_item()
        client = FakeLingxingClient(
            seller_map={"1448": "店铺A"},
            raw_items=[item],
            inventory_snapshot_map={("1448", "B001"): InventorySnapshot(9, 2, 1, 12, 12)},
            listing_items=[
                {
                    "sid": "1448",
                    "asin": "B001",
                    "principal_info": [{"principal_name": "张三"}],
                }
            ],
        )
        notifier = FakeNotifier()
        exported: list[tuple[list[object], date]] = []

        def export_report(alerts: list[object], today: date) -> str:
            exported.append((alerts, today))
            return "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1448"],
                exporter=export_report,
                notifier=notifier,
                notify_user_ids=["u1", "u2"],
            )
        )

        self.assertEqual(result.report_path, "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx")
        self.assertEqual(result.fetched_count, 1)
        self.assertEqual(result.alert_count, 1)
        self.assertEqual(result.sid_distribution, {"1448": 1})
        self.assertEqual(
            notifier.sent,
            [
                ("16063564311489688", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("17331048354297047", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("u1", "reports/2026-04-07/店铺A/LIBRATON库存预警-店铺A-20260407.xlsx"),
                ("u2", "reports/2026-04-07/店铺A/LIBRATON库存预警-店铺A-20260407.xlsx"),
            ],
        )
        self.assertEqual(exported[0][1], date(2026, 4, 7))
        self.assertEqual(exported[0][0][0].listing_contacts, "张三")

    def test_run_alert_job_sends_store_report_to_store_specific_recipients(self) -> None:
        item = make_summary_item(
            asin="B1444",
            hash_id="hash-1444",
            sid="1444",
            msku="MSKU-1444",
            fba_plus_days=55,
            fba_days=20,
            out_stock_date="2026-05-22",
            amazon_quantity_valid=10,
            amazon_quantity_shipping=5,
            afn_fulfillable_quantity=8,
            reserved_fc_transfers=1,
            reserved_fc_processing=1,
        )
        client = FakeLingxingClient(
            seller_map={"1444": "Libraton NA-CA"},
            raw_items=[item],
            inventory_snapshot_map={("1444", "B1444"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )
        notifier = FakeNotifier()

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1448"],
                exporter=lambda alerts, today: "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx",
                notifier=notifier,
                notify_user_ids=["fallback-user"],
            )
        )

        self.assertEqual(result.alert_count, 1)
        self.assertEqual(
            notifier.sent,
            [
                ("16063564311489688", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("17331048354297047", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("01364646263121664148", "reports/2026-04-07/Libraton NA-CA/LIBRATON库存预警-NA-CA-20260407.xlsx"),
            ],
        )

    def test_run_alert_job_sends_store_report_to_fallback_recipients(self) -> None:
        item = make_summary_item()
        client = FakeLingxingClient(
            seller_map={"1448": "店铺A"},
            raw_items=[item],
            inventory_snapshot_map={("1448", "B001"): InventorySnapshot(9, 2, 1, 12, 12)},
            listing_items=[],
        )
        notifier = FakeNotifier()

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1448"],
                exporter=lambda alerts, today: "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx",
                notifier=notifier,
                notify_user_ids=["fallback-1", "fallback-2"],
            )
        )

        self.assertEqual(
            notifier.sent,
            [
                ("16063564311489688", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("17331048354297047", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("fallback-1", "reports/2026-04-07/店铺A/LIBRATON库存预警-店铺A-20260407.xlsx"),
                ("fallback-2", "reports/2026-04-07/店铺A/LIBRATON库存预警-店铺A-20260407.xlsx"),
            ],
        )

    def test_run_alert_job_sends_combined_eu_store_report(self) -> None:
        uk_item = make_summary_item(
            asin="B-UK",
            hash_id="hash-uk",
            sid="1446",
            msku="MSKU-UK",
            fba_days=10,
        )
        de_item = make_summary_item(
            asin="B-DE",
            hash_id="hash-de",
            sid="1448",
            msku="MSKU-DE",
            fba_days=10,
        )
        client = FakeLingxingClient(
            seller_map={"1446": "Libraton EU-UK", "1448": "Libraton EU-DE"},
            raw_items=[uk_item, de_item],
            inventory_snapshot_map={},
            listing_items=[],
        )
        notifier = FakeNotifier()

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1446", "1448"],
                exporter=lambda alerts, today: "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx",
                notifier=notifier,
                notify_user_ids=["ukde-1", "ukde-2"],
            )
        )

        self.assertEqual(
            notifier.sent,
            [
                ("16063564311489688", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("17331048354297047", "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"),
                ("17496925056054051", "reports/2026-04-07/Libraton EU/LIBRATON库存预警-EU-20260407.xlsx"),
                ("17621342403159969", "reports/2026-04-07/Libraton EU/LIBRATON库存预警-EU-20260407.xlsx"),
                ("17490880140202841", "reports/2026-04-07/Libraton EU/LIBRATON库存预警-EU-20260407.xlsx"),
            ],
        )

    def test_run_alert_job_fetches_summary_with_resolved_sid_list(self) -> None:
        item = make_summary_item(
            asin="B1444",
            hash_id="hash-1444",
            sid="1444",
            msku="MSKU-1444",
            fba_plus_days=45,
            fba_days=20,
            out_stock_date="2026-05-02",
            amazon_quantity_valid=10,
            amazon_quantity_shipping=5,
            afn_fulfillable_quantity=8,
            reserved_fc_transfers=1,
            reserved_fc_processing=1,
        )
        client = FakeLingxingClient(
            seller_map={"1448": "Libraton EU-DE", "1443": "Libraton NA-US", "1444": "Libraton NA-CA"},
            raw_items=[item],
            inventory_snapshot_map={("1444", "B1444"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1448"],
                dry_run=True,
            )
        )

        self.assertEqual(result.alert_count, 1)
        self.assertEqual(result.sid_distribution, {"1444": 1})
        self.assertIn(("fetch_summary_items", ("1448", "1443", "1444")), client.calls)

    def test_run_alert_job_with_us_scope_queries_only_na_us(self) -> None:
        item = make_summary_item(
            asin="B-US",
            hash_id="hash-us",
            sid="1443",
            msku="MSKU-US",
            fba_plus_days=45,
            fba_days=20,
            out_stock_date="2026-05-02",
        )
        client = FakeLingxingClient(
            seller_map={"1443": "Libraton NA-US", "1444": "Libraton NA-CA", "1448": "Libraton EU-DE"},
            raw_items=[item],
            inventory_snapshot_map={("1443", "B-US"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                scope="us",
                dry_run=True,
            )
        )

        self.assertEqual(result.alert_count, 1)
        self.assertEqual(result.sid_distribution, {"1443": 1})
        self.assertIn(("fetch_summary_items", ("1443",)), client.calls)

    def test_run_alert_job_with_us_scope_does_not_send_main_report(self) -> None:
        item = make_summary_item(
            asin="B-US",
            hash_id="hash-us-send",
            sid="1443",
            msku="MSKU-US",
            fba_plus_days=45,
            fba_days=20,
            out_stock_date="2026-05-02",
        )
        client = FakeLingxingClient(
            seller_map={"1443": "Libraton NA-US"},
            raw_items=[item],
            inventory_snapshot_map={("1443", "B-US"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )
        notifier = FakeNotifier()

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                exporter=lambda alerts, today: "reports/2026-04-21/LIBRATON库存预警-20260421.xlsx",
                notifier=notifier,
                notify_user_ids=["fallback-user"],
                scope="us",
            )
        )

        self.assertEqual(result.report_path, "reports/2026-04-21/Libraton NA-US/LIBRATON库存预警-NA-US-20260421.xlsx")
        self.assertEqual(
            notifier.sent,
            [
                ("17489140420206931", "reports/2026-04-21/Libraton NA-US/LIBRATON库存预警-NA-US-20260421.xlsx"),
                ("17490879808802516", "reports/2026-04-21/Libraton NA-US/LIBRATON库存预警-NA-US-20260421.xlsx"),
            ],
        )

    def test_run_alert_job_with_eu_scope_returns_combined_eu_report(self) -> None:
        uk_item = make_summary_item(
            asin="B-UK",
            hash_id="hash-eu-uk",
            sid="1446",
            msku="MSKU-UK",
            fba_days=10,
        )
        de_item = make_summary_item(
            asin="B-DE",
            hash_id="hash-eu-de",
            sid="1448",
            msku="MSKU-DE",
            fba_days=10,
        )
        client = FakeLingxingClient(
            seller_map={"1446": "Libraton EU-UK", "1448": "Libraton EU-DE", "1443": "Libraton NA-US"},
            raw_items=[uk_item, de_item],
            inventory_snapshot_map={},
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                scope="eu",
                dry_run=True,
            )
        )

        self.assertEqual(result.report_path, "reports/2026-04-21/Libraton EU/LIBRATON库存预警-EU-20260421.xlsx")
        self.assertIn(("fetch_summary_items", ("1446", "1448")), client.calls)

    def test_run_alert_job_fetches_inventory_snapshot_for_all_allowed_asins(self) -> None:
        alert_item = make_summary_item(asin="B001", hash_id="hash-alert", sid="1448", fba_days=6)
        c_level_candidate_item = make_summary_item(
            asin="B002",
            hash_id="hash-c-level",
            sid="1448",
            fba_plus_days=120,
            fba_days=90,
            out_stock_date="2026-08-20",
            amazon_quantity_valid=1,
            amazon_quantity_shipping=4,
            afn_fulfillable_quantity=0,
            reserved_fc_transfers=0,
            reserved_fc_processing=1,
        )
        normal_item = make_summary_item(
            asin="B003",
            hash_id="hash-normal",
            sid="1448",
            fba_plus_days=120,
            fba_days=90,
            out_stock_date="2026-08-20",
            amazon_quantity_valid=20,
            amazon_quantity_shipping=0,
            afn_fulfillable_quantity=10,
            reserved_fc_transfers=5,
            reserved_fc_processing=2,
        )
        client = FakeLingxingClient(
            seller_map={"1448": "店铺A"},
            raw_items=[alert_item, c_level_candidate_item, normal_item],
            inventory_snapshot_map={("1448", "B002"): InventorySnapshot(0, 0, 0, 0, 4)},
            listing_items=[],
        )

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1448"],
                dry_run=True,
            )
        )

        self.assertIn(("fetch_inventory_snapshot_map", {"1448": {"B001", "B002", "B003"}}), client.calls)

    def test_run_alert_job_uses_inventory_snapshot_when_summary_inventory_fields_are_missing(self) -> None:
        item = make_summary_item(
            asin="B0F2HTCZTD",
            hash_id="hash-jp-missing-summary-inventory",
            sid="1457",
            msku="911115",
            fba_plus_days=120,
            fba_days=1,
            out_stock_date="2026-04-22",
            amazon_quantity_valid=0,
            amazon_quantity_shipping=0,
            afn_fulfillable_quantity=0,
            reserved_fc_transfers=0,
            reserved_fc_processing=0,
        )
        item["data"]["amazon_quantity_info"] = {
            "amazon_quantity_valid": None,
            "amazon_quantity_shipping": None,
            "afn_fulfillable_quantity": None,
            "reserved_fc_transfers": None,
            "reserved_fc_processing": None,
        }
        client = FakeLingxingClient(
            seller_map={"1457": "Libraton JP-JP"},
            raw_items=[item],
            inventory_snapshot_map={("1457", "B0F2HTCZTD"): InventorySnapshot(4, 0, 0, 4, 256)},
            listing_items=[],
        )
        exported: list[tuple[list[object], date]] = []

        def export_report(alerts: list[object], today: date) -> str:
            exported.append((alerts, today))
            return "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1457"],
                exporter=export_report,
                dry_run=True,
            )
        )

        self.assertEqual(result.alert_count, 1)
        self.assertEqual(exported[0][0][0].fba_inbound_inventory, 256)
        self.assertEqual(exported[0][0][0].fba_inventory, 4)
        self.assertIn(("fetch_inventory_snapshot_map", {"1457": {"B0F2HTCZTD"}}), client.calls)

    def test_run_alert_job_inventory_fields_always_use_source_list_snapshot(self) -> None:
        item = make_summary_item(
            asin="B001",
            hash_id="hash-source-list-wins",
            sid="1448",
            msku="MSKU-1",
            fba_plus_days=50,
            fba_days=6,
            out_stock_date="2026-04-20",
            amazon_quantity_valid=99,
            amazon_quantity_shipping=88,
            afn_fulfillable_quantity=77,
            reserved_fc_transfers=11,
            reserved_fc_processing=10,
        )
        client = FakeLingxingClient(
            seller_map={"1448": "店铺A"},
            raw_items=[item],
            inventory_snapshot_map={("1448", "B001"): InventorySnapshot(9, 2, 1, 12, 12)},
            listing_items=[],
        )
        exported: list[tuple[list[object], date]] = []

        def export_report(alerts: list[object], today: date) -> str:
            exported.append((alerts, today))
            return "reports/2026-04-07/LIBRATON库存预警-20260407.xlsx"

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["1448"],
                exporter=export_report,
                dry_run=True,
            )
        )

        record = exported[0][0][0]
        self.assertEqual(record.fba_inventory, 12)
        self.assertEqual(record.fba_inbound_inventory, 12)
        self.assertEqual(record.fba_sellable_inventory, 9)
        self.assertEqual(record.fba_transfer_reserved_inventory, 2)
        self.assertEqual(record.fba_processing_inventory, 1)

    def test_run_alert_job_refetches_missing_listing_contacts_individually(self) -> None:
        item = make_summary_item(
            asin="B0912KPQM6",
            hash_id="hash-na-us-contact-fallback",
            sid="1443",
            msku="900910BR",
            fba_plus_days=139,
            fba_days=2,
            out_stock_date="2026-04-23",
        )
        client = FakeLingxingClient(
            seller_map={"1443": "Libraton NA-US"},
            raw_items=[item],
            inventory_snapshot_map={("1443", "B0912KPQM6"): InventorySnapshot(0, 0, 2, 2, 100)},
            listing_items=[
                {
                    "sid": "1443",
                    "asin": "B0912KPQM6",
                    "principal_info": [],
                }
            ],
            listing_items_fallback={
                ("1443", "B0912KPQM6"): {
                    "sid": "1443",
                    "asin": "B0912KPQM6",
                    "principal_info": [{"principal_name": "许蓓湘"}],
                }
            },
        )
        exported: list[tuple[list[object], date]] = []

        def export_report(alerts: list[object], today: date) -> str:
            exported.append((alerts, today))
            return "reports/2026-04-21/LIBRATON库存预警-20260421.xlsx"

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1443"],
                exporter=export_report,
                dry_run=True,
            )
        )

        self.assertEqual(exported[0][0][0].listing_contacts, "许蓓湘")
        self.assertIn(("fetch_listing_item_by_asin", ("1443", "B0912KPQM6")), client.calls)


async def _build_prelim_alerts_for_test(
    items: list[dict],
    seller_map: dict[str, str] | None = None,
    sid_list: list[str] | None = None,
) -> list[object]:
    from fba_alert.alerts import parse_summary_items

    return parse_summary_items(
        items,
        date(2026, 4, 7),
        seller_map or {"1448": "店铺A"},
        sid_list or ["1448"],
    )


if __name__ == "__main__":
    unittest.main()
