from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.profiles import router as profiles_router
from app.db import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Qianchuan Local Assistant", version="0.1.0", lifespan=lifespan)
app.include_router(profiles_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}