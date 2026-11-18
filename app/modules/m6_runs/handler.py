from fastapi import APIRouter, Request
from fastapi.responses import Response
from . import core
from .service import execute
router = APIRouter(tags=["M6-批次对账"])

def _batches(store):
    return [{"kind": b["kind"], "run_id": b["run_id"], "digest": b["digest"],
             "pending_count": b["result"].get("pending_count", 0),
             "errors": b["result"].get("errors", 0)}
            for b in store.batches()]

def _latest_bucket_rows(store):
    """交班导出取最近一次分桶批次；没有分桶时才退回样例。"""
    batches = store.batches("buckets")
    if not batches:
        return None, None
    latest = batches[-1]
    return latest["result"].get("rows", []), latest

@router.get("/runs")
def page(request: Request):
    store = request.app.state.store
    data = execute({"store": store}, store=store)
    return request.app.state.templates.TemplateResponse(
        request, "m6_runs.html",
        {"title": "批次对账", "data": data, "batches": _batches(store)})

@router.get("/api/runs")
def runs(request: Request):
    store = request.app.state.store
    execute({"store": store}, store=store)
    return {"runs": store.all(), "batches": _batches(store)}

@router.get("/api/export/buckets.csv")
def export(request: Request):
    store = request.app.state.store
    rows, _ = _latest_bucket_rows(store)
    if rows is None:
        data = execute({"store": store}, store=store)
        return Response(data["csv"], media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=evidence.csv"})
    text = core.csv_text(rows)
    return Response(text, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=evidence.csv"})

@router.get("/api/runs/pending/{run_id}")
def pending_evidence(run_id: str, request: Request):
    """按批次查回全部待核对请求及其原行。"""
    store = request.app.state.store
    for kind in ("buckets", "import"):
        batch = next((b for b in store.batches(kind) if b["run_id"] == run_id), None)
        if batch is not None:
            return {"run_id": run_id, "kind": kind,
                    "pending": store.pending(kind, batch["digest"])}
    return {"run_id": run_id, "pending": []}
