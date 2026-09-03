import asyncio
import json
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — редактор новостей. Твоя задача — анализировать новостные статьи и выдавать результат строго в формате JSON.

Для каждой статьи верни JSON с полями:
- "summary": краткое изложение статьи на 2-3 предложения
- "keywords": список из 3-5 ключевых слов
- "category": одна категория из списка: Политика, Экономика, Технологии, Спорт, Культура, Наука, Общество, Происшествия, Мир, Другое

Отвечай ТОЛЬКО валидным JSON, без пояснений и markdown-разметки."""

NEWS_ANALYST_PROMPT = """Ты — опытный журналист и редактор. Твоя задача — глубоко анализировать новостные статьи и выдавать результат строго в формате JSON.

Для каждой статьи верни JSON с полями:
- "summary": развернутое изложение статьи на 5-8 предложений. Пиши как полноценный новостной текст: с фактами, контекстом, причинами и последствиями. Используй профессиональный журналистский стиль.
- "keywords": список из 7-10 ключевых слов и фраз, отражающих суть события
- "category": одна категория из списка: Политика, Экономика, Технологии, Спорт, Культура, Наука, Общество, Происшествия, Мир, Другое
- "sentiment": тональность новости (positive, negative, neutral)
- "fact_checks": список из 3-5 фактов из статьи, которые требуют проверки (с формулировкой "[факт] — проверка")
- "recommendations": список из 2-3 рекомендаций по дальнейшему чтению или смежным темам
- "detailed_analysis": развёрнутый анализ новости на 3-5 предложений: почему это важно, какие последствия, что это значит для аудитории

Отвечай ТОЛЬКО валидным JSON, без пояснений и markdown-разметки."""


class AIService:
    """Client for local AI (Ollama or OpenAI-compatible / LM Studio)."""

    def __init__(self) -> None:
        self.provider = settings.ai_provider.lower()
        self.model = settings.ai_model
        self._client = httpx.AsyncClient(timeout=settings.ai_timeout)

    @property
    def is_ollama(self) -> bool:
        return self.provider == "ollama"

    async def close(self) -> None:
        await self._client.aclose()

    async def check_connection(self) -> tuple[bool, str]:
        """Check that the local AI server is reachable."""
        try:
            if self.is_ollama:
                resp = await self._client.get(f"{settings.ollama_base_url}/api/tags")
                if resp.status_code == 200:
                    models = [m.get("name", "") for m in resp.json().get("models", [])]
                    if self.model in models:
                        return True, f"Модель '{self.model}' найдена"
                    return True, f"Сервер доступен, но модель '{self.model}' не найдена. Доступны: {', '.join(models[:5])}"
                return False, f"Ошибка: HTTP {resp.status_code}"
            else:
                resp = await self._client.get(f"{settings.openai_base_url}/models")
                if resp.status_code == 200:
                    return True, "OpenAI-совместимый сервер доступен"
                return False, f"Ошибка: HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            return False, f"Не удалось подключиться: {exc}"

    async def _generate(self, prompt: str, retries: int = 2, use_news_analyst: bool = False) -> Optional[str]:
        """Send a prompt to the local AI and return the raw text response."""
        for attempt in range(retries + 1):
            try:
                if self.is_ollama:
                    payload = {
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": settings.ai_temperature,
                            "num_predict": settings.ai_max_tokens,
                        },
                    }
                    resp = await self._client.post(
                        f"{settings.ollama_base_url}/api/generate", json=payload
                    )
                    resp.raise_for_status()
                    return resp.json().get("response", "")

                # OpenAI-compatible (LM Studio, llama.cpp server, etc.)
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": settings.ai_temperature,
                    "max_tokens": settings.ai_max_tokens,
                }
                resp = await self._client.post(
                    f"{settings.openai_base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
                logger.error("AI request failed (attempt %d/%d): %s", attempt + 1, retries + 1, exc)
                if attempt < retries:
                    await asyncio.sleep(1.0)
        return None

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Extract a JSON object from the model's raw output."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find the first {...} block
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return None

    async def analyze_article(self, title: str, summary: str) -> Optional[dict]:
        """Analyze a single article: summarize, extract keywords, categorize."""
        article_text = f"Заголовок: {title}\n"
        if summary:
            article_text += f"Текст: {summary}\n"
        article_text += "\nВерни JSON с полями summary, keywords, category."

        raw = await self._generate(article_text)
        if not raw:
            return None
        return self._extract_json(raw)

    async def analyze_article_deep(self, title: str, content: str) -> Optional[dict]:
        """
        Глубокий анализ статьи с использованием модели news-analyst.
        Возвращает расширенный JSON с полями: summary, keywords, category, sentiment, fact_checks, recommendations.
        """
        # Формируем промпт с четкой структурой JSON
        article_text = f"""Проанализируй эту новостную статью и верни строго JSON с полями:
- summary (строка, 3-5 предложений)
- keywords (список строк, 5-7 ключевых слов)
- category (строка из списка: Политика, Экономика, Технологии, Спорт, Культура, Наука, Общество, Происшествия, Мир, Другое)
- sentiment (строка: positive, negative, neutral)
- fact_checks (список строк, до 3 фактов для проверки)
- recommendations (список строк, до 2 рекомендаций для дальнейшего чтения)

Заголовок: {title}
Текст: {content}

Ответь ТОЛЬКО валидным JSON, без пояснений и markdown-разметки."""

        # Используем специальный промпт для news-analyst
        raw = await self._generate(article_text, use_news_analyst=True)
        if not raw:
            logger.error("Модель news-analyst не вернула ответ")
            return self._get_fallback_analysis(title, content)

        result = self._extract_json(raw)
        if not result:
            logger.error(f"Не удалось распарсить JSON: {raw[:200]}")
            return self._get_fallback_analysis(title, content)

        # Проверяем, что результат содержит все необходимые поля
        required_fields = ['summary', 'keywords', 'category', 'sentiment', 'fact_checks', 'recommendations']
        if not all(field in result for field in required_fields):
            logger.error(f"Ответ модели не содержит все поля: {result.keys()}")
            return self._get_fallback_analysis(title, content)

        return result

    def _get_fallback_analysis(self, title: str, content: str) -> dict:
        """Возвращает запасной анализ, если модель не ответила корректно."""
        return {
            "summary": f"Статья: {title[:100]}. Не удалось получить полный анализ от ИИ.",
            "keywords": ["новости", "анализ", "информация"],
            "category": "Другое",
            "sentiment": "neutral",
            "fact_checks": ["Проверьте достоверность информации в статье"],
            "recommendations": ["Поищите дополнительные источники по теме"]
        }

    async def analyze_articles_batch(
        self, articles: list[tuple[str, str]]
    ) -> list[Optional[dict]]:
        """Analyze multiple articles. Returns a list of results aligned with input."""
        results: list[Optional[dict]] = []
        for title, summary in articles:
            result = await self.analyze_article(title, summary)
            results.append(result)
        return results


ai_service = AIService()