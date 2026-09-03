from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging

from app.ai_service import ai_service
from app.config import settings
from app.models import AIStatus
from app.fact_checker import check_fact
from app.scheduler import scheduler
from app.storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


class FactCheckRequest(BaseModel):
    title: str
    text: str
    context: Optional[str] = ""


class FactCheckResponse(BaseModel):
    is_factual: bool
    trust_score: float
    detected_errors: List[str]
    rewritten_title: str
    rewritten_text: str
    sources: List[Dict[str, str]]
    analysis: str


class DeepAnalyzeRequest(BaseModel):
    title: str
    content: str


class DeepAnalyzeResponse(BaseModel):
    summary: str
    keywords: List[str]
    category: str
    sentiment: str
    fact_checks: List[str]
    recommendations: List[str]


@router.get("/status", response_model=AIStatus)
async def ai_status() -> AIStatus:
    """Check the local AI connection and model availability."""
    connected, message = await ai_service.check_connection()
    return AIStatus(
        provider=ai_service.provider,
        model=settings.ai_model,
        connected=connected,
        message=message,
    )


@router.post("/fact-check", response_model=FactCheckResponse)
async def fact_check(request: FactCheckRequest) -> FactCheckResponse:
    """
    Проверяет достоверность новости, используя поиск в интернете.
    Возвращает оценку доверия, найденные ошибки и исправленный текст.
    """
    try:
        context = request.context or ""
        result = await check_fact(request.title, request.text, context)
        return FactCheckResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при проверке фактов: {str(e)}")


@router.post("/deep-analyze", response_model=DeepAnalyzeResponse)
async def deep_analyze(request: DeepAnalyzeRequest) -> DeepAnalyzeResponse:
    """
    Глубокий анализ новости с использованием модели news-analyst через Ollama.
    Возвращает: краткое содержание, ключевые слова, категорию, тональность,
    список фактов для проверки и рекомендации.
    """
    try:
        result = await ai_service.analyze_article_deep(request.title, request.content)
        if not result:
            raise HTTPException(status_code=500, detail="Не удалось получить ответ от модели news-analyst")
        return DeepAnalyzeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при глубоком анализе: {str(e)}")


class SchedulerStatus(BaseModel):
    running: bool
    interval_minutes: int


class TriggerResponse(BaseModel):
    status: str
    message: str
    result: Optional[Dict[str, Any]] = None


@router.get("/scheduler/status", response_model=SchedulerStatus)
async def scheduler_status() -> SchedulerStatus:
    """Возвращает статус фонового планировщика."""
    return SchedulerStatus(
        running=scheduler.is_running,
        interval_minutes=scheduler.interval_minutes
    )


class ReclassifyResponse(BaseModel):
    total: int
    updated: int
    failed: int
    details: List[Dict[str, Any]]


@router.post("/reclassify", response_model=ReclassifyResponse)
async def reclassify_articles() -> ReclassifyResponse:
    """
    Перераспределяет категории для всех существующих новостей с помощью AI.
    Проходит по каждой статье, отправляет её на анализ и обновляет категорию.
    """
    all_articles = storage.list(limit=9999)
    total = len(all_articles)
    updated = 0
    failed = 0
    details = []

    for article in all_articles:
        try:
            # Анализируем статью
            result = await ai_service.analyze_article_deep(article.title, article.summary or "")
            if result and result.get("category"):
                new_category = result["category"]
                # Обновляем категорию
                article.ai_category = new_category
                storage.upsertrt(article)
                updated += 1
                details.append({
                    "id": article.id,
                    "title": article.title[:50] + "..." if len(article.title) > 50 else article.title,
                    "old_category": article.ai_category,
                    "new_category": new_category,
                    "status": "updated"
                })
                logger.info(f"Обновлена категория для статьи {article.id}: {new_category}")
            else:
                failed += 1
                details.append({
                    "id": article.id,
                    "title": article.title[:50] + "..." if len(article.title) > 50 else article.title,
                    "status": "failed",
                    "error": "AI не вернул категорию"
                })
        except Exception as e:
            failed += 1
            details.append({
                "id": article.id,
                "title": article.title[:50] + "..." if len(article.title) > 50 else article.title,
                "status": "failed",
                "error": str(e)
            })
            logger.error(f"Ошибка при обновлении категории для {article.id}: {e}")

    return ReclassifyResponse(
        total=total,
        updated=updated,
        failed=failed,
        details=details
    )


@router.post("/scheduler/trigger", response_model=TriggerResponse)
async def trigger_scheduler() -> TriggerResponse:
    """Принудительно запускает один цикл автоматического анализа."""
    try:
        result = await scheduler.run_once()
        return TriggerResponse(
            status="completed",
            message="Цикл автоматического анализа выполнен",
            result=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при запуске планировщика: {str(e)}")


@router.post("/scheduler/stop", response_model=TriggerResponse)
async def stop_scheduler() -> TriggerResponse:
    """Останавливает фоновый планировщик."""
    if not scheduler.is_running:
        return TriggerResponse(
            status="stopped",
            message="Планировщик уже остановлен"
        )
    await scheduler.stop()
    return TriggerResponse(
        status="stopped",
        message="Планировщик остановлен"
    )


@router.post("/scheduler/start", response_model=TriggerResponse)
async def start_scheduler() -> TriggerResponse:
    """Запускает фоновый планировщик."""
    if scheduler.is_running:
        return TriggerResponse(
            status="running",
            message="Планировщик уже запущен"
        )
    scheduler.start()
    return TriggerResponse(
        status="started",
        message=f"Планировщик запущен с интервалом {scheduler.interval_minutes} минут"
    )