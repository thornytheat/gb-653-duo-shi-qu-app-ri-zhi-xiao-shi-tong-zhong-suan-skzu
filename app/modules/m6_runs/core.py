import csv, io
from app.manifest import canonical_digest, run_id
SAMPLE={"store":None,"rows":[{"hour":"2026-11-15T01:00:00Z","service":"pay","count":2,"errors":1},{"hour":"2026-11-15T02:00:00Z","service":"pay","count":1,"errors":0}]}
FIELDS=["hour","service","count","errors","confirmed","pending"]
def csv_text(rows):
    out=io.StringIO(); w=csv.DictWriter(out,fieldnames=FIELDS,lineterminator="\n",extrasaction="ignore")
    w.writeheader()
    for row in rows:
        w.writerow({**{k:0 for k in FIELDS},**row})
    return out.getvalue()
def run(payload):
    rows=payload.get("rows",SAMPLE["rows"]); digest=canonical_digest(rows); rid=run_id(rows)
    total=sum(int(x["count"]) for x in rows); pending=sum(int(x.get("pending",0)) for x in rows)
    # 输入 = 已确认 + 待核对；两条日志对不上的请求不混入已确认错误。
    result={"input_count":total,"valid_count":total-pending,"quarantine_count":pending,"confirmed_count":total-pending,"pending_count":pending,"errors":sum(int(x["errors"]) for x in rows)}
    store=payload.get("store")
    if store:
        # 同一输入摘要重跑复用原 run_id，不增加结果行。
        saved=store.record(digest,rid,result); rid=saved["run_id"]; result=saved["result"]
    return {"status":"READY","run_id":rid,"digest":digest,"csv":csv_text(rows),**result,"reason":"PENDING" if pending else "OK"}
