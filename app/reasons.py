REASONS = {
    "BAD_COLUMNS": "字段数量不符", "EMPTY_VALUE": "必要值为空",
    "DUPLICATE_CONFLICT": "同一业务键取值冲突", "TRUNCATED": "尾记录不完整",
    "INVALID_VALUE": "值不符合定义", "STALE_VERSION": "提交版本已过期",
    # 同一请求的多条日志结论不一致，交班前需人工核对，不计入已确认错误。
    "OUTCOME_CONFLICT": "同一请求成功与失败并存，待核对",
    # 状态码缺失或无法解析，无法确认结论，同样计入待核对。
    "UNPARSEABLE": "状态码无法解析，待核对",
}

def reason(code: str) -> str:
    return REASONS.get(code, "未登记原因")
