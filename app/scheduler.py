"""
Модуль для автоматического фонового парсинга и анализа новостей.
Запускается каждые 20 минут.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.ai_service import ai_service
from app.config import settings
from app.fact_checker import check_fact
from app.models import NewsArticle
from app.rss_parser import fetch_feeds
from app.storage import storage

logger = logging.getLogger(__name__)


class NewsScheduler:
    """Планировщик для автоматического парсинга и анализа новостей."""

    def __init__(self, interval_minutes: int = 20):
        self.interval_minutes = interval_minutes
        self.interval_seconds = interval_minutes * 60
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def run_once(self) -> dict:
        """
        Выполняет один цикл: парсинг RSS, анализ через ИИ, факт-чекинг,
        сохранение результатов. Также удаляет статьи старше 24 часов.
        """
        start_time = datetime.now(timezone.utc)
        logger.info("Начинаю автоматический парсинг и анализ новостей...")

        result = {
            "started_at": start_time.isoformat(),
            "feeds_count": len(settings.default_feeds),
            "fetched": 0,
            "analyzed": 0,
            "fact_checked": 0,
            "new_articles": 0,
            "errors": 0,
            "cleaned_old": 0,
        }

        try:
            # 0. Удаляем статьи старше 24 часов
            cutoff_time = datetime.now(timezone.utc).replace(tzinfo=timezone.utc) - timedelta(hours=24)
            old_articles = []
            for article in storage.list(limit=1000):
                if article.published and article.published < cutoff_time:
                    old_articles.append(article.id)
            for article_id in old_articles:
                storage.delete(article_id)
                result["cleaned_old"] += 1
            if result["cleaned_old"] > 0:
                logger.info(f"Удалено {result['cleaned_old']} статей старше 24 часов")

            # 1. Парсинг RSS-лент
            articles = await fetch_feeds(settings.default_feeds)
            result["fetched"] = len(articles)

            if not articles:
                logger.info("Нет новых статей для обработки")
                return result

            # 2. Фильтруем только новые статьи (которых нет в хранилище)
            existing_ids = {a.id for a in storage.list(limit=1000)}
            new_articles = [a for a in articles if a.id not in existing_ids]
            result["new_articles"] = len(new_articles)

            if not new_articles:
                logger.info("Все статьи уже есть в хранилище")
                return result

            # 3. Анализ через ИИ (глубокий анализ для каждой новой статьи)
            for article in new_articles[:10]:  # Ограничиваем 10 статей за раз
                try:
                    # Глубокий анализ
                    analysis = await ai_service.analyze_article_deep(
                        article.title,
                        article.summary or ""
                    )
                    if analysis:
                        article.ai_summary = analysis.get("summary")
                        article.ai_keywords = analysis.get("keywords", [])
                        article.ai_category = analysis.get("category")
                        # Сохраняем дополнительные поля
                        article.sentiment = analysis.get("sentiment")
                        article.fact_checks = analysis.get("fact_checks", [])
                        article.recommendations = analysis.get("recommendations", [])
                        result["analyzed"] += 1

                    # 4. Факт-чекинг (для статей с potential фактами)
                    if article.fact_checks or analysis.get("fact_checks"):
                        fact_check_result = await check_fact(
                            article.title,
                            article.summary or "",
                            context=article.source
                        )
                        article.trust_score = fact_check_result.get("trust_score")
                        article.is_factual = fact_check_result.get("is_factual")
                        article.detected_errors = fact_check_result.get("detected_errors", [])
                        article.sources = fact_check_result.get("sources", [])
                        result["fact_checked"] += 1

                    # Сохраняем в хранилище
                    storage.upsert(article)

                except Exception as e:
                    logger.error(f"Ошибка при анализе статьи {article.title}: {e}")
                    result["errors"] += 1
                    # Сохраняем хотя бы базовую информацию
                    storage.upsert(article)

            logger.info(
                "Автоматический анализ завершён: %d новых статей, %d проанализировано, %d проверено фактов, %d удалено старых",
                result["new_articles"],
                result["analyzed"],
                result["fact_checked"],
                result["cleaned_old"]
            )

        except Exception as e:
            logger.error(f"Ошибка в цикле автоматического анализа: {e}")
            result["errors"] += 1

        return result

    async def _run_loop(self):
        """Бесконечный цикл выполнения задач."""
        self._running = True
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Ошибка в цикле планировщика: {e}")

            # Ждём до следующего запуска
            for _ in range(self.interval_seconds):
                if not self._running:
                    break
                await asyncio.sleep(1)

    def start(self):
        """Запускает планировщик в фоновом режиме."""
        if self._task and not self._task.done():
            logger.warning("Планировщик уже запущен")
            return

        logger.info(f"Запуск планировщика с интервалом {self.interval_minutes} минут")
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Останавливает планировщик."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Планировщик остановлен")

    @property
    def is_running(self) -> bool:
        """Возвращает True, если планировщик активен."""
        return self._running and self._task and not self._task.done()


# Глобальный экземпляр планировщика
scheduler = NewsScheduler(interval_minutes=20)
