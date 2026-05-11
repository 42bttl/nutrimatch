from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from catering.agents.allergy_agent import AllergyAgent
from catering.agents.excel_agent import ExcelAgent
from catering.agents.haccp_agent import HACCPAgent
from catering.agents.menu_planning_agent import MenuPlanningAgent
from catering.agents.nutrition_agent import NutritionAgent
from catering.agents.procurement_agent import ProcurementAgent
from catering.agents.recipe_sop_agent import RecipeSOPAgent
from catering.schemas import (
    CateringPlanResult,
    CateringRequest,
    SHIP_HEADCOUNT,
    SHIP_NAMES_KO,
)

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"
MENU_CSV = DATA_DIR / "menu_db.csv"
INGREDIENTS_CSV = DATA_DIR / "ingredients_db.csv"


def _collect_unique_menu_ids(daily_menus) -> List[str]:
    seen = set()
    result = []
    for day in daily_menus:
        for slot in [day.breakfast, day.lunch, day.dinner]:
            for mid in (
                [slot.rice_id, slot.soup_id]
                + slot.main_dish_ids
                + slot.sub_main_ids
                + slot.side_dish_ids
            ):
                if mid and mid not in seen:
                    seen.add(mid)
                    result.append(mid)
    return result


class CateringPipeline:
    """Orchestrates all 7 agents in sequence."""

    def __init__(self):
        self.menu_agent = MenuPlanningAgent()
        self.nutrition_agent = NutritionAgent()
        self.haccp_agent = HACCPAgent()
        self.allergy_agent = AllergyAgent()
        self.procurement_agent = ProcurementAgent()
        self.recipe_agent = RecipeSOPAgent()
        self.excel_agent = ExcelAgent()

    def run(self, request: CateringRequest) -> CateringPlanResult:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        headcount = SHIP_HEADCOUNT[request.ship]
        ship_name_ko = SHIP_NAMES_KO[request.ship]

        menu_df = pd.read_csv(MENU_CSV)
        ingredients_df = pd.read_csv(INGREDIENTS_CSV)

        # Stage 1 — AI menu selection
        daily_menus = self.menu_agent.plan(
            year=request.year,
            month=request.month,
            menu_df=menu_df,
            num_days=14,
        )

        # Stage 2-5 — Deterministic calculations
        nutrition = self.nutrition_agent.analyze(daily_menus, menu_df)
        haccp_flags = self.haccp_agent.validate(daily_menus, menu_df)
        allergens = self.allergy_agent.detect(daily_menus, menu_df)
        procurement = self.procurement_agent.calculate(daily_menus, ingredients_df, headcount)

        # Stage 6 — AI recipe SOP generation
        unique_ids = _collect_unique_menu_ids(daily_menus)
        recipes = self.recipe_agent.generate(unique_ids, menu_df, haccp_flags)

        plan = CateringPlanResult(
            request_id=request.request_id,
            ship=request.ship.value,
            ship_name_ko=ship_name_ko,
            headcount=headcount,
            year=request.year,
            month=request.month,
            daily_menus=daily_menus,
            nutrition_analysis=nutrition,
            haccp_flags=haccp_flags,
            allergen_table=allergens,
            procurement=procurement,
            recipes=recipes,
            excel_filename="",
            generated_at=datetime.utcnow(),
        )

        # Stage 7 — Excel rendering
        excel_path = self.excel_agent.render(plan, str(OUTPUT_DIR))
        plan.excel_filename = os.path.basename(excel_path)

        return plan
