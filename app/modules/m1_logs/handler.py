from fastapi import APIRouter, Body, Request
from . import core
from .service import execute
router = APIRouter(tags=["M1-日志采信"])

@router.get("/logs")
def page(request: Request):
    data = execute(None, store=request.app.state.store)
    return request.app.state.templates.TemplateResponse(request, "m1_logs.html", {"title": "日志采信", "data": data})

@router.post("/api/logs/import")
def api(request: Request, payload: dict = Body(default={})):
    return execute(payload or None, store=request.app.state.store)

@router.get("/api/logs/pending/{run_id}/{request_id}")
def pending_evidence(run_id: str, request_id: str, request: Request):
    """按批次与请求编号查回待核对请求的全部原始行。"""
    store = request.app.state.store
    batch = next((b for b in store.batches("import") if b["run_id"] == run_id), None)
    if batch is None:
        return {"run_id": run_id, "request_id": request_id, "found": False, "lines": []}
    records = store.pending_by_request("import", batch["digest"], request_id)
    lines = [line for record in records for line in record["lines"]]
    return {"run_id": run_id, "request_id": request_id, "found": bool(records),
            "groups": len(records), "lines": lines, "records": records}
