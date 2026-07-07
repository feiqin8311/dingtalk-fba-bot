# FBA 库存预警业务和代码逻辑

本文是运营排查和代码维护用的口径文档，记录品牌、店铺、SID、预警阈值、接口字段来源、特殊汇总规则、报表字段映射、钉盘上传和钉钉发送规则。

最后校对日期：2026-07-07，按当前本地代码和 `.env` 配置整理。

代码入口：

- CLI：`fba_alert/main.py`
- 主流程：`fba_alert/application.py`
- 预警分类：`fba_alert/alerts.py`
- Lingxing 接口：`fba_alert/lingxing.py`
- 报表导出：`fba_alert/report.py`
- 店铺阈值：`fba_alert/store_policies.py`
- scope 店铺范围：`fba_alert/scopes.py`

常用命令：

```bash
python -m fba_alert.main --scope ezarc --upload-only
python -m fba_alert.main --scope yplus --upload-only
python -m fba_alert.main --scope ezarc-test --upload-only
python -m fba_alert.main --scope yplus-test --upload-only
python -m fba_alert.main --scope all --upload-only
```

`--upload-only` 表示只上传钉盘，不发送钉钉消息。去掉 `--upload-only` 后会按本文“钉盘和发送”规则正式发送。

## 整体流程

`run_alert_job` 的执行顺序：

1. 调 Lingxing token 接口获取 `access_token`。
2. 调店铺列表接口获取 `sid -> seller_name`。
3. 根据 `scope` 解析本次目标店铺 SID。
4. 调补货建议接口 `getSummaryList` 拉原始记录。
5. 先用 `getSummaryList` 做一次初步预警；当前 SourceList 候选实际取本次 scope 原始记录里的 `sid + asin`。
6. 调 SourceList 接口 `getSourceList` 拉库存快照。
7. 用 SourceList 补齐后的库存再做最终预警。
8. 如果是 `ezarc` 或 `ezarc-test`，对 EZARC 日本两店做 ASIN 维度特殊汇总。
9. 调 Listing 接口补充 `Listing联系人`。
10. 生成 Excel 总表和店铺分表。
11. 非 dry-run 且启用钉盘时，上传总表和店铺分表。
12. 如果不是 `--upload-only`，按总表/分表各自收件人发送钉钉消息。

## 品牌和店铺 SID

SID 来自 Lingxing 店铺列表接口。下表列出当前代码 scope 使用到的店铺。

### EZARC

`scope=ezarc` 和 `scope=ezarc-test` 使用这些店铺。补货建议默认走 MSKU 维度，`data_type=2`。两者店铺范围和逻辑一致，区别是测试 scope 的报表标题和文件名带“测试”。

