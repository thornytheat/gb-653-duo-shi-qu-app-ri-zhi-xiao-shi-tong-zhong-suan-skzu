from datetime import datetime, timezone
from app import reconcile
from app.manifest import canonical_digest
SAMPLE={"events":[{"timestamp":"2026-11-15T01:00:00Z","service":"pay","status":200},{"timestamp":"2026-11-15T01:59:59Z","service":"pay","status":500},{"timestamp":"2026-11-15T02:00:00Z","service":"pay","status":200}]}
def hour_key(value):
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    # 带偏移的时间先归一到 UTC；无偏移的按 UTC 处理，避免结果随主机时区漂移。
    dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    # 小时桶右端开：把分钟秒清零。
    return dt.strftime("%Y-%m-%dT%H:00:00Z")
def _new_item(hour,service):
    return {"hour":hour,"service":service,"count":0,"errors":0,"confirmed":0,"pending":0}
def _bucket_groups(groups):
    """每个请求只进一个桶；errors 只统计可确认的错误。"""
    out={}
    for group in groups:
        anchor=group["anchor"]; key=(hour_key(anchor["timestamp"]),anchor["service"])
        item=out.setdefault(key,_new_item(*key)); item["count"]+=1
        if group["verdict"]==reconcile.ERROR:
            item["errors"]+=1; item["confirmed"]+=1
        elif group["verdict"]==reconcile.OK:
            item["confirmed"]+=1
        else:
            # 待核对既不算已确认错误，也不算已确认成功，单列一栏。
            item["pending"]+=1
    return sorted(out.values(),key=lambda x:(x["hour"],x["service"]))
def bucket(events):
    return _bucket_groups(reconcile.assess(events))
def build(events):
    """返回小时桶与待核对证据；两侧共用同一次归组裁决。"""
    groups=reconcile.assess(events)
    pending=[reconcile.pending_record(g["request_id"],g["lines"],g["key"]) for g in groups if g["verdict"]==reconcile.PENDING]
    return {"buckets":_bucket_groups(groups),"pending":pending,"requests":len(groups)}
def run(payload):
    payload=payload or {}
    events=payload.get("events",SAMPLE["events"]); out=build(events)
    buckets=out["buckets"]
    result={"status":"READY","input_count":len(events),"valid_count":out["requests"],"confirmed_requests":sum(x["confirmed"] for x in buckets),"quarantine_count":0,"buckets":len(buckets),"errors":sum(x["errors"] for x in buckets),"pending_count":len(out["pending"]),"pending_requests":sum(x["pending"] for x in buckets),"reason":"PENDING" if out["pending"] else "OK","rows":buckets}
    digest=canonical_digest({"kind":"buckets","events":events})
    store=payload.get("store")
    if store:
        # 同一批事件摘要固定：重试复用 run_id，结果与待核对证据不重复入账。
        saved=store.record_batch("buckets",digest,result,lines=events,pending=out["pending"])
        return {**saved["result"],"run_id":saved["run_id"],"digest":digest,"pending":store.pending("buckets",digest)}
    return {**result,"digest":digest,"pending":out["pending"]}
