from __future__ import annotations

import json
import random
from datetime import date, timedelta
from typing import List

import pandas as pd

from catering.agents.base_agent import BaseAgent
from catering.schemas import DailyMenu, MealSlot, NightSnack


class MenuPlanningAgent(BaseAgent):
    """Uses Claude to select daily menus from the database for a given month."""

    SYSTEM_PROMPT = """당신은 임상영양사이며 선박 급식 전문가입니다.
주어진 메뉴 데이터베이스에서 menu_id를 선택하여 2주 식단을 생성합니다.

규칙:
1. 반드시 메뉴 DB에 있는 menu_id만 사용하세요.
2. 주찬(main_dish_ids)은 14일 내 동일 메뉴 반복 금지.
3. 하루에 튀김(튀김) 조리법은 최대 2가지.
4. 매끼 색감 다양성: 빨강/초록/노랑/흰색/갈색 중 2가지 이상 포함.
5. 선원 선호: 국물류, 육류, 매운맛, 높은 포만감 우선.
6. 반드시 유효한 JSON 배열만 응답하세요. 주석이나 설명 없이.

각 날짜별 구조:
- 조식: rice_id(밥 1개), soup_id(국 1개), main_dish_ids(주찬 1개), sub_main_ids(주부찬 1개), side_dish_ids(부찬 2개)
- 중식: rice_id(밥 1개), soup_id(국 1개), main_dish_ids(주찬 2개), sub_main_ids(주부찬 2개), side_dish_ids(부찬 2개)
- 석식: rice_id(밥 1개), soup_id(국 1개), main_dish_ids(주찬 1개), sub_main_ids(주부찬 2개), side_dish_ids(부찬 2개)

후식/상시 항목은 자동 추가되므로 포함하지 마세요.
"""

    def plan(
        self,
        year: int,
        month: int,
        menu_df: pd.DataFrame,
        num_days: int = 14,
    ) -> List[DailyMenu]:
        menu_catalog = self._build_catalog(menu_df)
        dates = [date(year, month, 1) + timedelta(days=i) for i in range(num_days)]

        user_prompt = f"""메뉴 데이터베이스:
{menu_catalog}

{year}년 {month}월 {num_days}일치 식단을 생성하세요.
시작일: {dates[0].isoformat()}

응답 형식 (JSON 배열):
[
  {{
    "date": "YYYY-MM-DD",
    "breakfast": {{
      "rice_id": "B001",
      "soup_id": "S001",
      "main_dish_ids": ["M001"],
      "sub_main_ids": ["SM001"],
      "side_dish_ids": ["SD001", "SD002"]
    }},
    "lunch": {{
      "rice_id": "B001",
      "soup_id": "S002",
      "main_dish_ids": ["M002", "M003"],
      "sub_main_ids": ["SM002", "SM003"],
      "side_dish_ids": ["SD003", "SD004"]
    }},
    "dinner": {{
      "rice_id": "B001",
      "soup_id": "S003",
      "main_dish_ids": ["M004"],
      "sub_main_ids": ["SM004", "SM005"],
      "side_dish_ids": ["SD005", "SD006"]
    }}
  }},
  ...
]

{num_days}개 날짜 전부 포함하세요."""

        raw = self._call_claude(
            system=self.SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=8000,
        )

        parsed = self._parse_and_validate(raw, menu_df, dates)
        return parsed

    def _build_catalog(self, menu_df: pd.DataFrame) -> str:
        lines = ["menu_id | 메뉴명 | 카테고리 | 식사유형 | 조리법 | 색감"]
        for _, row in menu_df.iterrows():
            lines.append(
                f"{row['menu_id']} | {row['menu_name_ko']} | {row['category']} "
                f"| {row['meal_type']} | {row['cooking_method']} | {row['color_group']}"
            )
        return "\n".join(lines)

    def _parse_and_validate(
        self,
        raw: str,
        menu_df: pd.DataFrame,
        dates: List[date],
    ) -> List[DailyMenu]:
        # Extract JSON from the response
        raw = raw.strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            return self._fallback_plan(menu_df, dates)

        try:
            data = json.loads(raw[start:end])
        except json.JSONDecodeError:
            return self._fallback_plan(menu_df, dates)

        valid_ids = set(menu_df["menu_id"].tolist())
        daily_menus: List[DailyMenu] = []

        for i, item in enumerate(data[: len(dates)]):
            target_date = dates[i]
            breakfast = self._parse_slot(item.get("breakfast", {}), valid_ids, menu_df, "조식")
            lunch = self._parse_slot(item.get("lunch", {}), valid_ids, menu_df, "중식")
            dinner = self._parse_slot(item.get("dinner", {}), valid_ids, menu_df, "석식")
            daily_menus.append(
                DailyMenu(
                    date=target_date,
                    breakfast=breakfast,
                    lunch=lunch,
                    dinner=dinner,
                    night_snack=NightSnack(),
                )
            )

        # Fill any missing days with fallback
        while len(daily_menus) < len(dates):
            i = len(daily_menus)
            daily_menus.append(self._fallback_day(menu_df, dates[i]))

        return daily_menus

    def _parse_slot(
        self,
        slot_data: dict,
        valid_ids: set,
        menu_df: pd.DataFrame,
        meal_type: str,
    ) -> MealSlot:
        def pick(id_val: str, category: str) -> str:
            if id_val in valid_ids:
                return id_val
            return self._random_from_category(menu_df, category)

        def pick_list(ids: list, category: str, count: int) -> List[str]:
            result = [pick(i, category) for i in (ids or [])]
            while len(result) < count:
                result.append(self._random_from_category(menu_df, category))
            return result[:count]

        rice_id = pick(slot_data.get("rice_id", ""), "밥")
        soup_id = pick(slot_data.get("soup_id", ""), "국")

        if meal_type == "중식":
            main_ids = pick_list(slot_data.get("main_dish_ids", []), "주찬", 2)
            sub_ids = pick_list(slot_data.get("sub_main_ids", []), "주부찬", 2)
        else:
            main_ids = pick_list(slot_data.get("main_dish_ids", []), "주찬", 1)
            sub_ids = pick_list(slot_data.get("sub_main_ids", []), "주부찬", 1 if meal_type == "조식" else 2)

        side_ids = pick_list(slot_data.get("side_dish_ids", []), "부찬", 2)

        extras = self._default_extras(meal_type)

        return MealSlot(
            rice_id=rice_id,
            soup_id=soup_id,
            main_dish_ids=main_ids,
            sub_main_ids=sub_ids,
            side_dish_ids=side_ids,
            condiments=["K001", "고추장", "참기름"],
            extras=extras,
        )

    def _default_extras(self, meal_type: str) -> List[str]:
        if meal_type == "조식":
            return ["저지방우유"]
        elif meal_type == "중식":
            return ["제철과일", "당근스틱", "오이스틱", "쌈장", "요거트"]
        else:
            return ["견과류1봉", "매실차"]

    def _random_from_category(self, menu_df: pd.DataFrame, category: str) -> str:
        subset = menu_df[menu_df["category"] == category]
        if subset.empty:
            return ""
        return subset.sample(1)["menu_id"].iloc[0]

    def _fallback_day(self, menu_df: pd.DataFrame, target_date: date) -> DailyMenu:
        def pick(cat: str) -> str:
            return self._random_from_category(menu_df, cat)

        breakfast = MealSlot(
            rice_id=pick("밥"),
            soup_id=pick("국"),
            main_dish_ids=[pick("주찬")],
            sub_main_ids=[pick("주부찬")],
            side_dish_ids=[pick("부찬"), pick("부찬")],
            condiments=["K001", "고추장", "참기름"],
            extras=["저지방우유"],
        )
        lunch = MealSlot(
            rice_id=pick("밥"),
            soup_id=pick("국"),
            main_dish_ids=[pick("주찬"), pick("주찬")],
            sub_main_ids=[pick("주부찬"), pick("주부찬")],
            side_dish_ids=[pick("부찬"), pick("부찬")],
            condiments=["K001", "고추장", "참기름"],
            extras=["제철과일", "당근스틱", "오이스틱", "쌈장", "요거트"],
        )
        dinner = MealSlot(
            rice_id=pick("밥"),
            soup_id=pick("국"),
            main_dish_ids=[pick("주찬")],
            sub_main_ids=[pick("주부찬"), pick("주부찬")],
            side_dish_ids=[pick("부찬"), pick("부찬")],
            condiments=["K001", "고추장", "참기름"],
            extras=["견과류1봉", "매실차"],
        )
        return DailyMenu(
            date=target_date,
            breakfast=breakfast,
            lunch=lunch,
            dinner=dinner,
            night_snack=NightSnack(),
        )

    def _fallback_plan(self, menu_df: pd.DataFrame, dates: List[date]) -> List[DailyMenu]:
        return [self._fallback_day(menu_df, d) for d in dates]
