# Dingtalk FBA Bot

这个项目已经整理成可维护的模块化结构：

- 查询领星补货建议接口
- 按 A/B 级规则筛选提醒项
- 通过钉钉企业应用机器人给固定用户发送提醒
- 生成 Excel 报表并发送到钉钉

## 目录结构

```text
.
├── fba_alert/
│   ├── main.py               # 主流程与命令行入口
│   ├── config.py             # 配置读取
│   ├── lingxing.py           # 领星接口客户端
│   ├── dingtalk.py           # 钉钉发送
│   ├── alerts.py             # 预警规则与消息拼装
│   ├── models.py             # 数据模型
│   └── utils.py              # 通用工具
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，填写钉钉配置：

```bash
cp .env.example .env
```

关键配置：

- `LINGXING_SID_LIST`: 需要查询的店铺 ID 列表
  - 程序会额外通过店铺接口自动补入 `Libraton JP-JP` 和 `Libraton NA-CA` 对应的店铺 ID，用于应用其专属预警规则
- `LINGXING_MODE`: 补货建议模式，默认 `0`
- `LINGXING_LISTING_CONCURRENCY`: Listing 并发数，默认 `2`
- `LINGXING_SOURCE_LIST_CONCURRENCY`: SourceList 初始并发数，默认 `4`；命中领星限流后程序会自动降到更低并发重试
- `LINGXING_SOURCE_LIST_CACHE_ENABLED`: 是否启用 SourceList 本地缓存，默认 `true`
- `LINGXING_SOURCE_LIST_CACHE_DIR`: SourceList 本地缓存目录，默认 `.cache/fba_alert/source_list`
- `DINGTALK_APP_KEY`
- `DINGTALK_APP_SECRET`
- `DINGTALK_ROBOT_CODE`
- `DINGTALK_USER_IDS`: 默认钉钉用户 ID，多个用英文逗号分隔
  - 当前总表固定发送给 `16063564311489688`、`17331048354297047`
  - 各店铺分表统一按店铺收件人规则发送
  - 未配置专属收件人的店铺，分表发送给这里配置的默认收件人
  - 当前 `Libraton EU-DE`、`Libraton EU-UK` 会合并为一个 `Libraton EU` 分表，文件名为 `LIBRATON库存预警-EU-YYYYMMDD.xlsx`，发送给曹书璇 `17496925056054051`、李超逸 `17621342403159969`、施庆雲 `17490880140202841`
  - 其他 `Libraton` 店铺分表文件名会去掉前缀 `Libraton `，例如 `Libraton NA-CA` 对应 `LIBRATON库存预警-NA-CA-YYYYMMDD.xlsx`
- `PIP_INDEX_URL`: Docker 构建主镜像，默认清华源
- `PIP_EXTRA_INDEX_URL`: Docker 构建备用镜像，默认阿里云
- `PIP_FALLBACK_INDEX_URL`: Docker 构建最终回退镜像，默认官方 PyPI

## 运行

先激活你的 conda 环境，再执行：

```bash
python -m fba_alert.main --dry-run
```

`--dry-run` 会在本地生成 Excel 报表，不发送钉钉。

报表默认输出结构：

```text
reports/
└── YYYY-MM-DD/
    ├── LIBRATON库存预警-YYYYMMDD.xlsx
    ├── 店铺A/
    │   └── LIBRATON库存预警-店铺A-YYYYMMDD.xlsx
    └── 店铺B/
        └── LIBRATON库存预警-店铺B-YYYYMMDD.xlsx
```

正式发送：

```bash
python -m fba_alert.main
```

如果你只想跑指定范围，可以加 `--scope`：

```bash
python -m fba_alert.main --dry-run --scope all
python -m fba_alert.main --dry-run --scope us
python -m fba_alert.main --dry-run --scope ca
python -m fba_alert.main --dry-run --scope jp
python -m fba_alert.main --dry-run --scope eu
```

范围说明：

- `all`: 跑全量 Libraton 预警，生成总表，并继续生成命中的店铺分表
- `us`: 只跑 `Libraton NA-US`，只输出美国分表
- `ca`: 只跑 `Libraton NA-CA`，只输出加拿大分表
- `jp`: 只跑 `Libraton JP-JP`，只输出日本分表
- `eu`: 只跑当前支持的欧洲范围，输出合并后的 `Libraton EU` 分表

指定 `us/ca/jp/eu` 时不会生成或发送总表，只处理目标范围。

如果你想本地模拟“服务常驻调度”模式：

```bash
python -m fba_alert.main --schedule
```

## Docker 部署

### 1. 准备配置

在项目根目录创建 `.env`，并填写完整配置。

### 2. 使用 docker compose

默认 `docker-compose.yml` 配的是常驻调度模式，适合服务器直接后台运行：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker logs -f dingtalk-fba-bot
```

