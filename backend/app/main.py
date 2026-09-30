from fastapi import FastAPI

app = FastAPI(title="Qianchuan Local Assistant", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}