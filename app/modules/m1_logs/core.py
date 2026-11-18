import json
from app import reconcile
from app.manifest import canonical_digest
SAMPLE={"text":'{"request_id":"9007199254740993","timestamp":"2026-11-15T01:05:00Z","service":"pay","status":200}\n{"request_id":"r2","timestamp":"2026-11-15T09:10:00+08:00","service":"pay","status":500}\n{"request_id":"r3"'}
def parse(text):
    rows=[]; quarantine=[]
    for line_no,line in enumerate(text.splitlines(),1):
        if not line.strip(): continue
        try:
            row=json.loads(line)
            # 字符串编号逐字保留；原行随证据保存，待核对时可直接回看。
            row["request_id"]=str(row.get("request_id","")); row["source_line"]=line_no; row["raw"]=line
            rows.append(row)
        except json.JSONDecodeError: quarantine.append({"source_line":line_no,"reason":"TRUNCATED","raw":line})
    return {"rows":rows,"quarantine":quarantine}
def import_batch(text):
    """解析并裁决一个导入批次；结果与待核对证据共用一次计算，重试结果一致。"""
    out=parse(text)
    # 同一 request_id 的一成一败在此归为待核对，不计入已确认错误。
    check=reconcile.summarize(out["rows"])
    result={"status":"READY","input_count":len(out["rows"])+len(out["quarantine"]),"valid_count":len(out["rows"]),"quarantine_count":len(out["quarantine"]),"first_id":out["rows"][0]["request_id"] if out["rows"] else "","reason":"TRUNCATED" if out["quarantine"] else ("PENDING" if check["pending"] else "OK"),"pending_count":check["pending_requests"],"confirmed_errors":check["confirmed_errors"]}
    digest=canonical_digest({"kind":"import","text":text})
    return digest,out,result,check["pending"]
def run(payload):
    payload=payload or SAMPLE
    text=payload.get("text",SAMPLE["text"])
    digest,out,result,pending=import_batch(text)
    store=payload.get("store")
    if store:
        # 同一批次文本摘要固定，失败重试复用原 run_id，不重复入账。
        # 隔离行也一并留档，保证输入总数可从原始行复核。
        kept=out["rows"]+[{"source_line":q["source_line"],"raw":q["raw"],"request_id":"","status":None,"quarantine":True} for q in out["quarantine"]]
        saved=store.record_batch("import",digest,result,lines=kept,pending=pending)
        return {**saved["result"],"run_id":saved["run_id"],"digest":digest,"pending":store.pending("import",digest)}
    return {**result,"digest":digest,"pending":pending}
