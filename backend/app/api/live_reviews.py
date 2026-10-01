from fastapi import APIRouter, HTTPException

from app.services.live_review import LiveReviewStore

router = APIRouter(prefix="/api/reviews", tags=["live-reviews"])


@router.get("")
def list_live_reviews() -> list[dict]:
    return LiveReviewStore().list_reviews()


@router.get("/latest")
def latest_live_review() -> dict:
    review = LiveReviewStore().latest()
    if review is None:
        raise HTTPException(status_code=404, detail="No live review available")
    return review