| 区域 | 店铺 | SID | 是否特殊处理 | 预警阈值组 |
| --- | --- | --- | --- | --- |
| 北美 | `EZARC NA-US` | `1422` | 否 | EZARC NA-US |
| 北美 | `EZARC NA-CA` | `1423` | 否 | EZARC NA-CA |
| 欧洲 | `EZARC EU-UK` | `1425` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-ES` | `1426` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-NL` | `1427` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-IT` | `1428` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-DE` | `1429` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-SE` | `1430` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-PL` | `1431` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-FR` | `1432` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-IE` | `6236` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-TR` | `4756` | 否 | EZARC EU |
| 欧洲 | `EZARC EU-BE` | `4757` | 否 | EZARC EU |
| 日本 | `EZARC JP-JP` | `1433` | 是，和 CBT-F Tools-JP 按 ASIN 汇总 | EZARC JP |
| 日本 | `CBT-F Tools-JP` | `4572` | 是，和 EZARC JP-JP 按 ASIN 汇总 | EZARC JP |

`EZARC NA-MX` SID `1424`、`EZARC-SG-SG` SID `1883` 当前不在 `ezarc` / `ezarc-test` scope 中。

### YPLUS

`scope=yplus` 和 `scope=yplus-test` 使用这些店铺。补货建议默认走 MSKU 维度，`data_type=2`。两者店铺范围和逻辑一致，区别是测试 scope 的报表标题和文件名带“测试”。

| 区域 | 店铺 | SID | 预警阈值组 |
| --- | --- | --- | --- |
| 北美 | `YPLUS-US-US` | `2344` | YPLUS-US-US |
| 北美 | `YPLUS-US-CA` | `2345` | YPLUS-US-CA |
| 北美 | `TrailFun-US` | `6047` | TrailFun-US |
| 欧洲 | `YPLUS-EU-UK` | `2694` | YPLUS EU |
| 欧洲 | `YPLUS-EU-IT` | `2695` | YPLUS EU |
| 欧洲 | `YPLUS-EU-DE` | `2696` | YPLUS EU |
| 欧洲 | `YPLUS-EU-FR` | `2697` | YPLUS EU |
| 欧洲 | `YPLUS-EU-ES` | `2698` | YPLUS EU |
| 欧洲 | `YPLUS-EU-NL` | `2699` | YPLUS EU |
| 欧洲 | `YPLUS-EU-SE` | `2700` | YPLUS EU |
| 欧洲 | `YPLUS-EU-PL` | `2701` | YPLUS EU |
| 欧洲 | `YPLUS-EU-BE` | `4090` | YPLUS EU |
| 欧洲 | `YPLUS-EU-TR` | `4872` | YPLUS EU |
| 欧洲 | `YPLUS-EU-IE` | `6531` | YPLUS EU |
| 日本 | `YPLUS-JP-JP` | `2351` | YPLUS-JP-JP |

`YPLUS-US-MX` SID `4040`、`YPLUS-US-BR` SID `5837`、`YPLUS-UAE-AE` SID `5934` 当前不在 `yplus` / `yplus-test` scope 中。

### LIBRATON

Libraton 店铺名以 `Libraton ` 开头时，补货建议强制走 ASIN 维度，`data_type=1`。

| scope | 店铺 | SID | 预警阈值组 | 说明 |
| --- | --- | --- | --- | --- |
| `us` | `Libraton NA-US` | `1443` | Libraton NA-US | `auto_include_sid=True` |
| `ca` | `Libraton NA-CA` | `1444` | Libraton NA-CA | `auto_include_sid=True` |
| `jp` | `Libraton JP-JP` | `1457` | Libraton JP-JP | `auto_include_sid=True` |
| `eu` | `Libraton EU-DE` | `1448` | Libraton EU | 分表归入 `Libraton EU` |
| `eu` | `Libraton EU-UK` | `1446` | Libraton EU | 分表归入 `Libraton EU` |

当前 `.env` 里的基础 SID 是 `1448,1446`。运行 `scope=all` 时，`resolve_sid_list` 会自动追加 `auto_include_sid=True` 的店铺，所以会包含 `Libraton NA-US`、`Libraton NA-CA`、`Libraton JP-JP`。

其他 Libraton 店铺如 EU-FR、EU-IT、EU-PL 等虽然店铺列表里存在，但当前 scope 代码没有主动纳入。

## 补货建议维度

代码位置：`build_summary_fetch_batches`。

规则：

- 店铺名以 `Libraton ` 开头：调用 `getSummaryList` 时传 `data_type=1`，按 ASIN 维度。
- 其他店铺：调用时传 `data_type=None`，使用配置默认值 `LINGXING_DATA_TYPE`；当前默认是 `2`，按 MSKU 维度。

因此：

- EZARC：MSKU 维度。
- YPLUS：MSKU 维度。
- Libraton：ASIN 维度。

## 预警等级通用逻辑

代码位置：`classify_record`。

先判断 C，再判断 A，再判断 B。没有命中任何等级则不进报表。

### C 级

只要满足：

```text
FBA库存 == 0 且 FBA在途 > 0
```

就标记 C 级，原因：

```text
FBA库存=0 且 FBA在途=<数量>
```

### A 级

在没有命中 C 级时，任意一条命中即为 A 级：

```text
0 < 可售天数(FBA) <= a_fba_days
0 < 可售天数(FBA+在途) <= a_fba_plus_days
0 < 断货天数 <= a_out_stock_days
```

如果某个阈值为 `None`，该规则不判断。

### B 级

未命中 C/A 时，任意一条命中即为 B 级：

```text
0 < 可售天数(FBA) <= b_fba_days
0 < 可售天数(FBA) <= b_equal_out_stock_days 且 可售天数(FBA) == 断货天数
0 < 可售天数(FBA+在途) <= b_fba_plus_days
```

如果某个阈值为 `None`，该规则不判断。

注意：A/B 都要求天数 `> 0`，天数为 0 不会命中 A/B。

## 各品牌店铺预警阈值

表头含义：

- `A-FBA`：A 级 `可售天数(FBA)` 阈值。
- `A-FBA+在途`：A 级 `可售天数(FBA+在途)` 阈值。
- `A-断货`：A 级 `断货天数` 阈值。
- `B-FBA`：B 级 `可售天数(FBA)` 阈值。
- `B-FBA=断货`：B 级 `可售天数(FBA)==断货天数` 阈值。
- `B-FBA+在途`：B 级 `可售天数(FBA+在途)` 阈值。
- `-` 表示不判断该规则。

### EZARC 阈值

| 店铺 | SID | A-FBA | A-FBA+在途 | A-断货 | B-FBA | B-FBA=断货 | B-FBA+在途 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `EZARC NA-US` | `1422` | 20 | 60 | 45 | 45 | 60 | 75 |
| `EZARC NA-CA` | `1423` | 20 | 60 | 60 | 45 | 75 | 80 |
| `EZARC EU-*` | 多个 | 14 | 65 | 65 | 30 | - | 90 |
| `EZARC JP-JP` | `1433` | 20 | 30 | 50 | - | - | - |
| `EZARC JP 汇总` | 汇总 | 20 | 30 | 50 | - | - | - |
| `CBT-F Tools-JP` | `4572` | 20 | 30 | 50 | - | - | - |

EZARC 日本站最终不是按单店输出，而是把 `EZARC JP-JP` 和 `CBT-F Tools-JP` 按 ASIN 汇总成 `EZARC JP 汇总` 后再判断 A/C。

### YPLUS 阈值

| 店铺 | SID | A-FBA | A-FBA+在途 | A-断货 | B-FBA | B-FBA=断货 | B-FBA+在途 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `YPLUS-US-US` | `2344` | 14 | 45 | 30 | 30 | 45 | 60 |
| `TrailFun-US` | `6047` | 14 | 45 | 30 | 30 | 45 | 60 |
| `YPLUS-US-CA` | `2345` | 14 | 55 | 45 | 30 | 60 | 70 |
| `YPLUS-EU-*` | 多个 | 14 | 75 | 60 | 30 | 75 | 90 |
| `YPLUS-JP-JP` | `2351` | 14 | - | 40 | - | - | - |

YPLUS 当前没有按 ASIN 汇总的特殊逻辑；按接口返回记录进入普通分类。

### LIBRATON 阈值

| 店铺 | SID | A-FBA | A-FBA+在途 | A-断货 | B-FBA | B-FBA=断货 | B-FBA+在途 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Libraton NA-US` | `1443` | 14 | 45 | 30 | 30 | 45 | 60 |
| `Libraton NA-CA` | `1444` | 14 | 55 | 45 | 30 | 60 | 70 |
| `Libraton JP-JP` | `1457` | 14 | - | 40 | - | - | - |
| `Libraton EU-DE` | `1448` | 14 | 65 | 65 | 30 | - | 80 |
| `Libraton EU-UK` | `1446` | 14 | 65 | 65 | 30 | - | 80 |

