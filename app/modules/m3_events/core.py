from app import reconcile
SAMPLE={"events":[{"request_id":"r1","status":200,"timestamp":"2026-11-15T01:00:00Z"},{"request_id":"r1","status":200,"timestamp":"2026-11-15T01:00:00Z"},{"request_id":"r2","status":500,"timestamp":"2026-11-15T01:01:00Z"},{"request_id":"r2","status":200,"timestamp":"2026-11-15T01:02:00Z"}]}
def dedupe(events):
    seen={}; duplicate=[]; conflict=[]
    for row in events:
        key=str(row["request_id"])
        if key not in seen: seen[key]=row; continue
        if seen[key]==row: duplicate.append(row)
        else: conflict.append({"request_id":key,"first":seen[key],"other":row,"reason":reconcile.OUTCOME_CONFLICT_REASON})
    return {"accepted":list(seen.values()),"duplicate":duplicate,"conflict":conflict}
def run(payload):
    events=payload.get("events",SAMPLE["events"]); out=dedupe(events)
    # 与分桶共用同一判定：一成一败的请求是待核对，不当作已确认冲突入错误数。
    check=reconcile.summarize(events)
    return {"status":"READY","input_count":len(events),"valid_count":len(out["accepted"]),"quarantine_count":len(out["conflict"]),"duplicates":len(out["duplicate"]),"pending_count":check["pending_requests"],"pending":check["pending"],"reason":"CONFLICT" if out["conflict"] else "OK"}
