import json
import logging
import threading
from pathlib import Path

from app.config import settings
from app.models import NewsArticle

logger = logging.getLogger(__name__)


class JSONStorage:
    """Simple JSON-file based storage for news articles."""

    def __init__(self, file_path: str | None = None) -> None:
        self.file_path = Path(file_path or settings.storage_file)
        self._lock = threading.Lock()
        self._articles: dict[str, NewsArticle] = {}
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            for item in data:
                article = NewsArticle.model_validate(item)
                self._articles[article.id] = article
            logger.info("Loaded %d articles from %s", len(self._articles), self.file_path)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.error("Failed to load storage: %s", exc)

    def _save(self) -> None:
        try:
            data = [a.model_dump(mode="json") for a in self._articles.values()]
            self.file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Failed to save storage: %s", exc)

    def upsert(self, article: NewsArticle) -> NewsArticle:
        with self._lock:
            self._articles[article.id] = article
            self._save()
        return article

    def upsert_many(self, articles: list[NewsArticle]) -> int:
        with self._lock:
            for article in articles:
                self._articles[article.id] = article
            self._save()
        return len(articles)

    def get(self, article_id: str) -> NewsArticle | None:
        return self._articles.get(article_id)

    def list(self, limit: int = 50, offset: int = 0) -> list[NewsArticle]:
        articles = sorted(
            self._articles.values(),
            key=lambda a: a.published or a.id,
            reverse=True,
        )
        return articles[offset : offset + limit]

    def delete(self, article_id: str) -> bool:
        with self._lock:
            if article_id not in self._articles:
                return False
            del self._articles[article_id]
            self._save()
            return True

    def count(self) -> int:
        return len(self._articles)


storage = JSONStorage()