未显式配置的店铺使用默认阈值：A-FBA 14、A-FBA+在途 60、A-断货 50、B-FBA 30、B-FBA=断货 60、B-FBA+在途 75。

## 接口字段：补货建议 getSummaryList

接口路径：

```text
/erp/sc/routing/restocking/analysis/getSummaryList
```

代码：`LingxingClient.fetch_summary_items`。

请求体：

| 字段 | 说明 |
| --- | --- |
| `sid_list` | 本次店铺 SID 列表 |
| `data_type` | `1` ASIN 维度，`2` MSKU 维度 |
| `mode` | `LINGXING_MODE` |
| `offset` | 分页 offset |
| `length` | 分页大小，最大 50 |

返回字段使用：

| API 字段 | 代码字段 | 报表字段 | 用途 |
| --- | --- | --- | --- |
| `basic_info.sid` | `sid` | - | 匹配店铺 |
| `basic_info.asin` | `asin` | `ASIN` | SourceList 查询键、报表展示、EZARC JP 汇总键 |
| `basic_info.hash_id` | `hash_id` | - | 去重 |
| `basic_info.node_type` | `node_type` | - | 保存到记录 |
| `basic_info.msku_fnsku_list[].msku` | `mskus` | `MSKU` | 报表展示 |
| `suggest_info.estimated_sale_avg_quantity` | `summary_daily_sales` | `日均销量` | 计算天数，EZARC JP 汇总求和 |
| `suggest_info.available_sale_days_fba` | `fba_days` | `可售天数(FBA)` | 预警规则 |
| `suggest_info.fba_available_sale_days` | `fba_plus_days` | `可售天数(FBA+在途)` | 预警规则 |
| `suggest_info.out_stock_date` | `out_stock_date` | `断货时间` | 计算断货天数 |
| `data.amazon_quantity_info.amazon_quantity_valid` | `fba_inventory` | `FBA库存` | 预警和展示 |
| `data.amazon_quantity_info.amazon_quantity_shipping` | `fba_inbound_inventory` | `FBA在途` | 预警和展示 |
| `data.amazon_quantity_info.afn_fulfillable_quantity` | `fba_sellable_inventory` | `FBA可售-可售` | 展示 |
| `data.amazon_quantity_info.reserved_fc_transfers` | `fba_transfer_reserved_inventory` | `FBA可售-待调仓` | 展示 |
| `data.amazon_quantity_info.reserved_fc_processing` | `fba_processing_inventory` | `FBA可售-调仓中` | 展示 |
| `ext_info.restock_status` | `restock_status` | `补货状态` | `0` 正常补货，`1` 暂不补货 |

