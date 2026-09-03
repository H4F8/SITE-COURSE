import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx
from dateutil import parser

from app.config import settings
from app.models import NewsArticle

logger = logging.getLogger(__name__)


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse a date string from RSS into a timezone-aware datetime."""
    if not value:
        return None
    try:
        dt = parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, OverflowError):
        logger.debug(f"Failed to parse date: {value}")
        return None


def _make_article_id(link: str, title: str) -> str:
    """Generate a stable unique ID for an article."""
    raw = f"{link}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _clean_text(text: str, limit: int = 500) -> str:
    """Clean and truncate article text."""
    text = " ".join(text.split())
    return text[:limit]


async def fetch_feed(feed_url: str, limit: int | None = None) -> list[NewsArticle]:
    """Fetch and parse a single RSS feed."""
    limit = limit or settings.max_articles_per_feed
    articles: list[NewsArticle] = []

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch feed %s: %s", feed_url, exc)
        return articles

    feed = feedparser.parse(resp.content)
    source = feed.feed.get("title", feed_url)

    for entry in feed.entries[:limit]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        summary = _clean_text(entry.get("summary", "") or entry.get("description", ""))
        published = _parse_date(entry.get("published") or entry.get("pubDate"))

        articles.append(
            NewsArticle(
                id=_make_article_id(link, title),
                title=title,
                link=link,
                summary=summary,
                source=source,
                published=published,
            )
        )

    return articles


async def fetch_feeds(feed_urls: list[str]) -> list[NewsArticle]:
    """Fetch multiple RSS feeds and merge results (deduplicated by ID)."""
    all_articles: dict[str, NewsArticle] = {}

    for url in feed_urls:
        for article in await fetch_feed(url):
            all_articles[article.id] = article

    # Sort by published date, newest first
    return sorted(
        all_articles.values(),
        key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )