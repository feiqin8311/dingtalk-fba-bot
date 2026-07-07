import importlib.util
import sys
import types
import unittest
from pathlib import Path


FBA_ALERT_MODULE_NAMES = ("fba_alert", "fba_alert.config", "fba_alert.lingxing", "fba_alert.utils")


def snapshot_modules() -> dict[str, object]:
    return {name: sys.modules.get(name) for name in FBA_ALERT_MODULE_NAMES}


def restore_modules(snapshot: dict[str, object]) -> None:
    for name, module in snapshot.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load_script_module():
    snapshot = snapshot_modules()
    sys.modules.pop("fba_alert", None)
    sys.modules.pop("fba_alert.config", None)
    sys.modules.pop("fba_alert.lingxing", None)
    sys.modules.pop("fba_alert.utils", None)

    package = types.ModuleType("fba_alert")
    config_module = types.ModuleType("fba_alert.config")
    lingxing_module = types.ModuleType("fba_alert.lingxing")
    utils_module = types.ModuleType("fba_alert.utils")

    config_module.load_config = lambda: None

    class LingxingClient:
        pass

    lingxing_module.LingxingClient = LingxingClient
    utils_module.load_env_file = lambda env_path=".env": None

    sys.modules["fba_alert"] = package
    sys.modules["fba_alert.config"] = config_module
    sys.modules["fba_alert.lingxing"] = lingxing_module
    sys.modules["fba_alert.utils"] = utils_module

    script_path = Path(__file__).resolve().parent.parent / "lignxing-data2.py"
    spec = importlib.util.spec_from_file_location("lignxing_data2", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        restore_modules(snapshot)


def load_summary_script_module():
    snapshot = snapshot_modules()
    sys.modules.pop("fba_alert", None)
    sys.modules.pop("fba_alert.config", None)
    sys.modules.pop("fba_alert.lingxing", None)
    sys.modules.pop("fba_alert.utils", None)

    package = types.ModuleType("fba_alert")
    config_module = types.ModuleType("fba_alert.config")
    lingxing_module = types.ModuleType("fba_alert.lingxing")
    utils_module = types.ModuleType("fba_alert.utils")

    config_module.load_config = lambda: None

    class LingxingClient:
        pass

    lingxing_module.LingxingClient = LingxingClient
    utils_module.load_env_file = lambda env_path=".env": None

    sys.modules["fba_alert"] = package
    sys.modules["fba_alert.config"] = config_module
    sys.modules["fba_alert.lingxing"] = lingxing_module
    sys.modules["fba_alert.utils"] = utils_module

    script_path = Path(__file__).resolve().parent.parent / "lignxing-data.py"
    spec = importlib.util.spec_from_file_location("lignxing_data", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        restore_modules(snapshot)


class LingxingData2Tests(unittest.TestCase):
    def test_build_sample_supports_currency_month_response(self) -> None:
        module = load_script_module()

        response = {
            "code": 0,
            "message": "success",
            "data": [
                {
                    "date": "2026-04",
                    "code": "CNY",
                    "icon": "￥",
                    "name": "人民币",
                    "rate_org": "1.0000",
                    "my_rate": "1.0000",
                    "update_time": "2019-12-30 00:00:00",
                },
                {
                    "date": "2026-04",
                    "code": "USD",
                    "icon": "$",
                    "name": "美元",
                    "rate_org": "7.2000",
                    "my_rate": "7.1800",
                    "update_time": "2019-12-30 00:00:00",
                },
            ],
            "total": 2,
        }

        self.assertEqual(
            module.build_sample(response),
            {
                "month": "2026-04",
                "total": 2,
                "currencies": [
                    {
                        "code": "CNY",
                        "icon": "￥",
                        "name": "人民币",
                        "rate_org": "1.0000",
                        "my_rate": "1.0000",
                        "update_time": "2019-12-30 00:00:00",
                    },
                    {
                        "code": "USD",
                        "icon": "$",
                        "name": "美元",
                        "rate_org": "7.2000",
                        "my_rate": "7.1800",
                        "update_time": "2019-12-30 00:00:00",
                    },
                ],
            },
        )

    def test_build_sample_reads_estimated_sale_avg_quantity_from_top_level_suggest_info(self) -> None:
        module = load_summary_script_module()

        item = {
            "basic_info": {
                "asin": "B001",
                "sid": "1448",
                "hash_id": "hash-1",
                "msku_fnsku_list": [{"msku": "MSKU-1", "fnsku": "FNSKU-1"}],
            },
            "suggest_info": {
                "available_sale_days_fba": 12,
                "fba_available_sale_days": 34,
                "out_stock_date": "2026-04-30",
                "estimated_sale_avg_quantity": 5.5,
            },
            "sales_info": {
                "sales_avg_7": 7,
                "sales_avg_14": 14,
                "sales_avg_30": 30,
            },
            "amazon_quantity_info": {
                "amazon_quantity_valid": 10,
                "amazon_quantity_shipping": 20,
                "afn_fulfillable_quantity": 8,
                "reserved_fc_transfers": 1,
                "reserved_fc_processing": 1,
            },
            "data": {},
        }

        self.assertEqual(
            module.build_sample(item)["suggest_info"]["estimated_sale_avg_quantity"],
            5.5,
        )


if __name__ == "__main__":
    unittest.main()
