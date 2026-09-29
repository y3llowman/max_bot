import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.main import api_router
from core.config import DEBUG, FRONTEND_DIR, HOST, PORT
from databases import init_db

app = FastAPI(title="MAX Mini App API", debug=DEBUG, docs_url="/docs" if DEBUG else None,
              redoc_url="/redoc" if DEBUG else None, openapi_url="/openapi.json" if DEBUG else None)
app.include_router(api_router)


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
