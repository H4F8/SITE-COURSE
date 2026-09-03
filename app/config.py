from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # --- Local AI settings ---
    # Provider: "ollama" (default) or "openai" (LM Studio / any OpenAI-compatible server)
    ai_provider: str = "ollama"
    # Ollama endpoint
    ollama_base_url: str = "http://localhost:11434"
    # OpenAI-compatible endpoint (LM Studio default port is 1234)
    openai_base_url: str = "http://localhost:1234/v1"
    openai_api_key: str = "lm-studio"  # LM Studio doesn't need a real key
    # Model name
    ai_model: str = "llama3.2"
    # Generation parameters
    ai_temperature: float = 0.3
    ai_max_tokens: int = 1024
    ai_timeout: float = 60.0

    # --- News parsing settings ---
    # Default RSS feeds to parse
    default_feeds: list[str] = [
        "https://lenta.ru/rss",
        "https://www.rbc.ru/rss/",
        "https://news.yandex.ru/index.rss",
    ]
    # Max articles to fetch per feed
    max_articles_per_feed: int = 20
    # Max articles to summarize at once
    max_summarize_batch: int = 5

    # --- Storage ---
    storage_file: str = "news_storage.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()