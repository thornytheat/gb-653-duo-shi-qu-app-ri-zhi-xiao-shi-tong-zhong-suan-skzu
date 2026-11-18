import json

import pytest

from app import reconcile
from app.manifest import canonical_digest
from app.modules.m1_logs.core import run as import_run
from app.modules.m4_buckets.core import run as bucket_run
from app.store import Store


def line(rid, status, ts="2026-11-15T01:05:00Z", service="pay"):
    return {"request_id": rid, "timestamp": ts, "service": service, "status": status}


def test_import_retry_is_idempotent(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    text = "\n".join([json.dumps(line("a", 200)), json.dumps(line("a", 500))])
    first = import_run({"text": text, "store": store})
    second = import_run({"text": text, "store": store})
    assert first["run_id"] == second["run_id"]
    assert len(store.batches("import")) == 1
    assert len(store.lines("import", first["digest"])) == 2
    assert len(store.pending("import", first["digest"])) == 1


def test_bucket_retry_does_not_double_count(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    events = [line("a", 200), line("a", 500), line("b", 500)]
    first = bucket_run({"events": events, "store": store})
    second = bucket_run({"events": events, "store": store})
    assert first["run_id"] == second["run_id"]
    assert first["errors"] == second["errors"] == 1
    assert first["pending_count"] == second["pending_count"] == 1
    assert len(store.batches("buckets")) == 1
    assert len(store.pending("buckets", first["digest"])) == 1


def test_bucket_pending_evidence_survives_retry(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    events = [line("a", 200), line("a", 500, ts="2026-11-15T01:06:00Z")]
    out = bucket_run({"events": events, "store": store})
    stored = store.pending("buckets", out["digest"])[0]
    assert stored["line_count"] == 2
    assert [x["status"] for x in stored["lines"]] == [200, 500]
    # 两条原行都从批次原始行表可回溯，不丢失。
    all_lines = store.lines("buckets", out["digest"])
    assert len(all_lines) == 2


def test_failed_batch_leaves_no_partial_rows(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    good = line("a", 200)
    broken_line = line("b", 500) | {"extra": {"not", "serializable"}}
    digest = canonical_digest({"kind": "buckets", "events": [good, "placeholder"]})
    with pytest.raises(TypeError):
        # 第二行序列化失败，事务必须整体回滚，不能留下半条批次。
        store.record_batch("buckets", digest, {"errors": 0}, lines=[good, broken_line])
    assert store.batches("buckets") == []
    assert store.lines("buckets", digest) == []
    assert store.pending("buckets", digest) == []


def test_different_batches_get_different_run_ids(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    one = bucket_run({"events": [line("a", 500)], "store": store})
    two = bucket_run({"events": [line("b", 500)], "store": store})
    assert one["run_id"] != two["run_id"]
    assert len(store.batches("buckets")) == 2
