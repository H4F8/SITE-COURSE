from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.ai_service import ai_service
from app.config import settings
from app.models import (
    NewsArticle,
    NewsArticleCreate,
    NewsArticleUpdate,
    ParseRequest,
    ParseResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from app.rss_parser import fetch_feeds
from app.storage import storage

router = APIRouter(prefix="/news", tags=["news"])
templates = Jinja2Templates(directory="frontend/SITE-COURSE")


@router.get("", response_model=list[NewsArticle])
async def list_news(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, description="Поиск по заголовку, описанию и ключевым словам"),
) -> list[NewsArticle]:
    """List stored news articles, newest first. Supports search by title, summary, and keywords."""
    articles = storage.list(limit=9999)
    
    if search:
        search_lower = search.lower()
        articles = [
            a for a in articles
            if search_lower in (a.title or "").lower()
            or search_lower in (a.summary or "").lower()
            or search_lower in (a.ai_summary or "").lower()
            or any(search_lower in (kw or "").lower() for kw in (a.ai_keywords or []))
        ]
    
    # Сортировка по дате (новые сверху) и пагинация
    sorted_articles = sorted(articles, key=lambda a: a.published or a.id, reverse=True)
    return sorted_articles[offset:offset + limit]


@router.get("/{article_id}", response_model=NewsArticle)
async def get_news(article_id: str) -> NewsArticle:
    """Get a single article by ID."""
    article = storage.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return article


