from __future__ import annotations

from collections import defaultdict
from typing import List

import pandas as pd

from catering.schemas import DailyMenu, ProcurementLine


class ProcurementAgent:
    """Deterministic ingredient procurement calculation."""

    def calculate(
        self,
        daily_menus: List[DailyMenu],
        ingredients_df: pd.DataFrame,
        headcount: int,
    ) -> List[ProcurementLine]:
        # Count occurrences of each menu_id across all days and meals
        occurrence: dict[str, int] = defaultdict(int)

        for day in daily_menus:
            for slot in [day.breakfast, day.lunch, day.dinner]:
                for menu_id in (
                    [slot.rice_id, slot.soup_id]
                    + slot.main_dish_ids
                    + slot.sub_main_ids
                    + slot.side_dish_ids
                ):
                    if menu_id:
                        occurrence[menu_id] += 1

        # Aggregate by ingredient name
        agg: dict[str, dict] = defaultdict(lambda: {
            "total_g": 0.0,
            "unit": "g",
            "unit_price_krw": 0,
            "category": "",
            "haccp_critical": False,
            "per_serving_g": 0.0,
        })

        for menu_id, count in occurrence.items():
            subset = ingredients_df[ingredients_df["menu_id"] == menu_id]
            for _, ing_row in subset.iterrows():
                name = str(ing_row["ingredient_name_ko"])
                per_g = float(ing_row["per_serving_g"])
                total_g = per_g * headcount * count
                agg[name]["total_g"] += total_g
                agg[name]["unit"] = str(ing_row["unit"])
                agg[name]["unit_price_krw"] = int(ing_row["unit_price_krw_per_kg"])
                agg[name]["category"] = str(ing_row["category"])
                agg[name]["haccp_critical"] = str(ing_row.get("haccp_critical", "False")).lower() == "true"
                agg[name]["per_serving_g"] += per_g

        lines: List[ProcurementLine] = []
        for name, vals in agg.items():
            total_g = vals["total_g"]
            total_kg = round(total_g / 1000.0, 2)
            price_per_kg = vals["unit_price_krw"]
            total_cost = int(total_kg * price_per_kg)

            lines.append(
                ProcurementLine(
                    ingredient=name,
                    unit=vals["unit"],
                    per_serving_g=round(vals["per_serving_g"], 1),
                    total_g=round(total_g, 1),
                    total_kg=total_kg,
                    unit_price_krw=price_per_kg,
                    total_cost_krw=total_cost,
                    category=vals["category"],
                    haccp_critical=vals["haccp_critical"],
                )
            )

        # Sort by category then ingredient name
        category_order = ["곡류", "육류", "수산물", "가공육류", "수산가공품", "건어물",
                          "두부류", "유제품", "채소류", "해조류", "건채소류",
                          "발효식품", "조미료", "유지류", "견과류", "과일류", "건과일"]
        lines.sort(key=lambda x: (
            category_order.index(x.category) if x.category in category_order else 99,
            x.ingredient,
        ))
        return lines
