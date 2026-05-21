from fastapi import FastAPI
from router import history_rt, ai_serarch_rt, metrics_rt, user_rt
from utils.request_metrics import REQUEST_LATENCY_STORE, ResponseTimeMetricsMiddleware


app = FastAPI()
app.add_middleware(ResponseTimeMetricsMiddleware, store=REQUEST_LATENCY_STORE)

app.include_router(user_rt.router)
app.include_router(history_rt.router)
app.include_router(ai_serarch_rt.router)
app.include_router(metrics_rt.router)

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