@router.get("/{article_id}/page", response_class=HTMLResponse)
async def get_news_page(request: Request, article_id: str) -> HTMLResponse:
    """Get a single article as a styled HTML page."""
    article = storage.get(article_id)
    if not article:
        return HTMLResponse(
            content="<h1>404 — Статья не найдена</h1><p><a href='/'>Вернуться на главную</a></p>",
            status_code=404
        )

    # Подготовка данных
    category = article.ai_category or "Другое"
    category_map = {
        "Политика": "politics",
        "Экономика": "economy",
        "Технологии": "tech",
        "Спорт": "sport",
        "Культура": "culture",
        "Наука": "tech",
        "Общество": "society",
        "Происшествия": "society",
        "Мир": "politics",
        "Другое": "economy",
    }
    category_class = category_map.get(category, "economy")

    # Функция для экранирования HTML — определена до использования
    def esc(s):
        if not s:
            return ""
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    sentiment_map = {
        "positive": "Позитивная",
        "negative": "Негативная",
        "neutral": "Нейтральная",
    }
    sentiment_emoji_map = {
        "positive": "📈",
        "negative": "📉",
        "neutral": "➖",
    }
    sentiment_label = sentiment_map.get(article.sentiment, "Неизвестно")
    sentiment_emoji = sentiment_emoji_map.get(article.sentiment, "➖")

    trust_score = None
    trust_score_class = "medium"
    if article.trust_score is not None:
        trust_score = int(round(article.trust_score * 100))
        if trust_score >= 70:
            trust_score_class = "high"
        elif trust_score >= 40:
            trust_score_class = "medium"
        else:
            trust_score_class = "low"

    image_url = None
    if article.image_url:
        image_url = f"/images/proxy?url={article.image_url}"
    
    image_html = ""
    if image_url:
        image_html = f'<img src="{esc(image_url)}" alt="Иллюстрация к новости" class="article-image" onerror="this.style.display=\'none\'">'

    # Определяем списки для отображения
    keywords_list = article.ai_keywords or []
    fact_checks_list = article.fact_checks or []
    recommendations_list = article.recommendations or []

    # Генерируем HTML-блоки
    detailed_analysis_html = ""
    if hasattr(article, 'detailed_analysis') and article.detailed_analysis:
        detailed_analysis_html = f'<div class="article-detailed-analysis"><strong>🔍 Детальный анализ:</strong> {esc(article.detailed_analysis)}</div>'

    keywords_html = ""
    if keywords_list:
        keywords_html = ''.join(f'<span class="keyword">{esc(kw)}</span>' for kw in keywords_list)

    fact_checks_html = ""
    if fact_checks_list:
        fact_checks_html = ''.join(f'<div class="fact-check">{esc(check)}</div>' for check in fact_checks_list)
    else:
        fact_checks_html = '<p style="color: var(--ink-60);">Нет фактов для проверки</p>'

    recommendations_html = ""
    if recommendations_list:
        recommendations_html = ''.join(f'<div class="recommendation">{esc(rec)}</div>' for rec in recommendations_list)
    else:
        recommendations_html = '<p style="color: var(--ink-60);">Нет рекомендаций</p>'

    published_str = article.published.strftime("%d %b %Y, %H:%M") if article.published else "неизвестно"
    fact_checks_list = article.fact_checks or []
    recommendations_list = article.recommendations or []
    sources_count = len(article.sources) if article.sources else 0

    # Функция для экранирования HTML
    def esc(s):
        if not s:
            return ""
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # Формируем HTML-разметку с использованием общего дизайна сайта
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(article.title)} — КУРС.</title>
    <link rel="stylesheet" href="/static/style.css">
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,600;0,9..144,700;0,9..144,900;1,9..144,500;1,9..144,600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* Дополнительные стили для страницы статьи, поверх основного style.css */
        .article-container {{
            max-width: 820px;
            margin: 0 auto;
            padding: 40px 20px;
            line-height: 1.7;
        }}
        .article-title {{
            font-family: var(--serif);
            font-size: 40px;
            font-weight: 700;
            line-height: 1.2;
            margin: 8px 0 16px;
            color: var(--ink);
        }}
        .article-meta {{
            color: var(--ink-60);
            font-size: 14px;
            margin-bottom: 24px;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            font-family: var(--mono);
        }}
        .article-meta span {{ background: var(--ink-08); padding: 4px 12px; border-radius: var(--radius-sm); }}
        .article-image {{
            width: 100%;
            max-height: 440px;
            object-fit: cover;
            border-radius: var(--radius);
            margin: 16px 0 24px;
            background: var(--ink-08);
        }}
        .article-content {{
            font-size: 17px;
            line-height: 1.8;
        }}
        .article-content .summary {{
            background: var(--paper-2);
            border-radius: var(--radius);
            padding: 24px;
            margin: 16px 0 24px;
            border-left: 4px solid var(--tech);
            font-family: var(--serif);
            font-size: 18px;
            color: var(--ink-80);
        }}
        .article-content .summary strong {{ color: var(--ink); }}
        .article-content h3 {{
            font-family: var(--serif);
            font-weight: 600;
            margin: 28px 0 12px;
            color: var(--ink);
        }}
        .keywords {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 16px 0;
        }}
        .keyword {{
            background: var(--paper-2);
            padding: 6px 16px;
            border-radius: 999px;
            font-size: 13px;
            color: var(--ink-80);
            font-family: var(--mono);
        }}
        .fact-check {{
            background: var(--paper-2);
            border-radius: var(--radius-sm);
            padding: 14px 18px;
            margin: 8px 0;
            border-left: 3px solid var(--society);
            font-size: 15px;
        }}
        .recommendation {{
            background: var(--paper-2);
            border-radius: var(--radius-sm);
            padding: 14px 18px;
            margin: 8px 0;
            border-left: 3px solid var(--tech);
            font-size: 15px;
        }}
        .analysis-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin: 20px 0;
        }}
        .analysis-item {{
            background: var(--paper-2);
            border-radius: var(--radius-sm);
            padding: 16px 20px;
        }}
        .analysis-item .label {{
            color: var(--ink-60);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-family: var(--mono);
        }}
        .analysis-item .value {{
            font-weight: 600;
            margin-top: 4px;
            font-size: 15px;
        }}
        .analysis-item .value.sentiment-positive {{ color: var(--economy); }}
        .analysis-item .value.sentiment-negative {{ color: var(--politics); }}
        .analysis-item .value.sentiment-neutral {{ color: var(--ink-60); }}
        .trust-high {{ color: var(--economy); }}
        .trust-medium {{ color: var(--society); }}
        .trust-low {{ color: var(--politics); }}
        .back-link {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: var(--ink-60);
            font-size: 14px;
            font-family: var(--mono);
            margin-bottom: 24px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--ink-15);
            width: 100%;
            transition: color .2s;
        }}
        .back-link:hover {{ color: var(--ink); }}
        .back-link span {{ font-size: 18px; }}
        .article-tag {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-family: var(--mono);
            font-size: 12px;
            font-weight: 500;
            letter-spacing: .02em;
            color: var(--tag-color, var(--ink));
        }}
        .article-tag::before {{
            content: "";
            width: 6px; height: 6px; border-radius: 50%;
            background: var(--tag-color, var(--ink));
            flex: none;
        }}
        .article-tag.economy {{ --tag-color: var(--economy); }}
        .article-tag.politics {{ --tag-color: var(--politics); }}
        .article-tag.tech {{ --tag-color: var(--tech); }}
        .article-tag.society {{ --tag-color: var(--society); }}
        .article-tag.sport {{ --tag-color: var(--sport); }}
        .article-tag.culture {{ --tag-color: var(--culture); }}
        .article-detailed-analysis {{
            background: var(--paper-2);
            border-radius: var(--radius);
            padding: 20px 24px;
            margin: 20px 0;
            border-left: 4px solid var(--economy);
            font-size: 16px;
            line-height: 1.7;
        }}
        .article-detailed-analysis strong {{ color: var(--ink); }}
        @media (max-width: 600px) {{
            .article-title {{ font-size: 28px; }}
            .analysis-grid {{ grid-template-columns: 1fr; }}
            .article-container {{ padding: 20px 16px; }}
        }}
    </style>