手动测试一次 `dry-run`：

```bash
docker exec -it dingtalk-fba-bot python -m fba_alert.main --dry-run
```

手动测试正式发送：

```bash
docker exec -it dingtalk-fba-bot python -m fba_alert.main
```

### 3. 服务器定时执行

如果你已经用 `docker compose up -d --build` 启动了容器，就不需要再额外配宿主机 `cron`，容器会自己按每周一 09:00 执行。

如果你不想让容器常驻，也可以继续使用宿主机 `cron` 定时拉起一次容器：

```cron
0 9 * * 1 cd /path/to/dingtalk-fba-bot && /usr/bin/docker compose run --rm fba-alert python -m fba_alert.main >> logs/fba_alert.log 2>&1
```

如果你不用 `docker compose`，也可以直接写成：

```cron
0 9 * * 1 cd /path/to/dingtalk-fba-bot && /usr/bin/docker run --rm --env-file .env dingtalk-fba-bot:latest python -m fba_alert.main >> logs/fba_alert.log 2>&1
```

## 规则口径

- `可售天数(FBA + 在途)` 使用接口字段 `suggest_info.fba_available_sale_days`
- `可售天数(FBA)` 使用接口字段 `suggest_info.available_sale_days_fba`
- `FBA可售-可售` 使用接口 `/erp/sc/routing/fbaSug/asin/getSourceList` 在 `type=1` 时汇总 `data.source_list[].remark.afn_fulfillable_quantity`
- `FBA可售-待调仓` 使用接口 `/erp/sc/routing/fbaSug/asin/getSourceList` 在 `type=1` 时汇总 `data.source_list[].remark.reserved_fc_transfers`
- `FBA可售-调仓中` 使用接口 `/erp/sc/routing/fbaSug/asin/getSourceList` 在 `type=1` 时汇总 `data.source_list[].remark.reserved_fc_processing`
- `FBA库存` 计算公式：`FBA可售-可售 + FBA可售-待调仓 + FBA可售-调仓中`
- `FBA在途` 使用接口 `/erp/sc/routing/fbaSug/asin/getSourceList` 在 `type=2` 时汇总 `data.source_list[].quantity`
- `断货时间(天数)` 由 `suggest_info.out_stock_date - 今天` 计算
- `日均销量` 使用接口字段 `suggest_info.estimated_sale_avg_quantity`
- `Listing联系人` 通过 Listing 接口查询 `principal_info[].principal_name`
- `Listing联系人` 使用 `sid + asin` 作为关联键，命中多个负责人时去重后拼接展示

## 报表字段

导出的 Excel 报表包含以下主要字段：

- 店铺
- 等级
- MSKU
- Listing联系人
- 命中条数
- 命中规则
- 日均销量
- FBA库存
- 可售天数(FBA)
- FBA在途
- 可售天数(FBA+在途)
- 断货时间
- 断货天数
- FBA可售-可售
- FBA可售-待调仓
- FBA可售-调仓中

A级提醒满足其一：

- `可售天数(FBA) <= 14` 且 `> 0`
- `可售天数(FBA + 在途) <= 60` 且 `> 0`
- `断货时间(天数) <= 50` 且 `> 0`

其中 `Libraton JP-JP` 专属 A 级规则满足其一：

- `可售天数(FBA) <= 14` 且 `> 0`
- `断货时间(天数) <= 40` 且 `> 0`

其中 `Libraton NA-CA` 专属 A 级规则满足其一：

- `可售天数(FBA) <= 14` 且 `> 0`
- `可售天数(FBA + 在途) <= 55` 且 `> 0`
- `断货时间(天数) <= 45` 且 `> 0`

B级提醒满足其一：

- `可售天数(FBA) <= 30` 且 `> 0`
- `可售天数(FBA) = 断货时间(天数)` 且 `<= 60` 且 `> 0`
- `可售天数(FBA + 在途) <= 75` 且 `> 0`

其中 `Libraton JP-JP` 无 B 级提醒规则。

其中 `Libraton NA-CA` 专属 B 级规则满足其一：

- `可售天数(FBA) <= 30` 且 `> 0`
- `可售天数(FBA) = 断货时间(天数)` 且 `<= 60` 且 `> 0`
- `可售天数(FBA + 在途) <= 70` 且 `> 0`

C级提醒满足：

- `FBA库存 = 0` 且 `FBA在途 > 0`

## 定时执行

服务器上建议用 `cron` 每周一 09:00 运行：

```cron
0 9 * * 1 cd /path/to/dingtalk-fba-bot && /path/to/conda/env/bin/python -m fba_alert.main >> logs/fba_alert.log 2>&1
```

如果走 `docker compose up -d --build`，优先使用容器内调度，不需要再叠加宿主机 `cron`。
