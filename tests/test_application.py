from dataclasses import dataclass
from datetime import date
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fba_alert.application import (
    AlertJobResult,
    build_inventory_snapshot_candidate_sid_asin_map,
    build_dingpan_folder_route,
    count_sid_asin_pairs,
    ensure_dingpan_folder_route,
    notify_report,
    notify_store_reports,
    resolve_dingpan_route_parent_id,
    run_alert_job,
    upload_reports_to_dingpan,
)
from fba_alert.config import DingTalkConfig
from fba_alert.lingxing import InventorySnapshot
from fba_alert.models import AlertRecord
from fba_alert.report import build_report_rows
from fba_alert.scopes import AlertScope
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

    async def fetch_summary_items(
        self,
        access_token: str,
        sid_list: list[str] | None = None,
        data_type: int | None = None,
    ) -> list[dict]:
        self.calls.append(("fetch_summary_items", (tuple(sid_list or []), data_type)))
        if not sid_list:
            return self.raw_items
        allowed_sids = set(sid_list)
        return [
            item
            for item in self.raw_items
            if str((item.get("basic_info") or {}).get("sid") or "").strip() in allowed_sids
        ]

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
        self.texts: list[tuple[str, str]] = []

    def get_access_token(self) -> str:
        return "token"

    def send_user_text(self, user_id: str, text: str) -> dict:
        self.texts.append((user_id, text))
        return {"ok": True, "user_id": user_id}


class FakeDingpanFolderClient:
    def __init__(self, existing: dict[str, dict] | None = None) -> None:
        self.existing = existing or {}
        self.calls: list[tuple[str, str]] = []

    def list_dentries(self, *, parent_id: str) -> list[dict]:
        self.calls.append(("list", parent_id))
        return [entry for entry in self.existing.values() if entry.get("parentId") == parent_id]

    def create_folder(self, *, parent_id: str, name: str) -> dict:
        self.calls.append(("create", f"{parent_id}:{name}"))
        folder_id = f"new-{parent_id}-{name}"
        entry = {"id": folder_id, "name": name, "type": "FOLDER", "parentId": parent_id}
        self.existing[folder_id] = entry
        return {"dentry": entry}


