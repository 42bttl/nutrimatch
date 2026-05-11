from __future__ import annotations

from typing import List

import pandas as pd

from catering.schemas import DailyMenu, NutritionDay

# Fixed-calorie items not in menu_db.csv
FIXED_EXTRAS: dict[str, tuple[float, float, float, float, float]] = {
    # name: (kcal, protein_g, carb_g, fat_g, fiber_g)
    "저지방우유": (130.0, 9.0, 14.0, 2.0, 0.0),
    "요거트": (80.0, 5.0, 12.0, 1.5, 0.0),
    "요구르트": (80.0, 5.0, 12.0, 1.5, 0.0),
    "제철과일": (60.0, 0.5, 15.0, 0.2, 1.5),
    "당근스틱": (15.0, 0.4, 3.5, 0.1, 1.0),
    "오이스틱": (10.0, 0.3, 2.0, 0.1, 0.5),
    "쌈장": (25.0, 1.5, 3.5, 0.8, 0.5),
    "견과류1봉": (180.0, 5.0, 8.0, 15.0, 2.0),
    "매실차": (20.0, 0.0, 5.0, 0.0, 0.0),
    "삶은계란": (70.0, 6.0, 0.5, 5.0, 0.0),
    "바나나": (90.0, 1.1, 23.0, 0.3, 2.6),
    "우유 또는 두유": (130.0, 6.5, 12.0, 4.0, 0.5),
    "고추장": (15.0, 0.8, 3.0, 0.2, 0.3),
    "참기름": (40.0, 0.0, 0.0, 4.5, 0.0),
    "K001": (20.0, 1.5, 3.5, 0.3, 1.5),  # 배추김치
}

NUTRITION_TARGETS = {
    "kcal_min": 2700.0,
    "kcal_max": 3200.0,
    "protein_min": 90.0,
    "protein_max": 120.0,
    "fiber_min": 25.0,
}


class NutritionAgent:
    """Deterministic nutrition calculation from menu CSV data."""

    def analyze(
        self,
        daily_menus: List[DailyMenu],
        menu_df: pd.DataFrame,
    ) -> List[NutritionDay]:
        nutrition_index = menu_df.set_index("menu_id")
        results: List[NutritionDay] = []

        for day in daily_menus:
            bf = self._sum_slot(day.breakfast, nutrition_index)
            lu = self._sum_slot(day.lunch, nutrition_index)
            di = self._sum_slot(day.dinner, nutrition_index)
            sn = self._sum_night_snack()

            total_kcal = bf[0] + lu[0] + di[0] + sn[0]
            total_protein = bf[1] + lu[1] + di[1] + sn[1]
            total_carb = bf[2] + lu[2] + di[2] + sn[2]
            total_fat = bf[3] + lu[3] + di[3] + sn[3]
            total_fiber = bf[4] + lu[4] + di[4] + sn[4]

            within_target = (
                NUTRITION_TARGETS["kcal_min"] <= total_kcal <= NUTRITION_TARGETS["kcal_max"]
                and NUTRITION_TARGETS["protein_min"] <= total_protein <= NUTRITION_TARGETS["protein_max"]
                and total_fiber >= NUTRITION_TARGETS["fiber_min"]
            )

            results.append(
                NutritionDay(
                    date=day.date,
                    breakfast_kcal=round(bf[0], 1),
                    lunch_kcal=round(lu[0], 1),
                    dinner_kcal=round(di[0], 1),
                    snack_kcal=round(sn[0], 1),
                    total_kcal=round(total_kcal, 1),
                    protein_g=round(total_protein, 1),
                    carb_g=round(total_carb, 1),
                    fat_g=round(total_fat, 1),
                    fiber_g=round(total_fiber, 1),
                    within_target=within_target,
                )
            )

        return results

    def _sum_slot(
        self,
        slot,
        nutrition_index: pd.DataFrame,
    ) -> tuple[float, float, float, float, float]:
        """Returns (kcal, protein, carb, fat, fiber) for one meal slot."""
        kcal = prot = carb = fat = fiber = 0.0

        all_ids = (
            [slot.rice_id, slot.soup_id]
            + slot.main_dish_ids
            + slot.sub_main_ids
            + slot.side_dish_ids
            + slot.condiments
            + slot.extras
        )

        for menu_id in all_ids:
            if not menu_id:
                continue
            if menu_id in nutrition_index.index:
                row = nutrition_index.loc[menu_id]
                kcal += float(row["calories_kcal"])
                prot += float(row["protein_g"])
                carb += float(row["carb_g"])
                fat += float(row["fat_g"])
                fiber += float(row["fiber_g"])
            elif menu_id in FIXED_EXTRAS:
                vals = FIXED_EXTRAS[menu_id]
                kcal += vals[0]
                prot += vals[1]
                carb += vals[2]
                fat += vals[3]
                fiber += vals[4]

        return kcal, prot, carb, fat, fiber

    def _sum_night_snack(self) -> tuple[float, float, float, float, float]:
        kcal = prot = carb = fat = fiber = 0.0
        for item in ["삶은계란", "바나나", "우유 또는 두유"]:
            if item in FIXED_EXTRAS:
                v = FIXED_EXTRAS[item]
                kcal += v[0]; prot += v[1]; carb += v[2]; fat += v[3]; fiber += v[4]
        return kcal, prot, carb, fat, fiber
