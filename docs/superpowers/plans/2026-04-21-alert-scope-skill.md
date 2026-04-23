# Alert Scope Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scope-aware execution so the project and its AI skill can run either the full Libraton alert workflow or a specific regional report without querying unrelated stores.

**Architecture:** Introduce a small scope model in Python that decides which seller names and SIDs are in scope, then thread that scope through CLI parsing, report export, and notification behavior. Keep the AI skill thin: it should map a small fixed set of Chinese phrases to the new `--scope` argument and continue preferring `--dry-run`.

**Tech Stack:** Python 3.11, `unittest`, existing `fba_alert` package, repository skill markdown and shell script wrappers

---

## File Map

- Modify: `fba_alert/main.py`
  Responsibility: parse `--scope` and pass it into the application layer.
- Modify: `fba_alert/application.py`
  Responsibility: branch between full-report and scoped-report execution, export, and notification.
- Create: `fba_alert/scopes.py`
  Responsibility: define the supported scopes and resolve seller-name / SID filtering for each scope.
- Modify: `fba_alert/store_policies.py`
  Responsibility: expose the minimal seller-group knowledge needed by the scope layer if helper functions belong here.
- Modify: `tests/test_application.py`
  Responsibility: verify `all/us/ca/jp/eu` execution behavior and notification behavior.
- Create: `tests/test_scopes.py`
  Responsibility: verify scope parsing and seller/SID resolution logic independently from the main job.
- Modify: `skills/dingtalk-fba-alert/SKILL.md`
  Responsibility: document the fixed phrase -> scope mapping.
- Modify: `skills/dingtalk-fba-alert/references/config.md`
  Responsibility: document scoped command examples.
- Modify: `skills/dingtalk-fba-alert/scripts/run-fba-alert.sh`
  Responsibility: pass through `--scope` cleanly.
- Modify: `README.md`
  Responsibility: document `--scope` usage and the behavior difference between full and regional runs.

### Task 1: Add Scope Model

**Files:**
- Create: `fba_alert/scopes.py`
- Test: `tests/test_scopes.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from fba_alert.scopes import AlertScope, resolve_scope_seller_names


class ScopeTests(unittest.TestCase):
    def test_parse_all_scope(self) -> None:
        self.assertEqual(AlertScope.parse("all"), AlertScope.ALL)

    def test_parse_rejects_unknown_scope(self) -> None:
        with self.assertRaises(ValueError):
            AlertScope.parse("mx")

    def test_eu_scope_resolves_both_supported_eu_stores(self) -> None:
        seller_map = {
            "1446": "Libraton EU-UK",
            "1448": "Libraton EU-DE",
            "1443": "Libraton NA-US",
        }

        self.assertEqual(
            resolve_scope_seller_names(AlertScope.EU, seller_map),
            {"Libraton EU-UK", "Libraton EU-DE"},
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_scopes -v`
Expected: FAIL because `fba_alert.scopes` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from enum import Enum


class AlertScope(str, Enum):
    ALL = "all"
    US = "us"
    CA = "ca"
    JP = "jp"
    EU = "eu"

    @classmethod
    def parse(cls, value: str) -> "AlertScope":
        normalized = (value or "all").strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unsupported alert scope: {value}") from exc
```

- [ ] **Step 4: Extend implementation to resolve seller names and SIDs**

```python
SCOPE_SELLER_NAMES = {
    AlertScope.US: {"Libraton NA-US"},
    AlertScope.CA: {"Libraton NA-CA"},
    AlertScope.JP: {"Libraton JP-JP"},
    AlertScope.EU: {"Libraton EU-DE", "Libraton EU-UK"},
}


def resolve_scope_seller_names(scope: AlertScope, seller_map: dict[str, str]) -> set[str]:
    if scope is AlertScope.ALL:
        return set(seller_map.values())
    return set(SCOPE_SELLER_NAMES[scope])


def resolve_scope_sid_list(scope: AlertScope, base_sid_list: list[str], seller_map: dict[str, str]) -> list[str]:
    if scope is AlertScope.ALL:
        return list(base_sid_list)
    target_sellers = resolve_scope_seller_names(scope, seller_map)
    result = [sid for sid, seller_name in seller_map.items() if seller_name in target_sellers]
    if not result:
        raise RuntimeError(f"scope={scope.value} 未匹配到任何店铺 SID")
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_scopes -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fba_alert/scopes.py tests/test_scopes.py
git commit -m "feat: add alert scope model"
```

### Task 2: Add CLI Scope Argument

**Files:**
- Modify: `fba_alert/main.py`
- Test: `tests/test_scopes.py`

- [ ] **Step 1: Write the failing test**

```python
from fba_alert.main import parse_args
import sys
import unittest


