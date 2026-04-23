from typing import Any


def make_summary_item(
    *,
    asin: str = "B001",
    hash_id: str = "hash-1",
    sid: str = "1448",
    msku: str = "MSKU-1",
    fba_plus_days: int = 50,
    fba_days: int = 6,
    out_stock_date: str = "2026-04-20",
    estimated_sale_avg_quantity: float | None = None,
    amazon_quantity_valid: int = 5,
    amazon_quantity_shipping: int = 12,
    afn_fulfillable_quantity: int = 9,
    reserved_fc_transfers: int = 2,
    reserved_fc_processing: int = 1,
) -> dict[str, Any]:
    suggest_info: dict[str, Any] = {
        "fba_available_sale_days": fba_plus_days,
        "available_sale_days_fba": fba_days,
        "out_stock_date": out_stock_date,
    }
    if estimated_sale_avg_quantity is not None:
        suggest_info["estimated_sale_avg_quantity"] = estimated_sale_avg_quantity

    return {
        "basic_info": {
            "asin": asin,
            "hash_id": hash_id,
            "sid": sid,
            "node_type": 1,
            "msku_fnsku_list": [{"msku": msku}],
        },
        "suggest_info": suggest_info,
        "sales_info": {
            "sales_avg_7": 10,
            "sales_avg_14": 20,
            "sales_avg_30": 30,
        },
        "data": {
            "amazon_quantity_info": {
                "amazon_quantity_valid": amazon_quantity_valid,
                "amazon_quantity_shipping": amazon_quantity_shipping,
                "afn_fulfillable_quantity": afn_fulfillable_quantity,
                "reserved_fc_transfers": reserved_fc_transfers,
                "reserved_fc_processing": reserved_fc_processing,
            }
        },
        "ext_info": {"restock_status": 0},
    }
