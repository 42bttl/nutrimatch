from __future__ import annotations

import json
from typing import List

import pandas as pd

from catering.agents.base_agent import BaseAgent
from catering.schemas import HACCPFlag, RecipeSOP

BATCH_SIZE = 10


class RecipeSOPAgent(BaseAgent):
    """Generates Korean cooking SOPs using Claude (batched 10 dishes/call)."""

    SYSTEM_PROMPT = """당신은 한국 산업체 단체급식 전문 조리장입니다.
주어진 메뉴 목록에 대해 대량조리 기준 조리지침서(SOP)를 한국어로 작성하세요.

각 메뉴에 대해 다음 형식의 JSON 배열로 응답하세요:
[
  {
    "menu_id": "메뉴ID",
    "menu_name": "메뉴명",
    "ingredients": ["재료1 (1인 기준량)", "재료2 (1인 기준량)"],
    "steps": [
      "1. 재료 손질: ...",
      "2. 밑간/준비: ...",
      "3. 조리: ...",
      "4. 완성 및 담기: ..."
    ],
    "ccp_checkpoints": ["CCP 1: 중심온도 75℃ 이상 확인", "..."],
    "cooking_time_min": 30,
    "storage_instruction": "보관 방법",
    "allergen_note": "알레르기 유발물질: ..."
  }
]

반드시 유효한 JSON만 응답하세요. 조리 단계는 대량조리(선박 급식 기준) 관점으로 작성하세요."""

    def generate(
        self,
        unique_menu_ids: List[str],
        menu_df: pd.DataFrame,
        haccp_flags: List[HACCPFlag],
    ) -> List[RecipeSOP]:
        nutrition_index = menu_df.set_index("menu_id")
        haccp_map = {f.menu_name: f for f in haccp_flags}

        # Filter to only IDs that exist in the DB and are not rice/kimchi
        valid_ids = [
            mid for mid in unique_menu_ids
            if mid in nutrition_index.index
            and nutrition_index.loc[mid, "category"] not in ("밥", "김치류")
        ]

        recipes: List[RecipeSOP] = []
        for i in range(0, len(valid_ids), BATCH_SIZE):
            batch = valid_ids[i: i + BATCH_SIZE]
            batch_recipes = self._generate_batch(batch, nutrition_index, haccp_map)
            recipes.extend(batch_recipes)

        return recipes

    def _generate_batch(
        self,
        menu_ids: List[str],
        nutrition_index: pd.DataFrame,
        haccp_map: dict[str, HACCPFlag],
    ) -> List[RecipeSOP]:
        menu_descriptions = []
        for mid in menu_ids:
            row = nutrition_index.loc[mid]
            name = str(row["menu_name_ko"])
            method = str(row["cooking_method"])
            ingredient = str(row["main_ingredient"])
            allergens = str(row.get("allergens", "") or "")
            haccp_note = ""
            if name in haccp_map:
                haccp_note = f" (HACCP: {haccp_map[name].temperature_note})"
            menu_descriptions.append(
                f"- {mid}: {name} | 조리법: {method} | 주재료: {ingredient} | 알레르기: {allergens}{haccp_note}"
            )

        user_prompt = (
            "다음 메뉴들의 대량조리 SOP를 작성하세요:\n"
            + "\n".join(menu_descriptions)
        )

        try:
            raw = self._call_claude(
                system=self.SYSTEM_PROMPT,
                user=user_prompt,
                max_tokens=4096,
            )
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start == -1:
                return self._fallback_batch(menu_ids, nutrition_index)
            data = json.loads(raw[start:end])
        except Exception:
            return self._fallback_batch(menu_ids, nutrition_index)

        result: List[RecipeSOP] = []
        parsed_ids = {d.get("menu_id", ""): d for d in data}
        for mid in menu_ids:
            row = nutrition_index.loc[mid]
            name = str(row["menu_name_ko"])
            d = parsed_ids.get(mid) or next(
                (v for v in parsed_ids.values() if v.get("menu_name") == name), {}
            )
            result.append(
                RecipeSOP(
                    menu_id=mid,
                    menu_name=name,
                    serving_count=1,
                    ingredients=d.get("ingredients", [f"{row['main_ingredient']} 적당량"]),
                    steps=d.get("steps", ["1. 재료 손질", "2. 조리", "3. 배식"]),
                    ccp_checkpoints=d.get("ccp_checkpoints", []),
                    cooking_time_min=int(d.get("cooking_time_min", 30)),
                    storage_instruction=d.get("storage_instruction", "즉시 배식 또는 60℃ 이상 보온"),
                    allergen_note=d.get("allergen_note", ""),
                )
            )
        return result

    def _fallback_batch(
        self, menu_ids: List[str], nutrition_index: pd.DataFrame
    ) -> List[RecipeSOP]:
        result = []
        for mid in menu_ids:
            row = nutrition_index.loc[mid]
            result.append(
                RecipeSOP(
                    menu_id=mid,
                    menu_name=str(row["menu_name_ko"]),
                    serving_count=1,
                    ingredients=[f"{row['main_ingredient']} 적당량"],
                    steps=["1. 재료 손질", "2. 조리 준비", "3. 조리", "4. 완성 및 배식"],
                    ccp_checkpoints=["중심온도 75℃ 이상 확인"],
                    cooking_time_min=30,
                    storage_instruction="즉시 배식 또는 60℃ 이상 보온 유지",
                    allergen_note="",
                )
            )
        return result
