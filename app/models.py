from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    """A single news article."""

    id: str
    title: str
    link: str
    summary: str = ""
    source: str = ""
    published: Optional[datetime] = None
    ai_summary: Optional[str] = None
    ai_keywords: list[str] = Field(default_factory=list)
    ai_category: Optional[str] = None
    # Additional fields for deep analysis
    detailed_analysis: Optional[str] = None
    sentiment: Optional[str] = None
    fact_checks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    trust_score: Optional[float] = None
    is_factual: Optional[bool] = None
    detected_errors: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    # Image
    image_url: Optional[str] = None


class NewsArticleCreate(BaseModel):
    """Payload for adding an article manually."""

    title: str
    link: str
    summary: str = ""
    source: str = ""
    published: Optional[datetime] = None


class NewsArticleUpdate(BaseModel):
    """Payload for updating an article."""

    title: Optional[str] = None
    link: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    published: Optional[datetime] = None


class ParseRequest(BaseModel):
    """Request to parse news from RSS feeds."""

    feeds: list[str] = Field(default_factory=list)
    use_ai: bool = True


class ParseResponse(BaseModel):
    """Result of parsing news from RSS feeds."""

    parsed: int = 0
    articles: list[NewsArticle] = Field(default_factory=list)


class SummarizeRequest(BaseModel):
    """Request to summarize articles with local AI."""

    article_ids: list[str] = Field(default_factory=list)
    language: str = "ru"


class SummarizeResponse(BaseModel):
    """Result of AI summarization."""

    processed: int = 0
    articles: list[NewsArticle] = Field(default_factory=list)


class AIStatus(BaseModel):
    """Status of the local AI connection."""

    provider: str
    model: str
    connected: bool
    message: str = ""