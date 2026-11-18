"""请求级核对：把同一 request_id 的多条日志归组，判定是否可确认。

口径：
- 同一 request_id 至少有一条成功（status < 500）与一条失败（status >= 500）
  时，结果互相矛盾，记为 PENDING（待核对），不进入已确认错误数。
- 多条日志结论一致（全成功或全失败）时，可确认；同一请求只计一次。
- 缺少 request_id 的行无法归组，各自独立处理，不合并。
- 状态码无法解析的行不猜测结论：只要有一行无法判定，整组记为待核对，
  原因码单列为 UNPARSEABLE，不与取值冲突混淆。
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone

OUTCOME_CONFLICT_REASON = "OUTCOME_CONFLICT"
UNPARSEABLE_REASON = "UNPARSEABLE"
PENDING = "PENDING"
ERROR = "ERROR"
OK = "OK"
_ANONYMOUS = "__anonymous__"


def is_error(status) -> bool | None:
    """状态码是否算错误；无法判定时返回 None。"""
    if status is None or status == "":
        return None
    try:
        return int(status) >= 500
    except (TypeError, ValueError):
        return None


def request_id_of(line: dict) -> str:
    value = line.get("request_id", "")
    return "" if value is None else str(value)


def group_lines(lines) -> "OrderedDict[str, list]":
    """按 request_id 归组，保留首次出现顺序；空 id 每行自成一组。"""
    groups: OrderedDict[str, list] = OrderedDict()
    for index, line in enumerate(lines):
        rid = request_id_of(line)
        # 空 id 无法证明属于同一请求，绝不合并，避免误判互相矛盾。
        key = rid if rid else f"{_ANONYMOUS}:{index}"
        groups.setdefault(key, []).append(line)
    return groups


def classify(lines) -> str:
    """返回 ERROR / OK / PENDING；任何无法确认的结论都归入 PENDING。"""
    outcomes = {is_error(line.get("status")) for line in lines}
    if None in outcomes:
        return PENDING
    if len(outcomes) == 1:
        return ERROR if outcomes.pop() else OK
    return PENDING


def pending_reason(lines) -> str:
    """待核对的具体原因：状态码无法解析优先于取值冲突。"""
    if any(is_error(line.get("status")) is None for line in lines):
        return UNPARSEABLE_REASON
    return OUTCOME_CONFLICT_REASON


def _timestamp(line):
    value = line.get("timestamp")
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _line_order(line, index: int) -> int:
    source_line = line.get("source_line")
    return source_line if isinstance(source_line, int) else index + 1


def anchor_line(lines):
    """选择进入小时桶的代表行：事件时间最早，其次原文件行号，最后输入顺序。

    不依赖到达顺序，同一批输入无论日志先后都落到同一个小时桶。
    """
    far_future = datetime.max.replace(tzinfo=timezone.utc)

    def sort_key(item):
        index, line = item
        ts = _timestamp(line)
        return (0, ts) if ts is not None else (1, far_future), _line_order(line, index), index

    return min(enumerate(lines), key=sort_key)[1]


def pending_record(request_id: str, lines, key: str | None = None) -> dict:
    """待核对请求的证据：保留全部原始行，绝不丢记录。"""
    evidence = []
    for index, line in enumerate(lines):
        item = dict(line)
        item["source_line"] = _line_order(line, index)
        evidence.append(item)
    # 无业务编号的行用它自己的分组键，保证查回时键唯一、不互相覆盖。
    record_key = key or request_id or f"{_ANONYMOUS}:0"
    return {
        "key": record_key,
        "request_id": request_id,
        "reason": pending_reason(lines),
        "lines": evidence,
        # first/other 兼容既有的冲突证据结构，便于复核页直接展示两条原行。
        "first": evidence[0] if evidence else None,
        "other": evidence[1] if len(evidence) > 1 else None,
        "line_count": len(evidence),
    }


def assess(lines) -> list[dict]:
    """一次归组并裁决，供导入、分桶与对账共用同一口径。"""
    result = []
    for key, group in group_lines(lines).items():
        result.append({
            "key": key,
            "request_id": request_id_of(group[0]),
            "lines": group,
            "verdict": classify(group),
            "anchor": anchor_line(group),
        })
    return result


def summarize(lines) -> dict:
    """按请求归组后给出确认与待核对的汇总。"""
    pending = []
    confirmed_errors = 0
    confirmed_ok = 0
    groups = assess(lines)
    for group in groups:
        verdict = group["verdict"]
        if verdict == ERROR:
            confirmed_errors += 1
        elif verdict == OK:
            confirmed_ok += 1
        else:
            pending.append(pending_record(group["request_id"], group["lines"], group["key"]))
    return {
        "request_count": len(groups),
        "pending_requests": len(pending),
        "pending": pending,
        "confirmed_errors": confirmed_errors,
        "confirmed_ok": confirmed_ok,
    }
