import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SAEnum, Float, Integer, String, Text
from database import Base

# ─── 레이블 매핑 ──────────────────────────────────────────────────────────────

DIABETES_TYPE_LABELS = {
    "type1": "1형 당뇨",
    "type2": "2형 당뇨",
    "prediabetes": "당뇨 전단계",
    "gestational": "임신성 당뇨",
    "none": "비당뇨",
}

INTENSITY_LABELS = {
    "light": "가벼운",
    "moderate": "보통",
    "intense": "격렬한",
}

TREND_LABELS = {
    "NONE": "→",
    "DoubleUp": "↑↑",
    "SingleUp": "↑",
    "FortyFiveUp": "↗",
    "Flat": "→",
    "FortyFiveDown": "↘",
    "SingleDown": "↓",
    "DoubleDown": "↓↓",
    "NOT_COMPUTABLE": "-",
    "RATE_OUT_OF_RANGE": "?",
}

EXERCISE_TYPES = [
    "걷기", "달리기", "자전거", "수영", "근력운동",
    "요가", "등산", "HIIT", "필라테스", "골프", "테니스", "기타",
]

EXERCISE_MET = {
    "걷기": 3.5, "달리기": 8.0, "자전거": 6.0, "수영": 7.0,
    "근력운동": 5.0, "요가": 3.0, "등산": 6.0, "HIIT": 10.0,
    "필라테스": 3.5, "골프": 4.0, "테니스": 7.0, "기타": 4.0,
}

COMMON_FOODS = [
    {"name": "쌀밥 (1공기)", "calories": 300, "carbs": 65.0, "protein": 5.0, "fat": 1.0},
    {"name": "현미밥 (1공기)", "calories": 280, "carbs": 60.0, "protein": 5.0, "fat": 2.0},
    {"name": "잡곡밥 (1공기)", "calories": 290, "carbs": 61.0, "protein": 6.0, "fat": 2.0},
    {"name": "김치찌개", "calories": 150, "carbs": 10.0, "protein": 12.0, "fat": 6.0},
    {"name": "된장찌개", "calories": 130, "carbs": 8.0, "protein": 10.0, "fat": 5.0},
    {"name": "비빔밥", "calories": 450, "carbs": 75.0, "protein": 15.0, "fat": 10.0},
    {"name": "삼겹살 (200g)", "calories": 580, "carbs": 0.0, "protein": 30.0, "fat": 50.0},
    {"name": "닭가슴살 (100g)", "calories": 165, "carbs": 0.0, "protein": 31.0, "fat": 4.0},
    {"name": "계란 (2개)", "calories": 140, "carbs": 1.0, "protein": 12.0, "fat": 10.0},
    {"name": "두부찌개", "calories": 120, "carbs": 5.0, "protein": 10.0, "fat": 6.0},
    {"name": "고등어구이", "calories": 300, "carbs": 0.0, "protein": 25.0, "fat": 20.0},
    {"name": "국수 (1인분)", "calories": 380, "carbs": 72.0, "protein": 12.0, "fat": 4.0},
    {"name": "라면 (1봉)", "calories": 500, "carbs": 75.0, "protein": 10.0, "fat": 18.0},
    {"name": "샌드위치", "calories": 350, "carbs": 40.0, "protein": 18.0, "fat": 12.0},
    {"name": "바나나 (1개)", "calories": 90, "carbs": 23.0, "protein": 1.0, "fat": 0.0},
    {"name": "사과 (1개)", "calories": 80, "carbs": 21.0, "protein": 0.0, "fat": 0.0},
    {"name": "고구마 (1개)", "calories": 130, "carbs": 30.0, "protein": 2.0, "fat": 0.0},
    {"name": "우유 (200ml)", "calories": 130, "carbs": 10.0, "protein": 7.0, "fat": 7.0},
    {"name": "요거트 (150g)", "calories": 100, "carbs": 12.0, "protein": 5.0, "fat": 3.0},
    {"name": "아메리카노", "calories": 10, "carbs": 2.0, "protein": 0.0, "fat": 0.0},
    {"name": "라떼 (400ml)", "calories": 200, "carbs": 20.0, "protein": 7.0, "fat": 9.0},
    {"name": "오렌지주스 (200ml)", "calories": 90, "carbs": 21.0, "protein": 1.0, "fat": 0.0},
]


# ─── 모델 ─────────────────────────────────────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, default="사용자")
    weight_kg = Column(Float, default=65.0)
    diabetes_type = Column(
        SAEnum("type1", "type2", "prediabetes", "gestational", "none", name="diabetes_type_enum"),
        default="type2",
    )
    target_low = Column(Integer, default=70)
    target_high = Column(Integer, default=180)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def diabetes_label(self):
        return DIABETES_TYPE_LABELS.get(self.diabetes_type, self.diabetes_type)


class DexcomToken(Base):
    __tablename__ = "dexcom_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    glucose_value = Column(Integer, nullable=False)
    trend = Column(String(30), nullable=True)
    source = Column(String(20), default="dexcom")
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def trend_arrow(self):
        return TREND_LABELS.get(self.trend or "Flat", "→")

    @property
    def status(self):
        if self.glucose_value < 70:
            return "low"
        elif self.glucose_value > 180:
            return "high"
        return "normal"

    @property
    def status_label(self):
        return {"low": "저혈당", "high": "고혈당", "normal": "정상"}[self.status]


class MealLog(Base):
    __tablename__ = "meal_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    logged_at = Column(DateTime, nullable=False, index=True)
    meal_name = Column(String(200), nullable=False)
    calories = Column(Integer, nullable=True)
    carbs = Column(Float, nullable=True)
    protein = Column(Float, nullable=True)
    fat = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExerciseLog(Base):
    __tablename__ = "exercise_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    logged_at = Column(DateTime, nullable=False, index=True)
    exercise_type = Column(String(100), nullable=False)
    duration_min = Column(Integer, nullable=False)
    intensity = Column(
        SAEnum("light", "moderate", "intense", name="intensity_enum"),
        default="moderate",
    )
    calories_burned = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def intensity_label(self):
        return INTENSITY_LABELS.get(self.intensity, self.intensity)


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    ingredients = Column(Text, nullable=False)  # JSON array of strings
    instructions = Column(Text, nullable=True)
    calories = Column(Integer, nullable=True)
    carbs = Column(Float, nullable=True)
    protein = Column(Float, nullable=True)
    fat = Column(Float, nullable=True)
    servings = Column(Integer, default=1)
    tags = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def ingredients_list(self):
        try:
            return json.loads(self.ingredients)
        except Exception:
            return [self.ingredients]

    @property
    def tags_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]
