"""
Excel 출력 테스트 스크립트 (Claude API 없이 실행 가능)
Usage: python test_excel.py
출력: catering/output/nuribaram_202606.xlsx
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, datetime
import pandas as pd

from catering.agents.menu_planning_agent import MenuPlanningAgent
from catering.agents.nutrition_agent import NutritionAgent
from catering.agents.allergy_agent import AllergyAgent
from catering.agents.procurement_agent import ProcurementAgent
from catering.agents.excel_agent import ExcelAgent
from catering.schemas import (
    CateringPlanResult, HACCPFlag, RecipeSOP
)

# ─── 설정 ────────────────────────────────────────────────────────────────────
SHIP       = "nuribaram"
SHIP_KO    = "누리바람"
HEADCOUNT  = 97
YEAR       = 2026
MONTH      = 6
NUM_DAYS   = 14
OUTPUT_DIR = "catering/output"

# ─── 데이터 로드 ─────────────────────────────────────────────────────────────
print("📂 데이터 로드 중...")
menu_df = pd.read_csv("catering/data/menu_db.csv")
ing_df  = pd.read_csv("catering/data/ingredients_db.csv")
print(f"   메뉴 DB: {len(menu_df)}개 메뉴")
print(f"   식재료 DB: {len(ing_df)}개 식재료")

# ─── Stage 1: 메뉴 계획 (규칙 기반 fallback, Claude 없이) ────────────────────
print("\n🍚 14일 식단 생성 중 (규칙 기반)...")
dates = [date(YEAR, MONTH, d + 1) for d in range(NUM_DAYS)]
planner = MenuPlanningAgent()
daily_menus = planner._fallback_plan(menu_df, dates)
print(f"   생성 완료: {len(daily_menus)}일치 식단")

# ─── Stage 2: 영양 분석 ──────────────────────────────────────────────────────
print("\n📊 영양 분석 중...")
nutr = NutritionAgent().analyze(daily_menus, menu_df)
avg_kcal   = sum(n.total_kcal for n in nutr) / len(nutr)
avg_prot   = sum(n.protein_g for n in nutr) / len(nutr)
avg_fiber  = sum(n.fiber_g for n in nutr) / len(nutr)
target_ok  = sum(1 for n in nutr if n.within_target)
print(f"   평균 열량: {avg_kcal:.0f} kcal  (목표 2700~3200)")
print(f"   평균 단백질: {avg_prot:.1f} g   (목표 90~120)")
print(f"   평균 식이섬유: {avg_fiber:.1f} g (목표 25 이상)")
print(f"   목표 충족일: {target_ok}/{NUM_DAYS}일")

# ─── Stage 3: HACCP (샘플 데이터) ────────────────────────────────────────────
print("\n⚠️  HACCP 플래그 생성 중 (샘플)...")
haccp_flags = [
    HACCPFlag(
        menu_name="삼겹살구이",
        risk_level="HIGH",
        ccp_required=True,
        temperature_note="중심온도 75℃ 이상 가열 확인, 배식 전 온도 점검",
        cross_contamination_note="육류·채소 전용 칼·도마 구분 사용",
        handling_instruction="구이 후 즉시 배식, 60℃ 이상 보온 유지"
    ),
    HACCPFlag(
        menu_name="고등어구이",
        risk_level="HIGH",
        ccp_required=True,
        temperature_note="신선도 확인 후 사용, 중심온도 85℃ 이상 가열, 냉장 0~5℃ 보관",
        cross_contamination_note="해산물·육류 동시 조리 시 별도 작업대 사용 필수",
        handling_instruction="구이 후 즉시 배식, 실온 방치 금지"
    ),
    HACCPFlag(
        menu_name="낙지볶음",
        risk_level="HIGH",
        ccp_required=True,
        temperature_note="생물 낙지 냉장 0℃ 보관, 조리 중심온도 85℃ 이상",
        cross_contamination_note="육류·채소·해산물 전용 칼·도마 구분 사용",
        handling_instruction="조리 후 30분 이내 배식"
    ),
]
print(f"   HACCP 플래그: {len(haccp_flags)}개")

# ─── Stage 4: 알레르기 탐지 ──────────────────────────────────────────────────
print("\n🔍 알레르기 분석 중...")
allergens = AllergyAgent().detect(daily_menus, menu_df)
with_allergen = sum(1 for a in allergens if a.allergens_present)
print(f"   분석 메뉴: {len(allergens)}개 (알레르기 포함: {with_allergen}개)")

# ─── Stage 5: 발주량 계산 ────────────────────────────────────────────────────
print("\n📦 발주량 계산 중...")
procurement = ProcurementAgent().calculate(daily_menus, ing_df, HEADCOUNT)
total_cost = sum(p.total_cost_krw for p in procurement)
print(f"   발주 품목: {len(procurement)}개")
print(f"   총 발주 금액: ₩{total_cost:,}")
# 상위 5개 고가 식재료
top5 = sorted(procurement, key=lambda p: p.total_cost_krw, reverse=True)[:5]
print("   비용 상위 5개:")
for p in top5:
    print(f"     {p.ingredient}: {p.total_kg}kg → ₩{p.total_cost_krw:,}")

# ─── Stage 6: 조리지침서 (샘플 데이터) ───────────────────────────────────────
print("\n📋 조리지침서 샘플 생성 중...")
recipes = [
    RecipeSOP(
        menu_id="M006",
        menu_name="제육볶음",
        serving_count=HEADCOUNT,
        ingredients=[
            "돼지고기(앞다리) 120g/인 × 97명 = 11.64kg",
            "고추장 25g/인, 간장 15g/인, 설탕 10g/인",
            "양파 30g/인, 대파 10g/인, 참기름 5g/인",
            "마늘(다진것) 5g/인, 생강 2g/인"
        ],
        steps=[
            "1. [재료 손질] 돼지고기는 핏물 제거 후 5cm 크기로 썰기. 채소류 세척 및 어슷썰기.",
            "2. [밑간] 돼지고기에 고추장, 간장, 설탕, 마늘, 생강 혼합 후 30분 이상 재우기.",
            "3. [볶음] 대형 팬 고온(250℃ 이상) 예열 후 식용유 투입. 밑간한 고기 투입 후 센 불에서 볶기.",
            "4. [채소 투입] 고기가 70% 익으면 양파, 대파 투입. 5분 추가 볶음.",
            "5. [완성] 참기름으로 마무리. 중심온도 75℃ 이상 확인 후 배식 용기에 담기.",
            "6. [배식] 60℃ 이상 보온 용기에 담아 즉시 배식."
        ],
        ccp_checkpoints=[
            "CCP 1: 재우기 온도 — 냉장 5℃ 이하에서 30분 이상 재우기 (실온 방치 금지)",
            "CCP 2: 가열 온도 — 중심온도 75℃ 이상 달성 확인 (온도계 필수)",
            "CCP 3: 배식 온도 — 배식 시점 60℃ 이상 유지"
        ],
        cooking_time_min=40,
        storage_instruction="조리 후 즉시 배식. 보온 필요 시 60℃ 이상 유지. 잔식 2시간 이내 폐기.",
        allergen_note="알레르기 유발물질: ⑩돼지고기 ⑤대두(간장) ⑥밀(간장)"
    ),
    RecipeSOP(
        menu_id="M008",
        menu_name="고등어구이",
        serving_count=HEADCOUNT,
        ingredients=[
            "고등어 150g/인 × 97명 = 14.55kg (손질 후)",
            "소금 3g/인, 식용유 5g/인"
        ],
        steps=[
            "1. [재료 확인] 고등어 신선도 확인 (눈 맑음, 아가미 선홍색, 비늘 밀착). 냉장 0~5℃ 보관 확인.",
            "2. [손질] 고등어 머리 제거, 내장 제거 후 깨끗이 세척. 칼집 2~3회 넣기.",
            "3. [밑간] 소금 양면 골고루 뿌리기. 10~15분 치기.",
            "4. [구이] 석쇠 또는 오븐(230℃) 예열. 고등어 투입 후 한 면 6~8분 구이. 뒤집어 5~6분 추가 구이.",
            "5. [온도 확인] 중심부 온도계 삽입 — 85℃ 이상 확인 필수.",
            "6. [배식] 배식 용기에 담아 즉시 배식."
        ],
        ccp_checkpoints=[
            "CCP 1: 보관 온도 — 조리 전까지 냉장 0~5℃ 유지 (실온 2시간 이상 방치 금지)",
            "CCP 2: 가열 온도 — 중심온도 85℃ 이상 (어류 기준 강화 적용)",
            "CCP 3: 교차오염 방지 — 어류 전용 도마·칼 사용, 육류와 완전 분리"
        ],
        cooking_time_min=25,
        storage_instruction="구이 후 30분 이내 배식. 잔식 즉시 폐기 (재가열 금지).",
        allergen_note="알레르기 유발물질: ⑦고등어"
    ),
]
print(f"   조리지침서: {len(recipes)}개 (샘플)")

# ─── Stage 7: Excel 출력 ─────────────────────────────────────────────────────
print("\n📊 Excel 파일 생성 중...")
plan = CateringPlanResult(
    request_id="test-dummy-001",
    ship=SHIP,
    ship_name_ko=SHIP_KO,
    headcount=HEADCOUNT,
    year=YEAR,
    month=MONTH,
    daily_menus=daily_menus,
    nutrition_analysis=nutr,
    haccp_flags=haccp_flags,
    allergen_table=allergens,
    procurement=procurement,
    recipes=recipes,
    excel_filename="",
    generated_at=datetime.now(),
)

excel_path = ExcelAgent().render(plan, OUTPUT_DIR)
size_kb = os.path.getsize(excel_path) // 1024

print(f"\n✅ 완료!")
print(f"   파일: {excel_path}")
print(f"   크기: {size_kb} KB")
print(f"\n📋 시트 구성:")
print(f"   1. 월간 식단표  — {NUM_DAYS}일 달력형 식단")
print(f"   2. 조식        — 14일 조식 상세")
print(f"   3. 중식        — 14일 중식 상세")
print(f"   4. 석식        — 14일 석식 상세")
print(f"   5. 야식        — 삶은계란/바나나/우유")
print(f"   6. 영양분석     — 일별 열량 차트 포함")
print(f"   7. 알레르기표시 — 16종 알레르기 매트릭스")
print(f"   8. 원가분석     — 일별 식재료 원가")
print(f"   9. 발주량 집계  — {len(procurement)}개 식재료 총 발주량")
print(f"  10. 조리지침서   — {len(recipes)}개 메뉴 SOP (HACCP CCP 포함)")
