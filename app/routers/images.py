import httpx
from fastapi import APIRouter, HTTPException, Response
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/proxy")
async def proxy_image(url: str) -> Response:
    """
    Прокси для загрузки изображений из внешних источников (обход CORS).
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(content=resp.content, media_type=content_type)

    except httpx.HTTPError as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        raise HTTPException(status_code=404, detail="Image not found or failed to load")