当前不按 `restock_status` 剔除记录。`restock_status=1` 仍会进入预警判断，报表显示 `暂不补货`。

## 接口字段：库存明细 getSourceList

接口路径：

```text
/erp/sc/routing/fbaSug/asin/getSourceList
```

代码：

- `LingxingClient.fetch_source_list`
- `LingxingClient.fetch_inventory_snapshot_map`
- `aggregate_inventory_snapshot`

请求体：

| 字段 | 说明 |
| --- | --- |
| `sid` | 店铺 SID |
| `asin` | ASIN |
| `type` | `1` FBA 库存，`2` FBA 在途 |
| `mode` | `LINGXING_MODE` |

缓存：

```text
.cache/fba_alert/source_list/<date>/<sid>-<asin>-<type>-mode<mode>.json
```

当前代码会对本次 scope 下 `getSummaryList` 返回的 `sid + asin` 拉 SourceList 快照；普通分类只有在 `getSummaryList` 对应库存或天数字段为空时才采用 SourceList 值。

### type=1：FBA 库存

| API 字段 | 代码字段 | 报表字段 | 说明 |
| --- | --- | --- | --- |
| `source_list[].quantity` | `fba_inventory` | `FBA库存` | 当前 FBA库存用这个字段求和 |
| `source_list[].remark.afn_fulfillable_quantity` | `fba_sellable_inventory` | `FBA可售-可售` | 可售明细 |
| `source_list[].remark.reserved_fc_transfers` | `fba_transfer_reserved_inventory` | `FBA可售-待调仓` | 待调仓明细 |
| `source_list[].remark.reserved_fc_processing` | `fba_processing_inventory` | `FBA可售-调仓中` | 调仓中明细 |
| `source_list[].remark.afn_reserved_quantity` | - | - | 不单独展示，但通常包含在 `quantity` 中 |

口径提醒：`FBA库存` 使用 `type=1 source_list[].quantity`，不是只用 `afn_fulfillable_quantity`。例如 `quantity=14`、`afn_fulfillable_quantity=3`、`afn_reserved_quantity=11` 时，报表 `FBA库存=14`。

### type=2：FBA 在途

| API 字段 | 代码字段 | 报表字段 |
| --- | --- | --- |
| `source_list[].quantity` | `fba_inbound_inventory` | `FBA在途` |

## SourceList fallback 逻辑

普通分类时，只有 `getSummaryList` 字段为空才用 SourceList 补齐：

