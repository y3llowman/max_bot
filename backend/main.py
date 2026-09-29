import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.main import api_router
from core.config import DEBUG, FRONTEND_DIR, HOST, PORT
from databases import init_db, msp_registry

app = FastAPI(title="Радар обязанностей — API мини-приложения", version="1.0.0", debug=DEBUG, redoc_url=None)
app.include_router(api_router)


@app.on_event("startup")
async def startup() -> None:
    await init_db()
    await msp_registry.ensure_loaded()


@app.get("/health", summary="Проверка живости")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
