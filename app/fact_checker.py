"""
Модуль для проверки фактов в интернете.
Использует поисковые запросы и сравнение информации из нескольких источников.
"""
import asyncio
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import logging

logger = logging.getLogger(__name__)


class FactChecker:
    """Класс для проверки достоверности информации с использованием интернет-поиска."""

    def __init__(self, timeout: int = 10, max_sources: int = 5):
        self.timeout = timeout
        self.max_sources = max_sources
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    async def search_web(self, query: str) -> List[Dict[str, str]]:
        """Выполняет поиск в интернете и возвращает список результатов."""
        # Используем DuckDuckGo как бесплатный поисковик
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(search_url, headers=self.headers)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                results = []
                for result in soup.select('.result')[:self.max_sources]:
                    title_elem = result.select_one('.result__title')
                    link_elem = result.select_one('.result__url')
                    snippet_elem = result.select_one('.result__snippet')

                    if title_elem and link_elem:
                        title = title_elem.get_text(strip=True)
                        link = link_elem.get_text(strip=True)
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                        results.append({
                            'title': title,
                            'link': link,
                            'snippet': snippet
                        })

                return results
            except Exception as e:
                logger.error(f"Ошибка поиска: {e}")
                return []

    async def fetch_page_content(self, url: str) -> Optional[str]:
        """Загружает содержимое страницы по URL."""
        # Нормализуем URL — добавляем протокол, если его нет
        if url and not url.startswith(('http://', 'https://')):
            url = 'https://' + url.lstrip('/')

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                # Удаляем скрипты и стили
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text(separator=' ', strip=True)
                return text[:5000]  # Ограничиваем размер
            except Exception as e:
                logger.error(f"Ошибка загрузки страницы {url}: {e}")
                return None

    async def verify_claim(self, claim: str, context: str = "") -> Dict[str, Any]:
        """
        Проверяет утверждение, сравнивая с информацией из интернета.

        Args:
            claim: Утверждение для проверки
            context: Дополнительный контекст (например, заголовок новости)

        Returns:
            Dict с результатами проверки
        """
        # Формируем поисковые запросы
        search_queries = [
            claim[:200],  # Основной запрос
            f"{claim[:100]} факт",
            f"{claim[:100]} правда"
        ]

        all_results = []
        for query in search_queries:
            results = await self.search_web(query)
            all_results.extend(results)
            if len(all_results) >= self.max_sources * 2:
                break

        # Уникализация результатов
        seen_links = set()
        unique_results = []
        for r in all_results:
            if r['link'] not in seen_links:
                seen_links.add(r['link'])
                unique_results.append(r)

        # Загружаем содержимое топ-3 страниц
        contents = []
        for result in unique_results[:3]:
            if result['link'] and not result['link'].startswith('/'):
                content = await self.fetch_page_content(result['link'])
                if content:
                    contents.append({
                        'source': result['link'],
                        'title': result['title'],
                        'content': content
                    })

        # Анализируем результаты
        trust_score = self._calculate_trust_score(claim, unique_results, contents)
        is_factual = trust_score >= 0.5
        detected_errors = self._detect_errors(claim, contents)

        return {
            'is_factual': is_factual,
            'trust_score': trust_score,
            'detected_errors': detected_errors,
            'sources': unique_results[:5],
            'full_results': contents
        }

    def _calculate_trust_score(self, claim: str, results: List[Dict], contents: List[Dict]) -> float:
        """Вычисляет оценку доверия на основе найденных источников."""
        if not results:
            return 0.0

        # Чем больше источников, тем выше доверие
        source_score = min(len(results) / 3, 0.4)

        # Проверяем, есть ли в содержании упоминания, подтверждающие утверждение
        confirmation_score = 0.0
        if contents:
            claim_lower = claim.lower()
            for content in contents:
                text = content['content'].lower()
                # Ищем совпадения ключевых слов из утверждения
                words = re.findall(r'\b\w{4,}\b', claim_lower)
                matches = sum(1 for w in words[:10] if w in text)
                if matches > 3:
                    confirmation_score += 0.15
            confirmation_score = min(confirmation_score, 0.4)

        return min(source_score + confirmation_score, 1.0)

    def _detect_errors(self, claim: str, contents: List[Dict]) -> List[str]:
        """Обнаруживает потенциальные ошибки в утверждении."""
        errors = []
        claim_lower = claim.lower()

        # Проверяем наличие противоречий
        if contents:
            for content in contents:
                text = content['content'].lower()
                # Ищем явные противоречия
                negation_patterns = [
                    r'не (соответствует|правда|верно|так)',
                    r'опроверг(ает|нуть)',
                    r'фейк',
                    r'ложь',
                    r'неверно'
                ]
                for pattern in negation_patterns:
                    if re.search(pattern, text):
                        errors.append(f"Найдено противоречие в источнике: {content['source'][:50]}")
                        break

        # Проверка на даты (если есть)
        date_pattern = r'\b(\d{1,2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})\b'
        dates = re.findall(date_pattern, claim_lower)
        if dates and len(dates) > 2:
            errors.append("Обнаружено несколько дат, возможна путаница")

        # Проверка на чрезмерные утверждения
        superlative_patterns = [r'самый', r'лучший', r'первый', r'единственный', r'революционный']
        superlatives = [p for p in superlative_patterns if re.search(p, claim_lower)]
        if len(superlatives) > 2:
            errors.append("Слишком много категоричных утверждений, требуется проверка")

        return errors


# Функция-обёртка для вызова из роутера
async def check_fact(title: str, text: str, context: str = "") -> Dict[str, Any]:
    """
    Основная функция для проверки фактов.

    Args:
        title: Заголовок новости
        text: Текст новости
        context: Дополнительный контекст

    Returns:
        Dict с результатами проверки
    """
    checker = FactChecker()
    claim = f"{title}. {text[:300]}"
    result = await checker.verify_claim(claim, context)

    # Форматируем ответ в нужном формате
    return {
        "is_factual": result['is_factual'],
        "trust_score": result['trust_score'],
        "detected_errors": result['detected_errors'],
        "rewritten_title": title,  # Здесь можно добавить улучшение заголовка
        "rewritten_text": text,    # Здесь можно добавить улучшение текста
        "sources": result['sources'],
        "analysis": f"Найдено {len(result['sources'])} источников. Оценка достоверности: {result['trust_score']:.2f}"
    }