- `amazon_quantity_valid` 空：用 SourceList `fba_inventory`。
- `amazon_quantity_shipping` 空：用 SourceList `fba_inbound_inventory`。
- `afn_fulfillable_quantity` 空：用 SourceList `fba_sellable_inventory`。
- `reserved_fc_transfers` 空：用 SourceList `fba_transfer_reserved_inventory`。
- `reserved_fc_processing` 空：用 SourceList `fba_processing_inventory`。
- `available_sale_days_fba` 或 `fba_available_sale_days` 空：用 SourceList 库存和 `estimated_sale_avg_quantity` 重新计算：
  - `可售天数(FBA) = int(FBA库存 / 日均销量)`
  - `可售天数(FBA+在途) = int((FBA库存 + FBA在途) / 日均销量)`
  - 如果 `out_stock_date` 空，则 `断货时间 = today + 可售天数(FBA)`。

## EZARC 日本站特殊汇总

适用范围：

- 在 `scope=ezarc` 和 `scope=ezarc-test` 生效。
- 只处理 `EZARC JP-JP` SID `1433` 和 `CBT-F Tools-JP` SID `4572`。

业务口径：

- 两个日本店铺在最终总表里合并成 `EZARC JP 汇总`。
- 同一个 ASIN 算同一个品，即使 MSKU 不同。
- 例如 `EZK30013` 和 `EZK30013S` 如果 ASIN 都是 `B0CMSZKDH1`，最终只出一条预警，`MSKU` 显示 `EZK30013、EZK30013S`。

代码步骤：

1. 先删除普通分类结果里 `EZARC JP-JP` 和 `CBT-F Tools-JP` 的记录。
2. 遍历原始 `getSummaryList`，只保留这两个店铺。
3. 用 `basic_info.asin` 分桶。
4. 每个 ASIN 桶内：
   - MSKU 去重合并。
   - `summary_daily_sales` 求和。
   - `fba_inventory` 求和。
   - `fba_inbound_inventory` 求和。
   - `fba_sellable_inventory` 求和。
   - `fba_transfer_reserved_inventory` 求和。
   - `fba_processing_inventory` 求和。
5. 重新计算：
   - `可售天数(FBA) = int(汇总 FBA库存 / 汇总日均销量)`
   - `可售天数(FBA+在途) = int((汇总 FBA库存 + 汇总 FBA在途) / 汇总日均销量)`
   - `断货天数 = 可售天数(FBA)`
   - `断货时间 = today + 断货天数`
6. 用 EZARC JP 阈值判断：
   - C：`FBA库存 == 0` 且 `FBA在途 > 0`
   - A：`0 < FBA天数 <= 20`，或 `0 < FBA+在途天数 <= 30`，或 `0 < 断货天数 <= 50`
   - B：不判断
7. 输出：
   - `seller_name = EZARC JP 汇总`
   - `asin = 分桶 ASIN`
   - `mskus = 同 ASIN 下所有主 MSKU`
   - `hash_id = ezarc-jp-<asin>`

## MSKU 处理规则

代码：`normalize_msku`、`is_primary_msku`、`collapse_msku_variants`。

规则：

- 去首尾空格。
- 去掉末尾逗号。
- 过滤 `amzn.gr.` 开头的 MSKU。
- 如果同一记录同时有 `xxx` 和 `xxx-M`，保留 `xxx`，去掉 `xxx-M`。
- 报表中一条预警有多个 MSKU 时，用 `、` 合并到一个单元格。

## 报表字段

代码：`fba_alert/report.py`。

当前列顺序和来源：

