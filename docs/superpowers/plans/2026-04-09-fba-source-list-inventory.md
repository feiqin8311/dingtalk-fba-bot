# FBA Source List Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace inventory values in the alert flow with aggregates from `/erp/sc/routing/fbaSug/asin/getSourceList` while keeping `getSummaryList` as the source of summary alert candidates and sale-day metrics.

**Architecture:** Keep `getSummaryList` as the first-stage fetch for summary items, then enrich each alert record by requesting `getSourceList` twice per `sid + asin`: `type=1` for stock-side quantities and `type=2` for inbound quantities. Store the aggregates on `AlertRecord`, use them in the C-level rule and Excel output, and preserve the existing A/B day-based rules.

**Tech Stack:** Python 3.11+, aiohttp, dataclasses, unittest, openpyxl

---

### Task 1: Add Failing Tests For Source-List Aggregation

**Files:**
- Modify: `tests/test_summary_daily_sales.py`
- Test: `tests/test_summary_daily_sales.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_aggregate_inventory_snapshot_sums_type_1_and_type_2_values(self) -> None:
        type_1_rows = [
            {"remark": {"afn_fulfillable_quantity": "3", "reserved_fc_transfers": "2", "reserved_fc_processing": "1"}},
            {"remark": {"afn_fulfillable_quantity": "4", "reserved_fc_transfers": "5", "reserved_fc_processing": "6"}},
        ]
        type_2_rows = [
            {"quantity": 7},
            {"quantity": "8"},
        ]

        snapshot = aggregate_inventory_snapshot(type_1_rows, type_2_rows)

        self.assertEqual(snapshot.fba_sellable_inventory, 7)
        self.assertEqual(snapshot.fba_transfer_reserved_inventory, 7)
        self.assertEqual(snapshot.fba_processing_inventory, 7)
        self.assertEqual(snapshot.fba_inventory, 21)
        self.assertEqual(snapshot.fba_inbound_inventory, 15)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: FAIL because `aggregate_inventory_snapshot` does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class InventorySnapshot:
    fba_sellable_inventory: int
    fba_transfer_reserved_inventory: int
    fba_processing_inventory: int
    fba_inventory: int
    fba_inbound_inventory: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: PASS for the new aggregation test

- [ ] **Step 5: Commit**

```bash
git add tests/test_summary_daily_sales.py fba_alert/models.py fba_alert/lingxing.py
git commit -m "test: cover source list inventory aggregation"
```

### Task 2: Add Failing Test For C-Level Enrichment

**Files:**
- Modify: `tests/test_summary_daily_sales.py`
- Test: `tests/test_summary_daily_sales.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_apply_inventory_snapshots_updates_c_level_inventory_fields(self) -> None:
        record = classify_record(item, date(2026, 4, 7), {"1448": "店铺A"}, {"1448"})
        assert record is not None
        snapshot_map = {
            ("1448", "B001"): InventorySnapshot(
                fba_sellable_inventory=0,
                fba_transfer_reserved_inventory=0,
                fba_processing_inventory=0,
                fba_inventory=0,
                fba_inbound_inventory=12,
            )
        }

        apply_inventory_snapshots([record], snapshot_map)

        self.assertEqual(record.level, "C")
        self.assertEqual(record.reasons, ["FBA库存=0 且 FBA在途=12"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: FAIL because inventory enrichment is not implemented

- [ ] **Step 3: Write minimal implementation**

```python
def apply_inventory_snapshots(records, snapshot_map):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: PASS for enrichment and existing rule tests

- [ ] **Step 5: Commit**

```bash
git add tests/test_summary_daily_sales.py fba_alert/alerts.py fba_alert/models.py
git commit -m "feat: apply source list inventory to alert records"
```

### Task 3: Fetch Source-List Inventory In Main Flow

**Files:**
- Modify: `fba_alert/lingxing.py`
- Modify: `fba_alert/main.py`
- Test: `tests/test_summary_daily_sales.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_build_inventory_snapshot_map_uses_type_1_and_type_2_rows(self) -> None:
        ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: FAIL because the bulk inventory snapshot builder does not exist

- [ ] **Step 3: Write minimal implementation**

```python
async def fetch_inventory_snapshot_map(self, access_token: str, sid_asin_map: dict[str, set[str]]) -> dict[tuple[str, str], InventorySnapshot]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: PASS and no regressions in report tests

- [ ] **Step 5: Commit**

```bash
git add fba_alert/lingxing.py fba_alert/main.py tests/test_summary_daily_sales.py
git commit -m "feat: enrich alerts with source list inventory"
```

### Task 4: Verify Report Output Still Matches New Inventory Fields

**Files:**
- Modify: `fba_alert/report.py`
- Modify: `tests/test_summary_daily_sales.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_build_report_rows_outputs_source_list_inventory_columns(self) -> None:
        ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: FAIL if report output still reflects stale inventory assumptions

- [ ] **Step 3: Write minimal implementation**

```python
rows.append({"FBA库存": item.fba_inventory, "FBA在途": item.fba_inbound_inventory, ...})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test*.py' -v`
Expected: PASS for all tests

- [ ] **Step 5: Commit**

```bash
git add fba_alert/report.py tests/test_summary_daily_sales.py
git commit -m "test: verify report uses source list inventory"
```
