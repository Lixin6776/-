from fastapi import APIRouter, HTTPException, Request

from app.services.material_analysis import generate_and_publish_material_analysis

router = APIRouter(prefix="/api/material-analyses", tags=["material-analysis"])


@router.get("")
def list_material_analyses(request: Request) -> list[dict]:
    return request.app.state.material_analysis_store.list_analyses()


@router.get("/latest")
def latest_material_analysis(request: Request) -> dict:
    report = request.app.state.material_analysis_store.latest()
    if report is None:
        raise HTTPException(status_code=404, detail="No material analysis available")
    return report


@router.post("/generate")
async def generate_material_analysis(request: Request) -> dict:
    return await generate_and_publish_material_analysis(
        request.app.state.monitor_service,
        lambda: getattr(request.app.state, "latest_plan_snapshot", None),
        request.app.state.material_analysis_store,
        request.app.state.notification_hub,
    )