| 报表列 | 来源 |
| --- | --- |
| `店铺` | `AlertRecord.seller_name` |
| `等级` | `AlertRecord.level` |
| `MSKU` | `AlertRecord.mskus` 用 `、` 合并 |
| `ASIN` | `AlertRecord.asin` |
| `Listing联系人` | Listing 接口 `principal_info[].principal_name` |
| `命中条数` | `len(AlertRecord.reasons)` |
| `命中规则` | `AlertRecord.reasons` 用 `；` 合并 |
| `日均销量` | `suggest_info.estimated_sale_avg_quantity`；EZARC JP 汇总为同 ASIN 求和 |
| `FBA库存` | `amazon_quantity_valid`；为空时 SourceList `type=1 quantity`；EZARC JP 汇总为同 ASIN 求和 |
| `可售天数(FBA)` | `suggest_info.available_sale_days_fba`；为空时 fallback；EZARC JP 汇总重新计算 |
| `FBA在途` | `amazon_quantity_shipping`；为空时 SourceList `type=2 quantity`；EZARC JP 汇总为同 ASIN 求和 |
| `可售天数(FBA+在途)` | `suggest_info.fba_available_sale_days`；为空时 fallback；EZARC JP 汇总重新计算 |
| `断货时间` | `suggest_info.out_stock_date`；为空时 fallback；EZARC JP 汇总重新计算 |
| `断货天数` | `断货时间 - today`；EZARC JP 汇总为 `可售天数(FBA)` |
| `FBA可售-可售` | `afn_fulfillable_quantity`；为空时 SourceList `remark.afn_fulfillable_quantity` |
| `FBA可售-待调仓` | `reserved_fc_transfers`；为空时 SourceList `remark.reserved_fc_transfers` |
| `FBA可售-调仓中` | `reserved_fc_processing`；为空时 SourceList `remark.reserved_fc_processing` |
| `补货状态` | `ext_info.restock_status`：0 正常补货，1 暂不补货 |

报表行规则：

- 一条 `AlertRecord` 输出一行。
- 多个 MSKU 合并到同一个 `MSKU` 单元格。
- 用 `hash_id` 去重。
- 总表按 `店铺`、`等级`、`断货天数`、`MSKU` 排序。

## Listing 联系人

接口：

```text
/erp/sc/data/mws/listing
```

字段：

| API 字段 | 用途 |
| --- | --- |
| `sid` | 和 alert 的 `sid` 匹配 |
| `asin` | 和 alert 的 `asin` 匹配 |
| `principal_info[].principal_name` | 写入报表 `Listing联系人` |

联系人按 `(sid, asin)` 聚合，去重后用 `, ` 拼接。

## 钉盘和发送

上传逻辑在 `upload_reports_to_dingpan`。

### 报表生成

- `scope=ezarc`：生成 `EZARC库存预警-YYYYMMDD.xlsx` 总表和各店铺分表。
- `scope=ezarc-test`：生成 `EZARC库存预警测试-YYYYMMDD.xlsx` 总表和各店铺分表。
- `scope=yplus`：生成 `YPLUS库存预警-YYYYMMDD.xlsx` 总表和各店铺分表。
- `scope=yplus-test`：生成 `YPLUS库存预警测试-YYYYMMDD.xlsx` 总表和各店铺分表。
- `scope=all`：生成 `LIBRATON库存预警-YYYYMMDD.xlsx` 总表和各店铺分表。
- `scope=us/ca/jp/eu`：只生成对应 Libraton 范围分表。

店铺分表按 `resolve_store_report_group_name` 分组：

- `Libraton EU-DE`、`Libraton EU-UK` 合并到 `Libraton EU` 分表。
- EZARC 日本两店最终合并到 `EZARC JP 汇总` 分表。
- EZARC、YPLUS 其他店铺按店铺名各自生成分表，包括 `TrailFun-US`。

### 钉盘上传

非 dry-run、存在 notifier 且 `DINGTALK_DINGPAN_ENABLED=true` 时上传钉盘。

品牌根目录：

- `EZARC`：`225801991522`
- `YPLUS`：`225802102609`
- `LIBRATON`：`221392062127`

上传路径按文件名和分表店铺名判断品牌，再按区域进入：

- 总表：`汇总/YYYY-MM-DD`
- 店铺名包含 `JP`：`日本/YYYY-MM-DD`
- 店铺名包含 `EU`：`欧洲/YYYY-MM-DD`
- 店铺名包含 `NA`、`US` 或 `CA`：`北美/YYYY-MM-DD`

`scope=all/ezarc/yplus/ezarc-test/yplus-test` 会上传总表和所有分表。`scope=us/ca/jp/eu` 当前不上传钉盘，发送时走钉钉文件直发。

`--upload-only` 上传后跳过所有消息发送。

### 钉钉发送

- 上传拿到钉盘预览链接时，发送文本消息，内容包含预览链接。
- 未拿到预览链接时，回退为钉钉文件直发。
- `--dry-run` 不创建 notifier，不上传钉盘，也不发送消息。
- `--upload-only` 上传后跳过所有消息发送。
- 命令行传 `--notify-user-id` 时，只发送总表给指定 userId，并跳过店铺分表分发。

