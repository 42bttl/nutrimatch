from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ─── Enums ───────────────────────────────────────────────────────────────────

class ShipId(str, Enum):
    nuribaram = "nuribaram"  # 97명
    frontier = "frontier"    # 52명


SHIP_HEADCOUNT = {
    ShipId.nuribaram: 97,
    ShipId.frontier: 52,
}

SHIP_NAMES_KO = {
    ShipId.nuribaram: "누리바람",
    ShipId.frontier: "프론티어",
}


# ─── HTTP Request/Response (Pydantic) ────────────────────────────────────────

class CateringRequest(BaseModel):
    ship: ShipId
    year: int = Field(..., ge=2024, le=2030)
    month: int = Field(..., ge=1, le=12)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class NutritionSummary(BaseModel):
    avg_kcal: float
    min_kcal: float
    max_kcal: float
    target_min_kcal: int = 2700
    target_max_kcal: int = 3200
    protein_compliance_pct: float   # % of days within 90-120g protein
    fiber_compliance_pct: float     # % of days with >=25g fiber


class CateringResponse(BaseModel):
    request_id: str
    ship: str
    ship_name_ko: str
    headcount: int
    year: int
    month: int
    excel_filename: str
    download_url: str
    nutrition_summary: NutritionSummary
    generated_at: str


# ─── Internal pipeline data contracts (dataclasses) ──────────────────────────

@dataclass
class MealSlot:
    rice_id: str
    soup_id: str
    main_dish_ids: List[str]
    sub_main_ids: List[str]
    side_dish_ids: List[str]
    condiments: List[str] = field(default_factory=lambda: ["K001", "고추장", "참기름"])
    extras: List[str] = field(default_factory=list)


@dataclass
class NightSnack:
    items: List[str] = field(
        default_factory=lambda: ["삶은계란", "바나나", "우유 또는 두유"]
    )


@dataclass
class DailyMenu:
    date: date
    breakfast: MealSlot
    lunch: MealSlot
    dinner: MealSlot
    night_snack: NightSnack


@dataclass
class NutritionDay:
    date: date
    breakfast_kcal: float
    lunch_kcal: float
    dinner_kcal: float
    snack_kcal: float
    total_kcal: float
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float
    within_target: bool


@dataclass
class HACCPFlag:
    menu_name: str
    risk_level: str               # HIGH / MEDIUM / LOW
    ccp_required: bool
    temperature_note: str
    cross_contamination_note: str
    handling_instruction: str = ""


@dataclass
class AllergenRow:
    menu_name: str
    menu_id: str
    allergens_present: List[str]


@dataclass
class ProcurementLine:
    ingredient: str
    unit: str
    per_serving_g: float
    total_g: float
    total_kg: float
    unit_price_krw: int
    total_cost_krw: int
    category: str
    haccp_critical: bool


@dataclass
class RecipeSOP:
    menu_id: str
    menu_name: str
    serving_count: int
    ingredients: List[str]
    steps: List[str]
    ccp_checkpoints: List[str]
    cooking_time_min: int = 30
    storage_instruction: str = "즉시 배식 또는 60℃ 이상 보온 유지"
    allergen_note: str = ""


@dataclass
class CateringPlanResult:
    request_id: str
    ship: str
    ship_name_ko: str
    headcount: int
    year: int
    month: int
    daily_menus: List[DailyMenu]
    nutrition_analysis: List[NutritionDay]
    haccp_flags: List[HACCPFlag]
    allergen_table: List[AllergenRow]
    procurement: List[ProcurementLine]
    recipes: List[RecipeSOP]
    excel_filename: str
    generated_at: datetime