</head>
<body>
    <!-- Топбар -->
    <div class="topbar">
        <div class="wrap">
            <div class="clock"><b id="clock">00:00:00</b> МСК</div>
            <div class="ticker"><div class="ticker-track" id="tickerTrack"></div></div>
            <div class="loc">Амстердам, +19°</div>
        </div>
    </div>

    <!-- Шапка -->
    <header class="masthead">
        <div class="wrap">
            <div>
                <div class="wordmark"><a href="/">КУРС<span>.</span></a></div>
                <div class="tagline">события, которые двигают рынок</div>
            </div>
            <div class="masthead-date" id="fullDate">вторник, 1 сентября</div>
        </div>
        <div class="catnav-bar">
            <div class="wrap">
                <nav class="catnav">
                    <a href="/#economy" data-c="economy">Экономика</a>
                    <a href="/#politics" data-c="politics">Политика</a>
                    <a href="/#tech" data-c="tech">Технологии</a>
                    <a href="/#society" data-c="society">Общество</a>
                    <a href="/#sport" data-c="sport">Спорт</a>
                    <a href="/#culture" data-c="culture">Культура</a>
                </nav>
            </div>
        </div>
    </header>

    <!-- Содержание статьи -->
    <div class="article-container">
        <a href="/" class="back-link"><span>←</span> На главную</a>

        <span class="article-tag {category_class}">{category}</span>
        <h1 class="article-title">{esc(article.title)}</h1>

        <div class="article-meta">
            <span>🕒 {published_str}</span>
            <span>📌 {category}</span>
            <span>📊 Доверие: <span class="trust-{trust_score_class}">{trust_score}%</span></span>
            <span>📰 Источников: {sources_count}</span>
        </div>

        {image_html}

        <div class="article-content">
            <div class="summary">
                <strong>📖 Кратко:</strong> {esc(article.summary or 'Нет краткого изложения')}
            </div>

            {detailed_analysis_html}

            <div class="analysis-grid">
                <div class="analysis-item">
                    <div class="label">Тональность</div>
                    <div class="value sentiment-{article.sentiment or 'neutral'}">{sentiment_emoji} {sentiment_label}</div>
                </div>
                <div class="analysis-item">
                    <div class="label">Доверие</div>
                    <div class="value trust-{trust_score_class}">{trust_score}%</div>
                </div>
            </div>

            <h3>🏷️ Ключевые слова</h3>
            <div class="keywords">
                {keywords_html}
            </div>

            <h3>🔍 Факт-чекинг</h3>
            {fact_checks_html}

            <h3>📚 Рекомендации</h3>
            {recommendations_html}

            <p style="color: var(--ink-60); font-size: 14px; margin-top: 32px; border-top: 1px solid var(--ink-15); padding-top: 20px;">
                Источник: {esc(article.source or 'неизвестен')}
            </p>
        </div>
    </div>

    <!-- Подвал (можно добавить позже) -->
    <script>
        // Простая имитация часов для топбара
        function updateClock() {{
            const now = new Date();
            const s = now.toTimeString().split(' ')[0];
            document.getElementById('clock').textContent = s;
        }}
        updateClock();
        setInterval(updateClock, 1000);

        // Дата
        const d = new Date();
        const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
        const days = ['воскресенье','понедельник','вторник','среда','четверг','пятница','суббота'];
        document.getElementById('fullDate').textContent = days[d.getDay()] + ', ' + d.getDate() + ' ' + months[d.getMonth()];
    </script>