总表收件人：

- `scope=ezarc/ezarc-test`：从本次预警涉及店铺的 `notify_user_ids` 去重汇总；如果全为空，才用 `.env` 的 `DINGTALK_USER_IDS` 兜底。
- `scope=yplus/yplus-test`：从本次预警涉及店铺的 `notify_user_ids` 去重汇总；如果全为空，才用 `.env` 的 `DINGTALK_USER_IDS` 兜底。
- `scope=all`：固定发给 `MAIN_REPORT_USER_IDS`，当前是 `16063564311489688`、`17331048354297047`。
- `scope=us/ca/jp/eu`：按对应店铺/分组的 `notify_user_ids`，没有则用 `.env` 的 `DINGTALK_USER_IDS` 兜底。

店铺分表收件人：

- 优先使用该店铺或分组在 `STORE_POLICIES` 里的 `notify_user_ids`。
- 如果该店铺或分组没有专属收件人，才用 `.env` 的 `DINGTALK_USER_IDS` 兜底。
- 当前本地 `.env` 兜底只有 `17331048354297047`。

### 当前店铺收件人

代码只保存钉钉 userId，下面姓名为 2026-07-07 通过钉钉 user/get 校验得到的辅助说明。

| 范围 | 店铺/报告 | 收件人 |
| --- | --- | --- |
| EZARC 欧洲 | `EZARC EU-*` | 邸卓璇 `17506435638027211`、熊欢 `17585057805545058`、王怡 `17633432685584853`、孙千 `17800198373694159`、罗英 `17465848709312615` |
| EZARC 北美 | `EZARC NA-US`、`EZARC NA-CA` | 徐梦娴 `290435484624363486`、温丰铖 `01076420214327759759`、陆雨婷 `454365106138190421`、夏雪雪 `17427794048531392`、琚易凡 `17750084401515036`、陈潇潇 `17403614178121993` |
| EZARC 日本 | `EZARC JP-JP`、`EZARC JP 汇总` | 熊亚婷 `17439904366695445` |
| EZARC 日本原店 | `CBT-F Tools-JP` | 无专属收件人；实际最终合并到 `EZARC JP 汇总` 后发给熊亚婷 |
| YPLUS 欧洲 | `YPLUS-EU-*` | 黄杰 `23210537641286444`、邱文杰 `350843032936428602` |
| YPLUS 美国 | `YPLUS-US-US`、`TrailFun-US` | 彭锦 `17441633442965653` |
| YPLUS 加拿大 | `YPLUS-US-CA` | 葛佳伶 `395439341733212350` |
| YPLUS 日本 | `YPLUS-JP-JP` | 葛佳伶 `395439341733212350` |
| Libraton 总表 | `scope=all` 总表 | `16063564311489688`、`17331048354297047` |
| 兜底 | 无专属收件人时 | `17331048354297047` |

## 排查速查

### 为什么某个 MSKU 没进报表

按这个顺序查：

1. `getSummaryList` 是否返回该 MSKU/ASIN。
2. `sid` 是否在当前 scope 里。
3. `restock_status` 只影响展示，不影响是否进报表。
4. 库存字段是否为空，是否触发 SourceList fallback。
5. 计算后的 A/B/C 是否命中。
6. 如果是 EZARC 日本站，确认是否被按 ASIN 汇总到 `EZARC JP 汇总`。
7. 如果是 `--upload-only`，报表会上传但不会发送钉钉消息。

### 为什么 FBA库存和可售明细不相加

当前报表：

- `FBA库存` 用总量字段。
- SourceList fallback 时，`FBA库存` 用 `type=1 source_list[].quantity`。
- `FBA可售-可售`、`FBA可售-待调仓`、`FBA可售-调仓中` 是明细字段。

所以 `FBA库存` 不一定等于三个明细列相加，尤其存在 `afn_reserved_quantity` 时。

### 为什么 EZARC 日本站两个 MSKU 合成一条

EZARC 日本站按 ASIN 汇总，不按 MSKU 汇总。同 ASIN 的不同 MSKU 算同一个品，报表 `MSKU` 单元格合并展示。
