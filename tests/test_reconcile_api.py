import json

from app.modules.m1_logs.core import run as import_run
from app.modules.m4_buckets.core import run as bucket_run


def line(rid, status, ts="2026-11-15T01:05:00Z", service="pay"):
    return {"request_id": rid, "timestamp": ts, "service": service, "status": status}


def test_bucket_api_separates_pending(client):
    events = [line("a", 200), line("a", 500), line("b", 500)]
    body = client.post("/api/buckets/rebuild", json={"events": events}).json()
    assert body["errors"] == 1
    assert body["pending_count"] == 1
    assert body["rows"][0]["pending"] == 1
    assert body["rows"][0]["confirmed"] == 1
    assert body["run_id"]


def test_bucket_pending_lookup_returns_both_lines(client):
    events = [line("a", 200), line("a", 500, ts="2026-11-15T01:06:00Z")]
    body = client.post("/api/buckets/rebuild", json={"events": events}).json()
    found = client.get(f"/api/buckets/pending/{body['run_id']}/a").json()
    assert found["found"] is True
    assert [x["status"] for x in found["lines"]] == [200, 500]
    assert found["lines"][0]["timestamp"].startswith("2026-11-15T01:05")


def test_import_pending_lookup_keeps_raw_lines(client):
    text = "\n".join([json.dumps(line("a", 200)), json.dumps(line("a", 500))])
    body = client.post("/api/logs/import", json={"text": text}).json()
    found = client.get(f"/api/logs/pending/{body['run_id']}/a").json()
    assert found["found"] is True
    assert len(found["lines"]) == 2
    assert all(x["raw"] for x in found["lines"])


def test_budget_lookup_unknown_request(client):
    events = [line("a", 200), line("a", 500)]
    body = client.post("/api/buckets/rebuild", json={"events": events}).json()
    found = client.get(f"/api/buckets/pending/{body['run_id']}/zzz").json()
    assert found["found"] is False and found["lines"] == []


def test_import_retry_same_run_id(client):
    text = "\n".join([json.dumps(line("a", 200)), json.dumps(line("a", 500))])
    first = client.post("/api/logs/import", json={"text": text}).json()
    second = client.post("/api/logs/import", json={"text": text}).json()
    assert first["run_id"] == second["run_id"]
    runs = client.get("/api/runs").json()
    imports = [b for b in runs["batches"] if b["kind"] == "import"]
    assert len(imports) == 1


def test_export_csv_has_pending_column_and_total(client):
    events = [line("a", 200), line("a", 500), line("b", 500)]
    client.post("/api/buckets/rebuild", json={"events": events})
    csv_text = client.get("/api/export/buckets.csv").text
    header = csv_text.splitlines()[0]
    assert header.startswith("hour,service,count,errors")
    assert "pending" in header
    rows = dict(zip(header.split(","), csv_text.splitlines()[1].split(",")))
    assert rows["errors"] == "1"
    assert rows["pending"] == "1"


def test_runs_pending_endpoint(client):
    events = [line("a", 200), line("a", 500)]
    body = client.post("/api/buckets/rebuild", json={"events": events}).json()
    found = client.get(f"/api/runs/pending/{body['run_id']}").json()
    assert found["pending"][0]["request_id"] == "a"
    assert len(found["pending"][0]["lines"]) == 2


def test_import_quarantined_line_is_kept(client):
    text = "\n".join([json.dumps(line("a", 500)), '{"request_id":'])
    body = client.post("/api/logs/import", json={"text": text}).json()
    assert body["quarantine_count"] == 1 and body["input_count"] == 2
    # 隔离行同样留档，输入总数可从原始行复核。
    stored = client.app.state.store.lines("import", body["digest"])
    assert len(stored) == 2
    assert any(x.get("quarantine") for x in stored)


def test_anonymous_pending_groups_both_returned(client):
    # 两条空编号行不会被合并成待核对；若确实进入待核对，查回时也不能互相覆盖。
    events = [line("", 200), line("", 500)]
    body = client.post("/api/buckets/rebuild", json={"events": events}).json()
    assert body["pending_count"] == 0


def test_pending_evidence_total_matches_pending_count(client):
    # c 的两条都失败，结论一致，不算待核对。
    events = [line("a", 200), line("a", 500), line("b", 500), line("c", 500), line("c", 503)]
    body = client.post("/api/buckets/rebuild", json={"events": events}).json()
    assert body["pending_count"] == 1
    # b 与 c 都是可确认的错误请求，共 2 条。
    assert body["errors"] == 2
    found = client.get(f"/api/runs/pending/{body['run_id']}").json()
    assert sum(len(p["lines"]) for p in found["pending"]) == 2


def test_bucket_retry_does_not_grow_batch_list(client):
    events = [line("a", 200), line("a", 500)]
    client.post("/api/buckets/rebuild", json={"events": events})
    client.post("/api/buckets/rebuild", json={"events": events})
    batches = [b for b in client.get("/api/runs").json()["batches"] if b["kind"] == "buckets"]
    assert len(batches) == 1