</body>
</html>"""

    return HTMLResponse(content=html_content)


@router.post("", response_model=NewsArticle, status_code=201)
async def create_news(article: NewsArticleCreate) -> NewsArticle:
    """Manually add a news article."""
    from app.rss_parser import _make_article_id

    new_article = NewsArticle(
        id=_make_article_id(article.link, article.title),
        title=article.title,
        link=article.link,
        summary=article.summary,
        source=article.source,
        published=article.published,
    )
    return storage.upsert(new_article)


@router.put("/{article_id}", response_model=NewsArticle)
async def update_news(article_id: str, update: NewsArticleUpdate) -> NewsArticle:
    """Update an existing article."""
    article = storage.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")

    data = update.model_dump(exclude_unset=True)
    updated = article.model_copy(update=data)
    return storage.upsert(updated)


@router.delete("/{article_id}", status_code=204)
async def delete_news(article_id: str) -> None:
    """Delete an article."""
    if not storage.delete(article_id):
        raise HTTPException(status_code=404, detail="Статья не найдена")


@router.post("/parse", response_model=ParseResponse)
async def parse_news(request: ParseRequest) -> ParseResponse:
    """Parse news from RSS feeds. Uses default feeds if none provided."""
    feeds = request.feeds or settings.default_feeds
    articles = await fetch_feeds(feeds)

    if request.use_ai and articles:
        for article in articles:
            result = await ai_service.analyze_article(article.title, article.summary)
            if result:
                article.ai_summary = result.get("summary")
                article.ai_keywords = result.get("keywords", [])
                article.ai_category = result.get("category")

    storage.upsert_many(articles)
    return ParseResponse(parsed=len(articles), articles=articles)


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_news(request: SummarizeRequest) -> SummarizeResponse:
    """Summarize stored articles with local AI."""
    if not request.article_ids:
        articles = storage.list(limit=settings.max_summarize_batch)
    else:
        articles = [a for a in (storage.get(i) for i in request.article_ids) if a]

    if not articles:
        return SummarizeResponse(processed=0, articles=[])

    processed = 0
    for article in articles:
        result = await ai_service.analyze_article(article.title, article.summary)
        if result:
            article.ai_summary = result.get("summary")
            article.ai_keywords = result.get("keywords", [])
            article.ai_category = result.get("category")
            storage.upsert(article)
            processed += 1

    return SummarizeResponse(processed=processed, articles=articles)