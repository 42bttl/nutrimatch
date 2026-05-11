from __future__ import annotations

from typing import List

import pandas as pd

from catering.data.allergen_codes import KOREAN_16_ALLERGENS
from catering.schemas import AllergenRow, DailyMenu


class AllergyAgent:
    """Deterministic allergen detection using Korean 16-allergen lookup."""

    def detect(
        self,
        daily_menus: List[DailyMenu],
        menu_df: pd.DataFrame,
    ) -> List[AllergenRow]:
        nutrition_index = menu_df.set_index("menu_id")
        seen_ids: set[str] = set()
        rows: List[AllergenRow] = []

        for day in daily_menus:
            all_slots = [day.breakfast, day.lunch, day.dinner]
            for slot in all_slots:
                all_ids = (
                    [slot.rice_id, slot.soup_id]
                    + slot.main_dish_ids
                    + slot.sub_main_ids
                    + slot.side_dish_ids
                )
                for menu_id in all_ids:
                    if not menu_id or menu_id in seen_ids:
                        continue
                    if menu_id not in nutrition_index.index:
                        continue
                    seen_ids.add(menu_id)
                    row = nutrition_index.loc[menu_id]
                    allergens_raw = str(row.get("allergens", "") or "")
                    if allergens_raw.strip() == "" or allergens_raw == "nan":
                        present = []
                    else:
                        parts = [a.strip() for a in allergens_raw.replace("+", ",").split(",")]
                        present = [a for a in parts if a in KOREAN_16_ALLERGENS]

                    rows.append(
                        AllergenRow(
                            menu_name=str(row["menu_name_ko"]),
                            menu_id=menu_id,
                            allergens_present=present,
                        )
                    )

        rows.sort(key=lambda r: r.menu_name)
        return rows
