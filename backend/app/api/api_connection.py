from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/api-connection", tags=["api-connection"])


@router.get("/status")
def api_connection_status() -> dict:
    return {
        "configured": settings.api_configured,
        "provider_preference": (
            "api"
            if settings.api_configured and settings.api_advertiser_id
            else "cdp"
        ),
        "base_url": settings.api_base_url,
        "advertiser_id": settings.api_advertiser_id,
        "token_expires_at": settings.api_token_expires_at,
    }