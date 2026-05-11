from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from catering.pipeline import OUTPUT_DIR, CateringPipeline
from catering.schemas import (
    CateringRequest,
    CateringResponse,
    NutritionSummary,
    SHIP_HEADCOUNT,
    SHIP_NAMES_KO,
    CateringPlanResult,
)

router = APIRouter(prefix="/api/catering", tags=["ship-catering"])


def _build_nutrition_summary(plan: CateringPlanResult) -> NutritionSummary:
    nd_list = plan.nutrition_analysis
    if not nd_list:
        return NutritionSummary(
            avg_kcal=0,
            min_kcal=0,
            max_kcal=0,
            protein_compliance_pct=0,
            fiber_compliance_pct=0,
        )
    kcals = [n.total_kcal for n in nd_list]
    protein_ok = sum(1 for n in nd_list if 90 <= n.protein_g <= 120)
    fiber_ok = sum(1 for n in nd_list if n.fiber_g >= 25)
    return NutritionSummary(
        avg_kcal=round(sum(kcals) / len(kcals), 1),
        min_kcal=round(min(kcals), 1),
        max_kcal=round(max(kcals), 1),
        protein_compliance_pct=round(protein_ok / len(nd_list) * 100, 1),
        fiber_compliance_pct=round(fiber_ok / len(nd_list) * 100, 1),
    )


@router.post("/generate", response_model=CateringResponse)
async def generate_catering_plan(req: CateringRequest) -> CateringResponse:
    """
    Runs the full 7-agent pipeline and returns a download URL for the Excel file.
    Pipeline takes ~30-90 seconds (Claude API calls). Runs in a thread pool
    to avoid blocking the FastAPI event loop.
    """
    pipeline = CateringPipeline()
    loop = asyncio.get_event_loop()
    try:
        plan = await loop.run_in_executor(None, pipeline.run, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return CateringResponse(
        request_id=plan.request_id,
        ship=plan.ship,
        ship_name_ko=plan.ship_name_ko,
        headcount=plan.headcount,
        year=plan.year,
        month=plan.month,
        excel_filename=plan.excel_filename,
        download_url=f"/api/catering/download/{plan.excel_filename}",
        nutrition_summary=_build_nutrition_summary(plan),
        generated_at=plan.generated_at.isoformat(),
    )


@router.get("/download/{filename}")
async def download_excel(filename: str) -> FileResponse:
    """Serve the generated Excel file for download."""
    safe_name = os.path.basename(filename)  # prevent path traversal
    path = OUTPUT_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {safe_name}")
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_name,
    )
