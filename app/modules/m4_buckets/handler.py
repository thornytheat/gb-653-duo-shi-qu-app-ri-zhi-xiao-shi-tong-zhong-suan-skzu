from fastapi import APIRouter, Body, Request
from .service import execute
router = APIRouter(tags=["M4-小时分桶"])

@router.get("/buckets")
def page(request: Request):
    data = execute(None, store=request.app.state.store)
    return request.app.state.templates.TemplateResponse(request, "m4_buckets.html", {"title": "小时分桶", "data": data})

@router.post("/api/buckets/rebuild")
def api(request: Request, payload: dict = Body(default={})):
    return execute(payload or None, store=request.app.state.store)

@router.get("/api/buckets/pending/{run_id}/{request_id}")
def pending_evidence(run_id: str, request_id: str, request: Request):
    """交班复核：按批次与请求编号查回待核对请求的全部原行。"""
    store = request.app.state.store
    batch = next((b for b in store.batches("buckets") if b["run_id"] == run_id), None)
    if batch is None:
        return {"run_id": run_id, "request_id": request_id, "found": False, "lines": []}
    records = store.pending_by_request("buckets", batch["digest"], request_id)
    # 同编号若被归为多个分组（例如空编号行），全部返回，绝不只给一条。
    lines = [line for record in records for line in record["lines"]]
    return {"run_id": run_id, "request_id": request_id, "found": bool(records),
            "groups": len(records), "lines": lines,
            "records": records}
