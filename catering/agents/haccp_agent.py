from __future__ import annotations

import json
from typing import List, Set

import pandas as pd

from catering.agents.base_agent import BaseAgent
from catering.schemas import DailyMenu, HACCPFlag

RAW_MEAT_COOKING_METHODS = {"구이", "조림", "볶음", "전", "튀김", "찜", "튀김+조림"}
SEAFOOD_CATEGORIES_MAIN_INGREDIENT = {"낙지", "오징어", "새우", "고등어", "삼치", "조기", "갈치", "병어", "동태"}


class HACCPAgent(BaseAgent):
    """Rule-based HACCP flagging followed by Claude narrative generation."""

    SYSTEM_PROMPT = """당신은 HACCP 전문가이자 단체급식 위생관리 담당자입니다.
제공된 메뉴 목록에 대해 HACCP 중요관리점(CCP) 및 위생 지침을 한국어로 작성하세요.

각 항목에 대해 다음을 JSON 배열로 응답하세요:
[
  {
    "menu_name": "메뉴명",
    "temperature_note": "온도관리 지침 (예: 중심온도 75℃ 이상 가열, 냉장 5℃ 이하 보관)",
    "handling_instruction": "취급 주의사항 (예: 육류/채소 칼·도마 분리, 교차오염 방지)"
  }
]
반드시 유효한 JSON만 응답하세요."""

    def validate(
        self,
        daily_menus: List[DailyMenu],
        menu_df: pd.DataFrame,
    ) -> List[HACCPFlag]:
        # Stage 1: Deterministic rule-based flagging
        flags_map: dict[str, HACCPFlag] = {}
        nutrition_index = menu_df.set_index("menu_id")

        for day in daily_menus:
            all_slots = [day.breakfast, day.lunch, day.dinner]
            day_main_ingredients: Set[str] = set()

            for slot in all_slots:
                all_ids = (
                    slot.main_dish_ids
                    + slot.sub_main_ids
                    + [slot.soup_id]
                )
                for menu_id in all_ids:
                    if not menu_id or menu_id not in nutrition_index.index:
                        continue
                    row = nutrition_index.loc[menu_id]
                    if str(row.get("haccp_risk", "False")).lower() != "true":
                        continue

                    name = str(row["menu_name_ko"])
                    method = str(row["cooking_method"])
                    ingredient = str(row["main_ingredient"])

                    risk_level = "HIGH" if ingredient in SEAFOOD_CATEGORIES_MAIN_INGREDIENT else "MEDIUM"
                    ccp_required = method in RAW_MEAT_COOKING_METHODS

                    temp_note = self._default_temp_note(method, ingredient)
                    cross_note = self._cross_contamination_note(ingredient, day_main_ingredients)

                    day_main_ingredients.add(ingredient)

                    if name not in flags_map:
                        flags_map[name] = HACCPFlag(
                            menu_name=name,
                            risk_level=risk_level,
                            ccp_required=ccp_required,
                            temperature_note=temp_note,
                            cross_contamination_note=cross_note,
                        )

        if not flags_map:
            return []

        # Stage 2: Claude narrative for CCP instructions
        flags_list = list(flags_map.values())
        enriched = self._enrich_with_claude(flags_list)
        return enriched

    def _default_temp_note(self, method: str, ingredient: str) -> str:
        if ingredient in SEAFOOD_CATEGORIES_MAIN_INGREDIENT:
            return "신선도 확인 후 사용, 중심온도 85℃ 이상 가열, 냉장 0~5℃ 보관"
        if method in {"구이", "전", "튀김"}:
            return "중심온도 75℃ 이상 가열 확인, 배식 전 온도 점검"
        if method in {"조림", "찜"}:
            return "내부온도 75℃ 이상 도달 확인, 60℃ 이상 보온 유지"
        return "적정 가열 후 배식, 보온 60℃ 이상 유지"

    def _cross_contamination_note(self, ingredient: str, existing: Set[str]) -> str:
        is_seafood = ingredient in SEAFOOD_CATEGORIES_MAIN_INGREDIENT
        has_meat = any(
            m in existing
            for m in {"삼겹살", "돼지고기", "쇠고기", "닭고기"}
        )
        has_seafood = any(
            s in existing
            for s in SEAFOOD_CATEGORIES_MAIN_INGREDIENT
        )
        notes = ["육류·채소·해산물 전용 칼·도마 구분 사용"]
        if is_seafood and has_meat:
            notes.append("해산물·육류 동시 조리 시 별도 작업대 사용 필수")
        return "; ".join(notes)

    def _enrich_with_claude(self, flags: List[HACCPFlag]) -> List[HACCPFlag]:
        menu_list = "\n".join(
            f"- {f.menu_name} (위험등급: {f.risk_level}, CCP: {f.ccp_required})"
            for f in flags
        )
        user_prompt = f"다음 메뉴들의 HACCP CCP 지침을 작성하세요:\n{menu_list}"

        try:
            raw = self._call_claude(
                system=self.SYSTEM_PROMPT,
                user=user_prompt,
                max_tokens=2000,
            )
            start = raw.find("[")
            end = raw.rfind("]") + 1
            data = json.loads(raw[start:end]) if start != -1 else []
        except Exception:
            data = []

        enriched_map = {d["menu_name"]: d for d in data if "menu_name" in d}

        for flag in flags:
            enriched = enriched_map.get(flag.menu_name, {})
            if enriched.get("temperature_note"):
                flag.temperature_note = enriched["temperature_note"]
            if enriched.get("handling_instruction"):
                flag.handling_instruction = enriched["handling_instruction"]

        return flags
