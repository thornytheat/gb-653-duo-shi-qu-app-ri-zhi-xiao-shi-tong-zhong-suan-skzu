# 数据字典

| 字段 | 类型 | 可空 | 定义 |
|---|---|---:|---|
| `run_id` | string | 否 | 输入摘要派生的稳定运行编号 |
| `source_line` | integer | 否 | 原文件物理行号 |
| `reason_code` | string | 是 | 隔离或冲突的稳定原因码 |
| `raw_value` | string | 是 | 未归一的原始证据 |
| `normalized_value` | string | 是 | 按项目规则得到的值 |
| `rule_version` | string | 否 | 计算规则版本 |
| `pending` | boolean | 否 | 请求是否待核对；待核对不计入已确认错误 |
| `confirmed` | integer | 否 | 该小时桶内已确认的请求数（含成功与失败） |
| `pending_count` | integer | 否 | 该批次中待核对的请求数 |
| `request_key` | string | 否 | 待核对分组的稳定键，用于查回原行 |

字符串编号逐字保留。金额与计量值用 `Decimal`。时间值带偏移并以 UTC 参与比较。区间统一采用左闭右开。