class MainArgTests(unittest.TestCase):
    def test_parse_args_reads_scope(self) -> None:
        old_argv = sys.argv[:]
        self.addCleanup(lambda: setattr(sys, "argv", old_argv))
        sys.argv = ["prog", "--scope", "jp"]

        args = parse_args()

        self.assertEqual(args.scope, "jp")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_scopes.MainArgTests -v`
Expected: FAIL because `--scope` is not defined.

- [ ] **Step 3: Write minimal implementation**

```python
parser.add_argument(
    "--scope",
    default="all",
    choices=["all", "us", "ca", "jp", "eu"],
    help="预警范围：all/us/ca/jp/eu，默认 all",
)
```

- [ ] **Step 4: Thread scope into application call**

```python
await run_alert_job(
    ...,
    scope=args.scope,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_scopes.MainArgTests -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fba_alert/main.py tests/test_scopes.py
git commit -m "feat: add alert scope cli option"
```

### Task 3: Scope Application Execution

**Files:**
- Modify: `fba_alert/application.py`
- Modify: `tests/test_application.py`
- Modify: `fba_alert/scopes.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_run_alert_job_with_us_scope_queries_only_na_us(self) -> None:
    client = FakeLingxingClient(
        seller_map={"1443": "Libraton NA-US", "1444": "Libraton NA-CA"},
        raw_items=[make_summary_item(sid="1443", asin="B-US", hash_id="hash-us", fba_days=6)],
        inventory_snapshot_map={("1443", "B-US"): InventorySnapshot(1, 0, 0, 1, 0)},
        listing_items=[],
    )

    asyncio.run(
        run_alert_job(
            client=client,
            today=date(2026, 4, 21),
            sid_list=["1448"],
            scope="us",
            dry_run=True,
        )
    )

    self.assertIn(("fetch_summary_items", ("1443",)), client.calls)


def test_run_alert_job_with_us_scope_does_not_send_main_report(self) -> None:
    ...
    self.assertEqual(
        notifier.sent,
        [
            ("17489140420206931", "reports/.../Libraton NA-US/...xlsx"),
            ("17490879808802516", "reports/.../Libraton NA-US/...xlsx"),
        ],
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_application.ApplicationTests.test_run_alert_job_with_us_scope_queries_only_na_us tests.test_application.ApplicationTests.test_run_alert_job_with_us_scope_does_not_send_main_report -v`
Expected: FAIL because `run_alert_job` does not accept `scope`.

- [ ] **Step 3: Write minimal implementation**

```python
from .scopes import AlertScope, resolve_scope_sid_list


scope_value = AlertScope.parse(scope)
effective_sid_list = resolve_sid_list(sid_list, seller_map)
scoped_sid_list = resolve_scope_sid_list(scope_value, effective_sid_list, seller_map)
allowed_sids = set(scoped_sid_list)
raw_items = await client.fetch_summary_items(access_token, scoped_sid_list)
alerts = parse_summary_items(raw_items, today, seller_map, scoped_sid_list, inventory_snapshot_map)
```

- [ ] **Step 4: Add scoped export/notification branch**

```python
if scope_value is AlertScope.ALL:
    report_path = export_report(alerts, today)
    notify_report(report_path, notifier, resolve_main_report_user_ids(user_ids), dry_run=dry_run)
    notify_store_reports(report_path, alerts, today, notifier, user_ids, dry_run=dry_run)
else:
    report_path = export_scoped_report(alerts, today, scope_value)
    notify_store_reports(report_path, alerts, today, notifier, user_ids, dry_run=dry_run)
```

Implementation note:
- `export_scoped_report` should return the target store-group path only.
- For `us/ca/jp`, the scoped report path is the existing per-store report path.
- For `eu`, the scoped report path must be the merged `Libraton EU` path.

- [ ] **Step 5: Run focused tests to verify they pass**

Run: `python -m unittest tests.test_application -v`
Expected: PASS for existing full-flow tests and new scoped tests.

- [ ] **Step 6: Commit**

```bash
git add fba_alert/application.py fba_alert/scopes.py tests/test_application.py
git commit -m "feat: add scoped alert execution"
```

### Task 4: Scoped Export Helper

**Files:**
- Modify: `fba_alert/report.py`
- Modify: `tests/test_summary_daily_sales.py`

- [ ] **Step 1: Write the failing test**

```python
def test_export_alert_report_with_eu_scope_writes_only_merged_eu_report(self) -> None:
    alerts = [
        make_alert_record("Libraton EU-DE", "B-DE", "MSKU-DE"),
        make_alert_record("Libraton EU-UK", "B-UK", "MSKU-UK"),
    ]

    with TemporaryDirectory() as tmp_dir:
        report_path = export_scoped_alert_report(alerts, date(2026, 4, 21), "eu", tmp_dir)

        self.assertTrue(report_path.endswith("Libraton EU/LIBRATON库存预警-EU-20260421.xlsx"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_summary_daily_sales.SummaryDailySalesTests.test_export_alert_report_with_eu_scope_writes_only_merged_eu_report -v`
Expected: FAIL because helper does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def export_scoped_alert_report(alerts: list[AlertRecord], today: date, store_name: str, output_dir: str = "reports") -> str:
    rows = build_report_rows(alerts)
    rows_by_store_report = group_rows_by_store_report(rows)
    store_rows = rows_by_store_report[store_name]
    store_file_path = build_store_report_path(store_name, today, output_dir)
    store_file_path.parent.mkdir(parents=True, exist_ok=True)
    write_report_workbook(store_rows, store_file_path)
    return str(store_file_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_summary_daily_sales.SummaryDailySalesTests.test_export_alert_report_with_eu_scope_writes_only_merged_eu_report -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fba_alert/report.py tests/test_summary_daily_sales.py
git commit -m "feat: add scoped alert report export"
```

### Task 5: Update AI Skill Mapping

**Files:**
- Modify: `skills/dingtalk-fba-alert/SKILL.md`
- Modify: `skills/dingtalk-fba-alert/references/config.md`
- Modify: `skills/dingtalk-fba-alert/scripts/run-fba-alert.sh`
- Modify: `tests/test_skill_scaffold.py`

- [ ] **Step 1: Write the failing test**

```python
def test_skill_documents_supported_scope_phrases(self) -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    self.assertIn("LIBRATON库存美国预警", skill_text)
    self.assertIn("--scope us", skill_text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_skill_scaffold.SkillScaffoldTests.test_skill_documents_supported_scope_phrases -v`
Expected: FAIL because the phrases are not documented yet.

- [ ] **Step 3: Write minimal implementation**

```bash
# in run-fba-alert.sh
python -m fba_alert.main "$@"
```

Implementation note:
- Keep passthrough behavior so `--scope us --dry-run` works.
- In `SKILL.md`, document the exact phrase mapping and preserve the rule that live send should not be used from the skill unless the user explicitly asks.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_skill_scaffold -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/dingtalk-fba-alert/SKILL.md skills/dingtalk-fba-alert/references/config.md skills/dingtalk-fba-alert/scripts/run-fba-alert.sh tests/test_skill_scaffold.py
git commit -m "docs: add scoped alert skill mapping"
```

### Task 6: Update README and Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update docs**

Add:
- `--scope` usage examples
- difference between full and regional runs
- supported region list for first version

- [ ] **Step 2: Run full test suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS with all tests green.

- [ ] **Step 3: Smoke-check scoped dry-run commands**

Run:

```bash
python -m fba_alert.main --dry-run --scope all
python -m fba_alert.main --dry-run --scope us
python -m fba_alert.main --dry-run --scope ca
python -m fba_alert.main --dry-run --scope jp
python -m fba_alert.main --dry-run --scope eu
```

Expected:
- `all` returns the current full-flow behavior
- other scopes do not generate or notify a main report

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add scoped alert usage"
```

## Self-Review

- Spec coverage:
  - supported inputs: covered by Task 5
  - scope model: covered by Task 1
  - CLI: covered by Task 2
  - scoped execution and notification: covered by Task 3
  - scoped export: covered by Task 4
  - docs: covered by Task 5 and Task 6
- Placeholder scan:
  - removed generic TODOs; each task includes explicit files and commands
- Type consistency:
  - plan consistently uses `AlertScope`, `resolve_scope_sid_list`, `scope` string parameter, and `export_scoped_alert_report`
