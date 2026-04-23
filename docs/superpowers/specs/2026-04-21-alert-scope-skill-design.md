# Alert Scope Skill Design

## Goal

让仓库内的 `skills/dingtalk-fba-alert` 能根据用户输入的预警文本，选择运行总表或指定国家/区域分表；当用户指定国家/区域时，Python 主流程只查询对应范围，不再执行全量店铺查询。

## Supported Inputs

- `LIBRATON库存预警`：运行总表模式
- `LIBRATON库存美国预警`：运行美国分表模式
- `LIBRATON库存加拿大预警`：运行加拿大分表模式
- `LIBRATON库存日本预警`：运行日本分表模式
- `LIBRATON库存欧洲预警`：运行欧洲分表模式

第一版只支持以上 5 类固定词，不做模糊匹配，不支持自由组合国家名。

## Architecture

本次改动分两层：

1. Python 主流程新增“预警范围”能力，统一控制查询 SID、报表导出范围和发送范围。
2. `skills/dingtalk-fba-alert` 负责把用户文本映射成范围参数，并调用项目现有执行入口。

这样 skill 层只做意图识别，业务范围裁剪仍由 Python 代码负责，避免 skill 看起来像支持“按国家运行”，实际却仍然跑全量。

## Scope Model

新增统一范围枚举或等价常量，至少支持：

- `all`
- `us`
- `ca`
- `jp`
- `eu`

范围含义如下：

- `all`：现有全量逻辑，输出总表，并继续按店铺规则生成分表
- `us`：只处理 `Libraton NA-US`
- `ca`：只处理 `Libraton NA-CA`
- `jp`：只处理 `Libraton JP-JP`
- `eu`：只处理欧洲范围，并输出 `Libraton EU` 合并分表

## Data Selection Rules

### all

- 保持现有逻辑
- 使用当前 SID 列表解析及自动补店铺规则
- 生成总表和所有命中的店铺分表

### us / ca / jp

- 只查询并处理对应店铺 SID
- 不附带运行其他国家或区域
- 不导出总表
- 只导出对应店铺分表

### eu

- 只查询欧洲范围内需要支持的店铺
- 第一版至少覆盖当前已存在合并规则的 `Libraton EU-DE` 和 `Libraton EU-UK`
- 导出结果为单个 `Libraton EU` 分表
- 不导出总表

如果现有 `LINGXING_SID_LIST` 未包含某个目标范围需要的店铺 SID，则程序应通过店铺映射和既有策略补全，而不是要求用户手工改 `.env`。

## CLI Changes

在 `python -m fba_alert.main` 增加一个可选参数，例如：

- `--scope all`
- `--scope us`
- `--scope ca`
- `--scope jp`
- `--scope eu`

默认值为 `all`，保持现有调用兼容。

`--dry-run`、`--today`、`--env-file`、`--schedule` 的现有行为保持不变。

## Export Behavior

### all

- 返回现有总表路径
- 保持现有总表 + 分表导出结构

### us / ca / jp / eu

- 返回对应目标分表路径
- 不再生成总表
- 不导出无关国家/区域的分表

## Notification Behavior

### all

- 保持当前逻辑：总表发给固定收件人；分表按店铺规则发送

### us / ca / jp / eu

- 只发送对应目标分表
- 不发送总表
- 收件人仍按店铺规则解析

## Skill Behavior

`skills/dingtalk-fba-alert` 第一版增加固定映射：

- `LIBRATON库存预警` -> `--scope all`
- `LIBRATON库存美国预警` -> `--scope us`
- `LIBRATON库存加拿大预警` -> `--scope ca`
- `LIBRATON库存日本预警` -> `--scope jp`
- `LIBRATON库存欧洲预警` -> `--scope eu`

skill 仍默认优先使用 `--dry-run`，除非用户明确要求真实发送。

## Error Handling

- 如果用户输入了未支持的国家词，skill 应明确提示当前只支持 `总表/美国/加拿大/日本/欧洲`
- 如果目标范围无法解析到任何有效店铺 SID，主流程应报错并说明缺少映射
- 如果目标范围存在但没有命中任何预警，保持当前“未命中提醒”的成功退出语义

## Testing

至少补以下测试：

- `--scope all` 保持当前全量行为
- `--scope us/ca/jp` 只查询目标范围 SID，不导出总表
- `--scope eu` 只查询欧洲目标范围，并导出 `Libraton EU` 合并分表
- 非 `all` 范围只发送对应分表，不发送总表
- skill 对 5 类固定输入的映射正确

## Non-Goals

- 不新增新的钉钉机器人命令系统
- 不支持英文别名、模糊国家词、自由文本解析
- 不重构现有店铺规则配置结构
