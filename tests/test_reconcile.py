import json
from datetime import datetime

import pytest

from app import reconcile
from app.modules.m1_logs.core import run as import_run
from app.modules.m3_events.core import run as dedupe_run
from app.modules.m4_buckets.core import bucket, hour_key, run as bucket_run


def line(rid, status, ts="2026-11-15T01:05:00Z", service="pay"):
    return {"request_id": rid, "timestamp": ts, "service": service, "status": status}


def test_conflict_is_pending_not_error():
    events = [line("a", 200), line("a", 500)]
    out = bucket_run({"events": events})
    assert out["errors"] == 0
    assert out["pending_count"] == 1
    assert out["rows"][0]["pending"] == 1
    assert out["rows"][0]["confirmed"] == 0


def test_confirmed_error_still_counts_at_handover():
    # 两条都失败，结论一致：照常计入已确认错误。
    events = [line("a", 500), line("a", 503)]
    out = bucket_run({"events": events})
    assert out["errors"] == 1
    assert out["pending_count"] == 0
    assert out["rows"][0]["confirmed"] == 1


def test_confirmed_success_not_error():
    events = [line("a", 200), line("a", 204)]
    out = bucket_run({"events": events})
    assert out["errors"] == 0 and out["pending_count"] == 0
    assert out["rows"][0]["count"] == 1


def test_pending_keeps_both_raw_lines():
    events = [line("a", 200), line("a", 500, ts="2026-11-15T01:06:00Z")]
    out = bucket_run({"events": events})
    record = out["pending"][0]
    assert record["request_id"] == "a"
    assert record["line_count"] == 2
    assert [x["status"] for x in record["lines"]] == [200, 500]
    assert record["other"]["status"] == 500
    # 原行逐字保留，不丢记录。
    assert record["lines"][0]["timestamp"].startswith("2026-11-15T01:05")


def test_multi_line_conflict_keeps_all_lines():
    events = [line("a", 200), line("a", 500), line("a", 502)]
    record = bucket_run({"events": events})["pending"][0]
    assert record["line_count"] == 3
    assert len({x["status"] for x in record["lines"]}) == 3


def test_pending_request_still_bucketed_once():
    events = [line("a", 200), line("a", 500)]
    out = bucket_run({"events": events})
    assert out["rows"][0]["count"] == 1
    assert sum(x["count"] for x in out["rows"]) == 1


def test_arrival_order_does_not_change_bucket():
    early_success = [line("a", 200, "2026-11-15T01:05:00Z"), line("a", 500, "2026-11-15T02:05:00Z")]
    late_failure_first = list(reversed(early_success))
    assert bucket(early_success) == bucket(late_failure_first)
    assert bucket(early_success)[0]["hour"] == "2026-11-15T01:00:00Z"


def test_duplicate_identical_lines_not_pending():
    events = [line("a", 500), line("a", 500)]
    out = bucket_run({"events": events})
    assert out["errors"] == 1 and out["pending_count"] == 0


def test_unparseable_status_is_pending():
    events = [line("a", "abc")]
    out = bucket_run({"events": events})
    assert out["errors"] == 0 and out["pending_count"] == 1
    assert out["pending"][0]["reason"] == reconcile.UNPARSEABLE_REASON


def test_unparseable_mixed_is_pending():
    events = [line("a", 500), line("a", "abc")]
    out = bucket_run({"events": events})
    assert out["errors"] == 0 and out["pending_count"] == 1


def test_blank_request_ids_not_merged():
    events = [line("", 200), line("", 500)]
    groups = reconcile.assess(events)
    assert len(groups) == 2
    assert all(g["verdict"] != reconcile.PENDING for g in groups)


def test_import_separates_pending():
    import json as _json
    text = "\n".join([
        _json.dumps(line("a", 200)),
        _json.dumps(line("a", 500)),
        _json.dumps(line("b", 500)),
    ])
    out = import_run({"text": text})
    assert out["pending_count"] == 1
    assert out["confirmed_errors"] == 1
    assert out["pending"][0]["line_count"] == 2


def test_dedupe_uses_same_verdict():
    out = dedupe_run({"events": [line("a", 200), line("a", 500)]})
    assert out["pending_count"] == 1
    assert out["pending"][0]["reason"] == reconcile.OUTCOME_CONFLICT_REASON


def test_pending_reason_codes_registered():
    from app.reasons import reason
    assert reason(reconcile.OUTCOME_CONFLICT_REASON) != "未登记原因"
    assert reason(reconcile.UNPARSEABLE_REASON) != "未登记原因"


def test_accounting_conserves_requests():
    events = [line("a", 200), line("a", 500), line("b", 500), line("c", 200), line("c", 200)]
    out = bucket_run({"events": events})
    assert out["valid_count"] == out["confirmed_requests"] + out["pending_requests"] == 3
    assert out["input_count"] == len(events)