class ApplicationTests(unittest.TestCase):
    def test_resolve_dingpan_route_parent_id_uses_yplus_fixed_folder_id(self) -> None:
        parent_id = resolve_dingpan_route_parent_id(
            "YPLUS库存预警测试-20260622.xlsx",
            "",
            "225801923282",
        )

        self.assertEqual(parent_id, "225835002566")

    def test_resolve_dingpan_route_parent_id_uses_libraton_fixed_folder_id(self) -> None:
        parent_id = resolve_dingpan_route_parent_id(
            "LIBRATON库存预警-20260622.xlsx",
            "",
            "225801923282",
        )

        self.assertEqual(parent_id, "225843426167")

    def test_resolve_dingpan_route_parent_id_uses_ezarc_fixed_folder_id(self) -> None:
        parent_id = resolve_dingpan_route_parent_id(
            "EZARC库存预警测试-20260622.xlsx",
            "",
            "225801923282",
        )

        self.assertEqual(parent_id, "225835089358")

    def test_ensure_dingpan_folder_route_uses_cache_when_available(self) -> None:
        from fba_alert import application
        from fba_alert import dingpan

        with TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "dingpan-folders.json"
            cache_path.write_text(
                '{"28859011990:root:YPLUS/\u6c47\u603b/2026-06-22":"cached-folder"}',
                encoding="utf-8",
            )

            original_cache_path = application.DINGPAN_FOLDER_CACHE_PATH
            original_ensure_child_folder = dingpan.ensure_child_folder
            try:
                application.DINGPAN_FOLDER_CACHE_PATH = cache_path

                def fail_if_called(*args, **kwargs):
                    raise AssertionError("ensure_child_folder should not be called on cache hit")

                dingpan.ensure_child_folder = fail_if_called  # type: ignore[assignment]

                folder_id = ensure_dingpan_folder_route(
                    "token",
                    space_id="28859011990",
                    union_id="union",
                    parent_id="root",
                    folder_names=["YPLUS", "汇总", "2026-06-22"],
                )
            finally:
                application.DINGPAN_FOLDER_CACHE_PATH = original_cache_path
                dingpan.ensure_child_folder = original_ensure_child_folder  # type: ignore[assignment]

        self.assertEqual(folder_id, "cached-folder")

    def test_ensure_dingpan_folder_route_skips_lookup_when_requested(self) -> None:
        from fba_alert import application
        from fba_alert import dingpan

        with TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "dingpan-folders.json"

            original_cache_path = application.DINGPAN_FOLDER_CACHE_PATH
            original_ensure_child_folder = dingpan.ensure_child_folder
            original_create_folder = dingpan.create_folder
            try:
                application.DINGPAN_FOLDER_CACHE_PATH = cache_path

                def fail_if_called(*args, **kwargs):
                    raise AssertionError("ensure_child_folder should not be called when skip_lookup=True")

                def create_folder(*args, **kwargs):
                    return {"dentry": {"id": "created-date-folder", "name": kwargs["name"]}}

                dingpan.ensure_child_folder = fail_if_called  # type: ignore[assignment]
                dingpan.create_folder = create_folder  # type: ignore[assignment]

                folder_id = ensure_dingpan_folder_route(
                    "token",
                    space_id="28859011990",
                    union_id="union",
                    parent_id="225835002566",
                    folder_names=["2026-06-22"],
                    skip_lookup=True,
                )
            finally:
                application.DINGPAN_FOLDER_CACHE_PATH = original_cache_path
                dingpan.ensure_child_folder = original_ensure_child_folder  # type: ignore[assignment]
                dingpan.create_folder = original_create_folder  # type: ignore[assignment]

        self.assertEqual(folder_id, "created-date-folder")

    def test_ensure_child_folder_reuses_existing_folder(self) -> None:
        from fba_alert import dingpan

        client = FakeDingpanFolderClient(
            existing={
                "folder-1": {"id": "folder-1", "name": "汇总", "type": "FOLDER", "parentId": "parent-1"}
            }
        )

        original_list_dentries = dingpan.list_dentries
        original_create_folder = dingpan.create_folder
        try:
            dingpan.list_dentries = lambda *args, **kwargs: client.list_dentries(parent_id=kwargs["parent_id"])  # type: ignore[assignment]
            dingpan.create_folder = lambda *args, **kwargs: client.create_folder(parent_id=kwargs["parent_id"], name=kwargs["name"])  # type: ignore[assignment]

            folder = dingpan.ensure_child_folder(
                "token",
                space_id="space",
                union_id="union",
                parent_id="parent-1",
                folder_name="汇总",
            )
        finally:
            dingpan.list_dentries = original_list_dentries  # type: ignore[assignment]
            dingpan.create_folder = original_create_folder  # type: ignore[assignment]

        self.assertEqual(folder["id"], "folder-1")
        self.assertEqual(client.calls[0], ("list", "parent-1"))
        self.assertNotIn(("create", "parent-1:汇总"), client.calls)

    def test_build_dingpan_folder_route_routes_brands_and_regions(self) -> None:
        self.assertEqual(
            build_dingpan_folder_route("EZARC库存预警测试-20260622.xlsx", "EZARC JP-JP"),
            ["日本"],
        )
        self.assertEqual(
            build_dingpan_folder_route("YPLUS库存预警测试-20260622.xlsx", ""),
            ["汇总"],
        )
        self.assertEqual(
            build_dingpan_folder_route("LIBRATON库存预警-20260622.xlsx", "Libraton NA-US"),
            ["北美"],
        )
        self.assertEqual(
            build_dingpan_folder_route("LIBRATON库存预警-20260622.xlsx", "Libraton EU"),
            ["欧洲"],
        )

    def test_upload_reports_to_dingpan_retries_after_stale_cached_folder_id(self) -> None:
        from fba_alert import application
        from fba_alert import dingpan

        notifier = FakeNotifier()
        config = DingTalkConfig(
            api_base_url="https://api.dingtalk.com",
            app_key="app-key",
            app_secret="app-secret",
            robot_code="robot-code",
            user_ids=[],
            dingpan_enabled=True,
            dingpan_space_id="28859011990",
            dingpan_parent_folder_id="221392062127",
            dingpan_user_id="user-id",
            dingpan_union_id="union-id",
        )

        with TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "LIBRATON库存预警-20260626.xlsx"
            report_path.write_text("test", encoding="utf-8")
            cache_path = Path(tmp_dir) / "dingpan-folders.json"
            cache_path.write_text(
                '{"28859011990:225843426167:2026-06-26":"stale-folder"}',
                encoding="utf-8",
            )

            ensure_calls: list[str] = []
            upload_calls: list[str] = []
            original_cache_path = application.DINGPAN_FOLDER_CACHE_PATH
            original_ensure_route = application.ensure_dingpan_folder_route
            original_upload_file = dingpan.upload_file
            original_extract_file_id = dingpan.extract_file_id
            original_build_preview_url = dingpan.build_preview_url
            try:
                application.DINGPAN_FOLDER_CACHE_PATH = cache_path

                def ensure_route(*args, **kwargs):
                    folder_id = "stale-folder" if not ensure_calls else "fresh-folder"
                    ensure_calls.append(folder_id)
                    return folder_id

                def upload_file(*args, **kwargs):
                    parent_id = kwargs["parent_id"]
                    upload_calls.append(parent_id)
                    if parent_id == "stale-folder":
                        raise RuntimeError(
                            "files/commit: HTTP 400: {'code': 'paramError', 'message': 'parentDentry not exist'}"
                        )
                    return {"commit": {"dentry": {"id": "file-1"}}}

                application.ensure_dingpan_folder_route = ensure_route  # type: ignore[assignment]
                dingpan.upload_file = upload_file  # type: ignore[assignment]
                dingpan.extract_file_id = lambda commit: "file-1"  # type: ignore[assignment]
                dingpan.build_preview_url = lambda space_id, file_id: f"preview:{space_id}:{file_id}"  # type: ignore[assignment]

                preview_url_map = upload_reports_to_dingpan(
                    notifier,
                    config,
                    str(report_path),
                    [],
                    date(2026, 6, 26),
                    AlertScope.ALL,
                )
            finally:
                application.DINGPAN_FOLDER_CACHE_PATH = original_cache_path
                application.ensure_dingpan_folder_route = original_ensure_route  # type: ignore[assignment]
                dingpan.upload_file = original_upload_file  # type: ignore[assignment]
                dingpan.extract_file_id = original_extract_file_id  # type: ignore[assignment]
                dingpan.build_preview_url = original_build_preview_url  # type: ignore[assignment]

        self.assertEqual(ensure_calls, ["stale-folder", "fresh-folder"])
        self.assertEqual(upload_calls, ["stale-folder", "fresh-folder"])
        self.assertEqual(preview_url_map[str(report_path)], "preview:28859011990:file-1")

    def test_upload_reports_to_dingpan_includes_brand_store_reports(self) -> None:
        from fba_alert import application
        from fba_alert import dingpan

        notifier = FakeNotifier()
        config = DingTalkConfig(
            api_base_url="https://api.dingtalk.com",
            app_key="app-key",
            app_secret="app-secret",
            robot_code="robot-code",
            user_ids=[],
            dingpan_enabled=True,
            dingpan_space_id="28859011990",
            dingpan_parent_folder_id="221392062127",
            dingpan_user_id="user-id",
            dingpan_union_id="union-id",
        )
        alert = AlertRecord(
            level="A",
            reasons=["可售天数(FBA)=20天"],
            asin="B-EZARC",
            sid="1422",
            seller_name="EZARC NA-US",
            node_type=1,
            mskus=["EZ-US"],
            listing_contacts="",
            fba_plus_days=60,
            fba_days=20,
            fba_inventory=8,
            fba_inbound_inventory=1,
            fba_sellable_inventory=1,
            fba_transfer_reserved_inventory=10,
            fba_processing_inventory=5,
            summary_daily_sales=1.0,
            out_stock_date="2026-05-12",
            out_stock_days=20,
            restock_status=0,
            hash_id="hash-ezarc",
        )

        with TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "2026-04-21"
            report_dir.mkdir(parents=True)
            main_report_path = report_dir / "EZARC库存预警-20260421.xlsx"
            store_report_path = report_dir / "EZARC NA-US" / "EZARC库存预警-EZARC NA-US-20260421.xlsx"
            main_report_path.write_text("main", encoding="utf-8")
            store_report_path.parent.mkdir()
            store_report_path.write_text("store", encoding="utf-8")

            upload_calls: list[str] = []
            original_ensure_route = application.ensure_dingpan_folder_route
            original_upload_file = dingpan.upload_file
            original_extract_file_id = dingpan.extract_file_id
            original_build_preview_url = dingpan.build_preview_url
            try:
                application.ensure_dingpan_folder_route = lambda *args, **kwargs: "folder-id"  # type: ignore[assignment]

                def upload_file(*args, **kwargs):
                    upload_calls.append(Path(kwargs["file_path"]).name)
                    return {"commit": {"dentry": {"id": f"file-{len(upload_calls)}"}}}

                dingpan.upload_file = upload_file  # type: ignore[assignment]
                dingpan.extract_file_id = lambda commit: str((commit["dentry"])["id"])  # type: ignore[assignment]
                dingpan.build_preview_url = lambda space_id, file_id: f"preview:{file_id}"  # type: ignore[assignment]

                preview_url_map = upload_reports_to_dingpan(
                    notifier,
                    config,
                    str(main_report_path),
                    [alert],
                    date(2026, 4, 21),
                    AlertScope.EZARC,
                )
            finally:
                application.ensure_dingpan_folder_route = original_ensure_route  # type: ignore[assignment]
                dingpan.upload_file = original_upload_file  # type: ignore[assignment]
                dingpan.extract_file_id = original_extract_file_id  # type: ignore[assignment]
                dingpan.build_preview_url = original_build_preview_url  # type: ignore[assignment]

        self.assertEqual(
            upload_calls,
            ["EZARC库存预警-20260421.xlsx", "EZARC库存预警-EZARC NA-US-20260421.xlsx"],
        )
        self.assertEqual(preview_url_map[str(store_report_path)], "preview:file-2")

    def test_notify_store_reports_uses_brand_title_for_preview_links(self) -> None:
        cases = [
            ("EZARC库存预警", "EZARC NA-US", "1422", "B-EZARC", "EZARC 库存预警 - EZARC NA-US"),
            ("YPLUS库存预警", "YPLUS-US-US", "2344", "B-YPLUS", "YPLUS 库存预警 - YPLUS-US-US"),
        ]
        for report_name, seller_name, sid, asin, title in cases:
            with self.subTest(seller_name=seller_name):
                alert = AlertRecord(
                    level="A",
                    reasons=["rule"],
                    asin=asin,
                    sid=sid,
                    seller_name=seller_name,
                    node_type=1,
                    mskus=["MSKU"],
                    listing_contacts="",
                    fba_plus_days=0,
                    fba_days=10,
                    fba_inventory=1,
                    fba_inbound_inventory=0,
                    fba_sellable_inventory=1,
                    fba_transfer_reserved_inventory=0,
                    fba_processing_inventory=0,
                    summary_daily_sales=1.0,
                    out_stock_date="2026-05-12",
                    out_stock_days=20,
                    restock_status=0,
                    hash_id=asin,
                )
                main_report = f"reports/2026-04-21/{report_name}-20260421.xlsx"
                store_report = f"reports/2026-04-21/{seller_name}/{report_name}-{seller_name}-20260421.xlsx"
                notifier = FakeNotifier()

                notify_store_reports(
                    main_report,
                    [alert],
                    date(2026, 4, 21),
                notifier,
                dry_run=False,
                    preview_url_map={store_report: "https://example.invalid/preview"},
                )

                self.assertIn(f"【{title}】", notifier.texts[0][1])

    def test_notify_report_skips_without_dingpan_preview_url(self) -> None:
        notifier = FakeNotifier()

        notify_report("reports/report.xlsx", notifier, ["user-1"], dry_run=False)

        self.assertEqual(notifier.texts, [])

    def test_count_sid_asin_pairs_sums_unique_pairs(self) -> None:
        self.assertEqual(count_sid_asin_pairs({"1448": {"A1", "A2"}, "1444": {"B1"}}), 3)

    def test_build_inventory_snapshot_candidate_sid_asin_map_includes_scope_asins(self) -> None:
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
        self.assertEqual(notifier.texts, [])
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
        self.assertEqual(notifier.texts, [])

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

        self.assertEqual(notifier.texts, [])

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

        self.assertEqual(notifier.texts, [])

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
        self.assertIn(("fetch_summary_items", (("1448", "1443", "1444"), 1)), client.calls)

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
        self.assertIn(("fetch_summary_items", (("1443",), 1)), client.calls)

    def test_run_alert_job_with_ezarc_test_scope_queries_only_ezarc_sellers(self) -> None:
        item = make_summary_item(
            asin="B-EZARC-US",
            hash_id="hash-ezarc-us",
            sid="2001",
            msku="EZ-US",
            fba_plus_days=60,
            fba_days=20,
            out_stock_date="2026-05-12",
        )
        client = FakeLingxingClient(
            seller_map={
                "2001": "EZARC NA-US",
                "2002": "EZARC JP-JP",
                "2003": "CBT-F Tools-JP",
                "9001": "Other Store",
            },
            raw_items=[item],
            inventory_snapshot_map={("2001", "B-EZARC-US"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                scope="ezarc-test",
                dry_run=True,
            )
        )

        self.assertEqual(result.sid_distribution, {"2001": 1})
        self.assertIn(("fetch_summary_items", (("2001", "2002", "2003"), None)), client.calls)

    def test_run_alert_job_with_yplus_test_scope_queries_only_yplus_sellers(self) -> None:
        item = make_summary_item(
            asin="B-YPLUS-US",
            hash_id="hash-yplus-us",
            sid="2344",
            msku="YP-US",
            fba_plus_days=45,
            fba_days=14,
            out_stock_date="2026-05-12",
        )
        client = FakeLingxingClient(
            seller_map={
                "2344": "YPLUS-US-US",
                "2345": "YPLUS-US-CA",
                "2351": "YPLUS-JP-JP",
                "6047": "TrailFun-US",
            },
            raw_items=[item],
            inventory_snapshot_map={("2344", "B-YPLUS-US"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                scope="yplus-test",
                dry_run=True,
            )
        )

        self.assertEqual(result.sid_distribution, {"2344": 1})
        self.assertIn(("fetch_summary_items", (("2344", "2345", "2351", "6047"), None)), client.calls)

    def test_run_alert_job_with_yplus_test_scope_keeps_restock_paused_items(self) -> None:
        required_item = make_summary_item(
            asin="B-YPLUS-JP-REQUIRED",
            hash_id="hash-yplus-jp-required",
            sid="2351",
            msku="YP-JP-1",
            fba_plus_days=45,
            fba_days=14,
            out_stock_date="2026-05-12",
        )
        required_us_item = make_summary_item(
            asin="B-YPLUS-US-REQUIRED",
            hash_id="hash-yplus-us-required",
            sid="2344",
            msku="YP-US-1",
            fba_plus_days=45,
            fba_days=14,
            out_stock_date="2026-05-12",
        )
        skipped_item = make_summary_item(
            asin="B-YPLUS-SKIPPED",
            hash_id="hash-yplus-skipped",
            sid="2351",
            msku="YP-JP-2",
            fba_plus_days=10,
            fba_days=2,
            out_stock_date="2026-04-23",
        )
        skipped_item["ext_info"]["restock_status"] = 1
        skipped_us_item = make_summary_item(
            asin="B-YPLUS-US-SKIPPED",
            hash_id="hash-yplus-us-skipped",
            sid="2344",
            msku="YP-US-2",
            fba_plus_days=10,
            fba_days=2,
            out_stock_date="2026-04-23",
        )
        skipped_us_item["ext_info"]["restock_status"] = 1
        client = FakeLingxingClient(
            seller_map={"2344": "YPLUS-US-US", "2351": "YPLUS-JP-JP"},
            raw_items=[required_item, required_us_item, skipped_item, skipped_us_item],
            inventory_snapshot_map={
                ("2351", "B-YPLUS-JP-REQUIRED"): InventorySnapshot(8, 1, 1, 10, 5),
                ("2344", "B-YPLUS-US-REQUIRED"): InventorySnapshot(8, 1, 1, 10, 5),
            },
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                scope="yplus-test",
                dry_run=True,
            )
        )

        self.assertEqual(result.sid_distribution, {"2351": 2, "2344": 2})
        self.assertEqual(result.alert_count, 4)
        self.assertIn(
            (
                "fetch_inventory_snapshot_map",
                {
                    "2351": {"B-YPLUS-JP-REQUIRED", "B-YPLUS-SKIPPED"},
                    "2344": {"B-YPLUS-US-REQUIRED", "B-YPLUS-US-SKIPPED"},
                },
            ),
            client.calls,
        )

    def test_run_alert_job_with_ezarc_test_scope_sends_to_store_policy_users(self) -> None:
        item = make_summary_item(
            asin="B-EZARC-US-SEND",
            hash_id="hash-ezarc-us-send",
            sid="1422",
            msku="EZ-US-SEND",
            fba_plus_days=60,
            fba_days=20,
            out_stock_date="2026-05-12",
        )
        client = FakeLingxingClient(
            seller_map={"1422": "EZARC NA-US"},
            raw_items=[item],
            inventory_snapshot_map={("1422", "B-EZARC-US-SEND"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )
        notifier = FakeNotifier()

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                exporter=lambda alerts, today, **kwargs: "reports/2026-04-21/EZARC库存预警测试-20260421.xlsx",
                notifier=notifier,
                notify_user_ids=["fallback-user"],
                scope="ezarc-test",
            )
        )

        self.assertEqual(notifier.texts, [])

    def test_run_alert_job_with_yplus_test_scope_sends_to_store_policy_users(self) -> None:
        item = make_summary_item(
            asin="B-YPLUS-US-SEND",
            hash_id="hash-yplus-us-send",
            sid="2344",
            msku="YP-US-SEND",
            fba_plus_days=45,
            fba_days=14,
            out_stock_date="2026-05-12",
        )
        client = FakeLingxingClient(
            seller_map={"2344": "YPLUS-US-US"},
            raw_items=[item],
            inventory_snapshot_map={("2344", "B-YPLUS-US-SEND"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )
        notifier = FakeNotifier()

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1448"],
                exporter=lambda alerts, today, **kwargs: "reports/2026-04-21/YPLUS库存预警测试-20260421.xlsx",
                notifier=notifier,
                notify_user_ids=["fallback-user"],
                scope="yplus-test",
            )
        )

        self.assertEqual(notifier.texts, [])

    def test_run_alert_job_with_formal_brand_scopes_uses_formal_report_names(self) -> None:
        ezarc_item = make_summary_item(
            asin="B-EZARC-FORMAL",
            hash_id="hash-ezarc-formal",
            sid="1422",
            msku="EZ-FORMAL",
            fba_plus_days=60,
            fba_days=20,
            out_stock_date="2026-05-12",
        )
        yplus_item = make_summary_item(
            asin="B-YPLUS-FORMAL",
            hash_id="hash-yplus-formal",
            sid="2344",
            msku="YP-FORMAL",
            fba_plus_days=45,
            fba_days=14,
            out_stock_date="2026-05-12",
        )
        calls: list[tuple[str, bool]] = []

        def export_report(alerts: list[object], today: date, **kwargs: object) -> str:
            calls.append((str(kwargs["main_report_name"]), bool(kwargs["include_store_reports"])))
            return f"reports/2026-04-21/{kwargs['main_report_name']}-20260421.xlsx"

        asyncio.run(
            run_alert_job(
                client=FakeLingxingClient(
                    seller_map={"1422": "EZARC NA-US"},
                    raw_items=[ezarc_item],
                    inventory_snapshot_map={("1422", "B-EZARC-FORMAL"): InventorySnapshot(8, 1, 1, 10, 5)},
                    listing_items=[],
                ),
                today=date(2026, 4, 21),
                sid_list=["1448"],
                exporter=export_report,
                scope="ezarc",
                dry_run=True,
            )
        )
        asyncio.run(
            run_alert_job(
                client=FakeLingxingClient(
                    seller_map={"2344": "YPLUS-US-US"},
                    raw_items=[yplus_item],
                    inventory_snapshot_map={("2344", "B-YPLUS-FORMAL"): InventorySnapshot(8, 1, 1, 10, 5)},
                    listing_items=[],
                ),
                today=date(2026, 4, 21),
                sid_list=["1448"],
                exporter=export_report,
                scope="yplus",
                dry_run=True,
            )
        )

        self.assertEqual(calls, [("EZARC库存预警", True), ("YPLUS库存预警", True)])

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
        self.assertEqual(notifier.texts, [])

    def test_run_alert_job_with_notify_override_sends_only_to_override_user(self) -> None:
        item = make_summary_item(
            asin="B-US",
            hash_id="hash-us-override",
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
                notify_user_override_ids=["asker-user"],
            )
        )

        self.assertEqual(result.report_path, "reports/2026-04-21/Libraton NA-US/LIBRATON库存预警-NA-US-20260421.xlsx")
        self.assertEqual(notifier.texts, [])

    def test_run_alert_job_with_upload_only_skips_all_notifications(self) -> None:
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
                notify_user_ids=["u1", "u2"],
                upload_only=True,
            )
        )

        self.assertEqual(notifier.texts, [])

    def test_run_alert_job_with_ezarc_test_merges_jp_rows_by_asin(self) -> None:
        ezarc_item = make_summary_item(
            asin="JP-1",
            hash_id="hash-jp-a",
            sid="2002",
            msku="JP-SKU-1",
            fba_plus_days=0,
            fba_days=0,
            out_stock_date="",
            estimated_sale_avg_quantity=0.0,
            amazon_quantity_valid=0,
            amazon_quantity_shipping=0,
            afn_fulfillable_quantity=0,
            reserved_fc_transfers=0,
            reserved_fc_processing=0,
        )
        cbt_item = make_summary_item(
            asin="JP-1",
            hash_id="hash-jp-b",
            sid="2003",
            msku="JP-SKU-1S",
            fba_plus_days=9,
            fba_days=9,
            out_stock_date="2026-04-16",
            estimated_sale_avg_quantity=2.63,
            amazon_quantity_valid=0,
            amazon_quantity_shipping=0,
            afn_fulfillable_quantity=0,
            reserved_fc_transfers=0,
            reserved_fc_processing=0,
        )
        client = FakeLingxingClient(
            seller_map={"2002": "EZARC JP-JP", "2003": "CBT-F Tools-JP"},
            raw_items=[ezarc_item, cbt_item],
            inventory_snapshot_map={
                ("2002", "JP-1"): InventorySnapshot(0, 0, 0, 0, 250),
                ("2003", "JP-1"): InventorySnapshot(14, 0, 0, 14, 0),
            },
            listing_items=[],
        )
        exported: list[list[object]] = []

        def export_report(alerts: list[object], today: date) -> str:
            exported.append(alerts)
            return "reports/2026-04-07/EZARC库存预警测试-20260407.xlsx"

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 7),
                sid_list=["2002", "2003"],
                exporter=export_report,
                scope="ezarc-test",
                dry_run=True,
            )
        )

        self.assertEqual(len(exported[0]), 1)
        self.assertEqual(exported[0][0].seller_name, "EZARC JP 汇总")
        self.assertEqual(exported[0][0].asin, "JP-1")
        self.assertEqual(exported[0][0].mskus, ["JP-SKU-1", "JP-SKU-1S"])
        self.assertEqual(exported[0][0].level, "A")
        self.assertEqual(exported[0][0].fba_inventory, 14)
        self.assertEqual(exported[0][0].fba_inbound_inventory, 250)
        self.assertEqual(exported[0][0].summary_daily_sales, 2.63)
        self.assertEqual(
            build_report_rows(exported[0]),
            [
                {
                    "店铺": "EZARC JP 汇总",
                    "等级": "A",
                    "MSKU": "JP-SKU-1、JP-SKU-1S",
                    "ASIN": "JP-1",
                    "Listing联系人": "",
                    "命中条数": 2,
                    "命中规则": "可售天数(FBA)=5天；断货时间(天数)=5天",
                    "日均销量": 2.63,
                    "FBA库存": 14,
                    "可售天数(FBA)": 5,
                    "FBA在途": 250,
                    "可售天数(FBA+在途)": 100,
                    "断货时间": "2026-04-12",
                    "断货天数": 5,
                    "FBA可售-可售": 14,
                    "FBA可售-待调仓": 0,
                    "FBA可售-调仓中": 0,
                    "补货状态": "正常补货",
                }
            ],
        )
        self.assertIn(("fetch_inventory_snapshot_map", {"2002": {"JP-1"}, "2003": {"JP-1"}}), client.calls)

        formal_client = FakeLingxingClient(
            seller_map={"2002": "EZARC JP-JP", "2003": "CBT-F Tools-JP"},
            raw_items=[ezarc_item, cbt_item],
            inventory_snapshot_map={
                ("2002", "JP-1"): InventorySnapshot(0, 0, 0, 0, 250),
                ("2003", "JP-1"): InventorySnapshot(14, 0, 0, 14, 0),
            },
            listing_items=[],
        )
        formal_exported: list[list[object]] = []

        asyncio.run(
            run_alert_job(
                client=formal_client,
                today=date(2026, 4, 7),
                sid_list=["2002", "2003"],
                exporter=lambda alerts, today: formal_exported.append(alerts) or "reports/2026-04-07/EZARC库存预警-20260407.xlsx",
                scope="ezarc",
                dry_run=True,
            )
        )

        self.assertEqual(len(formal_exported[0]), 1)
        self.assertEqual(formal_exported[0][0].seller_name, "EZARC JP 汇总")
        self.assertEqual(formal_exported[0][0].mskus, ["JP-SKU-1", "JP-SKU-1S"])

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
        self.assertIn(("fetch_summary_items", (("1446", "1448"), 1)), client.calls)

    def test_run_alert_job_uses_asin_dimension_for_libraton(self) -> None:
        item = make_summary_item(
            asin="B-LIB",
            hash_id="hash-lib",
            sid="1443",
            msku="LIB-MSKU",
            fba_plus_days=45,
            fba_days=20,
            out_stock_date="2026-05-02",
        )
        client = FakeLingxingClient(
            seller_map={"1443": "Libraton NA-US"},
            raw_items=[item],
            inventory_snapshot_map={("1443", "B-LIB"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1443"],
                dry_run=True,
            )
        )

        self.assertIn(("fetch_summary_items", (("1443",), 1)), client.calls)

    def test_run_alert_job_keeps_msku_dimension_for_non_libraton(self) -> None:
        item = make_summary_item(
            asin="B-EZARC-US",
            hash_id="hash-ezarc-us-datatype",
            sid="2001",
            msku="EZ-US",
            fba_plus_days=60,
            fba_days=20,
            out_stock_date="2026-05-12",
        )
        client = FakeLingxingClient(
            seller_map={"2001": "EZARC NA-US"},
            raw_items=[item],
            inventory_snapshot_map={("2001", "B-EZARC-US"): InventorySnapshot(8, 1, 1, 10, 5)},
            listing_items=[],
        )

        asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["2001"],
                dry_run=True,
            )
        )

        self.assertIn(("fetch_summary_items", (("2001",), None)), client.calls)

    def test_run_alert_job_splits_libraton_and_other_brands_in_all_scope(self) -> None:
        libraton_item = make_summary_item(
            asin="B-LIB-MIX",
            hash_id="hash-lib-mix",
            sid="1443",
            msku="LIB-MSKU",
            fba_plus_days=45,
            fba_days=20,
            out_stock_date="2026-05-02",
        )
        ezarc_item = make_summary_item(
            asin="B-EZ-MIX",
            hash_id="hash-ez-mix",
            sid="2001",
            msku="EZ-MSKU",
            fba_plus_days=60,
            fba_days=20,
            out_stock_date="2026-05-12",
        )
        client = FakeLingxingClient(
            seller_map={"1443": "Libraton NA-US", "2001": "EZARC NA-US"},
            raw_items=[libraton_item, ezarc_item],
            inventory_snapshot_map={
                ("1443", "B-LIB-MIX"): InventorySnapshot(8, 1, 1, 10, 5),
                ("2001", "B-EZ-MIX"): InventorySnapshot(8, 1, 1, 10, 5),
            },
            listing_items=[],
        )

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 21),
                sid_list=["1443", "2001"],
                dry_run=True,
            )
        )

        self.assertEqual(result.sid_distribution, {"1443": 1, "2001": 1})
        self.assertIn(("fetch_summary_items", (("1443",), 1)), client.calls)
        self.assertIn(("fetch_summary_items", (("2001",), None)), client.calls)

    def test_run_alert_job_fetches_inventory_snapshot_for_scope_asins(self) -> None:
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

    def test_run_alert_job_prefers_summary_inventory_fields_when_present(self) -> None:
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
        self.assertEqual(record.fba_inventory, 99)
        self.assertEqual(record.fba_inbound_inventory, 88)
        self.assertEqual(record.fba_sellable_inventory, 77)
        self.assertEqual(record.fba_transfer_reserved_inventory, 11)
        self.assertEqual(record.fba_processing_inventory, 10)

    def test_run_alert_job_can_promote_non_alert_summary_row_to_c_level_from_source_list(self) -> None:
        item = make_summary_item(
            asin="B0FDG7BRXJ",
            hash_id="hash-source-list-c-level",
            sid="1457",
            msku="919005",
            fba_plus_days=48,
            fba_days=0,
            out_stock_date="2026-04-28",
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
            inventory_snapshot_map={("1457", "B0FDG7BRXJ"): InventorySnapshot(0, 0, 0, 0, 48)},
            listing_items=[],
        )
        exported: list[tuple[list[object], date]] = []

        def export_report(alerts: list[object], today: date) -> str:
            exported.append((alerts, today))
            return "reports/2026-04-28/LIBRATON库存预警-20260428.xlsx"

        result = asyncio.run(
            run_alert_job(
                client=client,
                today=date(2026, 4, 28),
                sid_list=["1457"],
                exporter=export_report,
                dry_run=True,
            )
        )

        self.assertEqual(result.alert_count, 1)
        record = exported[0][0][0]
        self.assertEqual(record.level, "C")
        self.assertEqual(record.fba_inventory, 0)
        self.assertEqual(record.fba_inbound_inventory, 48)
        self.assertEqual(record.mskus, ["919005"])
        self.assertIn(("fetch_inventory_snapshot_map", {"1457": {"B0FDG7BRXJ"}}), client.calls)

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
