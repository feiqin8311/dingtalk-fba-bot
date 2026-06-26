from datetime import date
import unittest

from fba_alert.models import AlertRecord
from fba_alert.store_policies import (
    DEFAULT_STORE_POLICY,
    get_store_policy,
    resolve_notify_user_ids,
    resolve_sid_list,
)


class StorePolicyTests(unittest.TestCase):
    def test_get_store_policy_returns_default_for_unknown_store(self) -> None:
        policy = get_store_policy("Libraton EU-FR")

        self.assertEqual(policy.alert_thresholds, DEFAULT_STORE_POLICY.alert_thresholds)
        self.assertEqual(policy.notify_user_ids, [])
        self.assertFalse(policy.auto_include_sid)

    def test_get_store_policy_returns_special_policy_for_na_ca(self) -> None:
        policy = get_store_policy("Libraton NA-CA")

        self.assertTrue(policy.auto_include_sid)
        self.assertEqual(policy.alert_thresholds["a_fba_plus_days"], 55)
        self.assertEqual(policy.alert_thresholds["b_fba_plus_days"], 70)
        self.assertEqual(policy.notify_user_ids, ["01364646263121664148"])

    def test_get_store_policy_returns_special_policy_for_na_us(self) -> None:
        policy = get_store_policy("Libraton NA-US")

        self.assertTrue(policy.auto_include_sid)
        self.assertEqual(policy.alert_thresholds["a_fba_plus_days"], 45)
        self.assertEqual(policy.alert_thresholds["a_out_stock_days"], 30)
        self.assertEqual(policy.alert_thresholds["b_equal_out_stock_days"], 45)
        self.assertEqual(policy.alert_thresholds["b_fba_plus_days"], 60)
        self.assertEqual(
            policy.notify_user_ids,
            ["17489140420206931", "17490879808802516"],
        )

    def test_get_store_policy_returns_special_policy_for_libraton_eu(self) -> None:
        policy = get_store_policy("Libraton EU-DE")

        self.assertEqual(policy.alert_thresholds["a_fba_days"], 14)
        self.assertEqual(policy.alert_thresholds["a_fba_plus_days"], 65)
        self.assertEqual(policy.alert_thresholds["a_out_stock_days"], 65)
        self.assertEqual(policy.alert_thresholds["b_fba_days"], 30)
        self.assertIsNone(policy.alert_thresholds["b_equal_out_stock_days"])
        self.assertEqual(policy.alert_thresholds["b_fba_plus_days"], 80)

    def test_get_store_policy_returns_special_policy_for_ezarc_jp(self) -> None:
        policy = get_store_policy("EZARC JP-JP")

        self.assertEqual(policy.alert_thresholds["a_fba_days"], 20)
        self.assertEqual(policy.alert_thresholds["a_fba_plus_days"], 30)
        self.assertEqual(policy.alert_thresholds["a_out_stock_days"], 50)
        self.assertIsNone(policy.alert_thresholds["b_fba_days"])
        self.assertEqual(policy.notify_user_ids, ["17439904366695445"])

    def test_get_store_policy_returns_special_policy_for_ezarc_regions(self) -> None:
        eu_policy = get_store_policy("EZARC EU-DE")
        na_policy = get_store_policy("EZARC NA-US")

        self.assertEqual(
            eu_policy.notify_user_ids,
            [
                "17506435638027211",
                "17585057805545058",
                "17633432685584853",
                "17800198373694159",
                "17465848709312615",
            ],
        )
        self.assertEqual(
            na_policy.notify_user_ids,
            [
                "290435484624363486",
                "01076420214327759759",
                "454365106138190421",
                "17427794048531392",
                "17750084401515036",
                "17403614178121993",
            ],
        )

    def test_get_store_policy_returns_special_policy_for_yplus_jp(self) -> None:
        policy = get_store_policy("YPLUS-JP-JP")

        self.assertEqual(policy.alert_thresholds["a_fba_days"], 14)
        self.assertIsNone(policy.alert_thresholds["a_fba_plus_days"])
        self.assertEqual(policy.alert_thresholds["a_out_stock_days"], 40)
        self.assertIsNone(policy.alert_thresholds["b_fba_days"])

    def test_get_store_policy_returns_special_policy_for_yplus_us(self) -> None:
        policy = get_store_policy("YPLUS-US-US")

        self.assertEqual(policy.notify_user_ids, ["17441633442965653"])

    def test_get_store_policy_returns_special_policy_for_yplus_eu(self) -> None:
        policy = get_store_policy("YPLUS-EU-DE")

        self.assertEqual(
            policy.notify_user_ids,
            ["23210537641286444", "350843032936428602"],
        )

    def test_get_store_policy_returns_special_policy_for_yplus_ca(self) -> None:
        policy = get_store_policy("YPLUS-US-CA")

        self.assertEqual(policy.notify_user_ids, ["395439341733212350"])

    def test_resolve_sid_list_adds_auto_include_store_sids(self) -> None:
        seller_map = {
            "1448": "Libraton EU-DE",
            "1443": "Libraton NA-US",
            "1444": "Libraton NA-CA",
            "1457": "Libraton JP-JP",
        }

        sid_list = resolve_sid_list(["1448"], seller_map)

        self.assertEqual(sid_list, ["1448", "1443", "1444", "1457"])

    def test_resolve_notify_user_ids_uses_store_specific_recipients(self) -> None:
        alerts = [
            AlertRecord(
                level="A",
                reasons=["rule"],
                asin="B1443",
                sid="1443",
                seller_name="Libraton NA-US",
                node_type=1,
                mskus=["MSKU-1443"],
                listing_contacts="",
                fba_plus_days=0,
                fba_days=10,
                fba_inventory=1,
                fba_inbound_inventory=0,
                fba_sellable_inventory=1,
                fba_transfer_reserved_inventory=0,
                fba_processing_inventory=0,
                summary_daily_sales=1.0,
                out_stock_date=str(date(2026, 4, 20)),
                out_stock_days=13,
                hash_id="hash-1443",
            ),
            AlertRecord(
                level="A",
                reasons=["rule"],
                asin="B1457",
                sid="1457",
                seller_name="Libraton JP-JP",
                node_type=1,
                mskus=["MSKU-1457"],
                listing_contacts="",
                fba_plus_days=0,
                fba_days=10,
                fba_inventory=1,
                fba_inbound_inventory=0,
                fba_sellable_inventory=1,
                fba_transfer_reserved_inventory=0,
                fba_processing_inventory=0,
                summary_daily_sales=1.0,
                out_stock_date=str(date(2026, 4, 20)),
                out_stock_days=13,
                hash_id="hash-1457",
            ),
        ]

        user_ids = resolve_notify_user_ids(alerts, ["fallback-user"])

        self.assertEqual(
            user_ids,
            [
                "17489140420206931",
                "17490879808802516",
                "250755202726645853",
            ],
        )


if __name__ == "__main__":
    unittest.main()
