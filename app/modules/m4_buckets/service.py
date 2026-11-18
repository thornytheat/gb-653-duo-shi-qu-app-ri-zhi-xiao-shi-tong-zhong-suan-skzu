from . import core

def execute(payload: dict | None = None, store=None) -> dict:
    data = dict(payload or {})
    if store is not None:
        data["store"] = store
    return core.run(data)
