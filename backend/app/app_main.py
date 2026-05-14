from fastapi import FastAPI
from router import history_rt, ai_serarch_rt, user_rt


app = FastAPI()

app.include_router(user_rt.router)
app.include_router(history_rt.router)
app.include_router(ai_serarch_rt.router)

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
