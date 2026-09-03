import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.ai_service import ai_service
from app.routers import ai, news, images
from app.scheduler import scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    connected, message = await ai_service.check_connection()
    if connected:
        logging.info("Local AI connected: %s", message)
    else:
        logging.warning("Local AI not available: %s", message)

    # Запускаем фоновый планировщик
    scheduler.start()
    logging.info("Автоматический парсинг новостей запущен (интервал: 20 минут)")

    yield

    # Shutdown
    await scheduler.stop()
    await ai_service.close()


app = FastAPI(
    title="News Parser API",
    description="Бэкенд для парсинга новостей с использованием локальной ИИ-модели",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — разрешаем запросы с любого источника (удобно для разработки)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(news.router)
app.include_router(ai.router)
app.include_router(images.router)

# Раздача статики фронтенда
app.mount("/static", StaticFiles(directory="frontend/SITE-COURSE"), name="static")


@app.get("/", tags=["health"])
async def root() -> FileResponse:
    """Root endpoint serving the frontend."""
    return FileResponse("frontend/SITE-COURSE/index.html")


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}