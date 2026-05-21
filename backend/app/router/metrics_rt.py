from fastapi import APIRouter

from utils.request_metrics import REQUEST_LATENCY_STORE


router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/latency")
def get_latency_metrics():
    return REQUEST_LATENCY_STORE.summary()


@router.delete("/latency")
def clear_latency_metrics():
    REQUEST_LATENCY_STORE.clear()
    return {"message": "latency metrics cleared"}
