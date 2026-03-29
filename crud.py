import json
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from models import (
    DexcomToken, ExerciseLog, GlucoseReading, MealLog, Recipe,
    UserProfile, EXERCISE_MET,
)


# ─── User Profile ─────────────────────────────────────────────────────────────

def get_user_profile(db: Session) -> UserProfile:
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def update_user_profile(
    db: Session, name: str, weight_kg: float,
    diabetes_type: str, target_low: int, target_high: int,
) -> UserProfile:
    profile = get_user_profile(db)
    profile.name = name
    profile.weight_kg = weight_kg
    profile.diabetes_type = diabetes_type
    profile.target_low = target_low
    profile.target_high = target_high
    db.commit()
    db.refresh(profile)
    return profile


# ─── Dexcom Token ─────────────────────────────────────────────────────────────

def save_dexcom_token(
    db: Session, access_token: str, refresh_token: str, expires_at: datetime
) -> DexcomToken:
    token = db.query(DexcomToken).first()
    if token:
        token.access_token = access_token
        token.refresh_token = refresh_token
        token.expires_at = expires_at
        token.updated_at = datetime.utcnow()
    else:
        token = DexcomToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        db.add(token)
    db.commit()
    return token


def get_dexcom_token(db: Session) -> Optional[DexcomToken]:
    return db.query(DexcomToken).first()


def delete_dexcom_token(db: Session):
    db.query(DexcomToken).delete()
    db.commit()


# ─── Glucose ──────────────────────────────────────────────────────────────────

def save_glucose_readings(db: Session, readings: list):
    for r in readings:
        ts_str = r.get("displayTime") or r.get("systemTime", "")
        if not ts_str:
            continue
        ts_str = ts_str.rstrip("Z").split("+")[0]
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            continue

        existing = db.query(GlucoseReading).filter(GlucoseReading.timestamp == ts).first()
        if not existing:
            db.add(GlucoseReading(
                timestamp=ts,
                glucose_value=int(r.get("value", 0)),
                trend=r.get("trend", "Flat"),
                source="dexcom",
            ))
    db.commit()


def add_manual_glucose(
    db: Session, timestamp: datetime, glucose_value: int, trend: str = "Flat"
) -> GlucoseReading:
    reading = GlucoseReading(
        timestamp=timestamp,
        glucose_value=glucose_value,
        trend=trend,
        source="manual",
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def get_glucose_readings(db: Session, hours: int = 24) -> List[GlucoseReading]:
    since = datetime.utcnow() - timedelta(hours=hours)
    return (
        db.query(GlucoseReading)
        .filter(GlucoseReading.timestamp >= since)
        .order_by(GlucoseReading.timestamp)
        .all()
    )


def get_latest_glucose(db: Session) -> Optional[GlucoseReading]:
    return db.query(GlucoseReading).order_by(GlucoseReading.timestamp.desc()).first()


def get_daily_glucose_stats(
    db: Session, target_low: int = 70, target_high: int = 180
) -> dict:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    readings = db.query(GlucoseReading).filter(GlucoseReading.timestamp >= today).all()

    if not readings:
        return {"count": 0, "avg": None, "min": None, "max": None, "tir": None, "gmi": None}

    values = [r.glucose_value for r in readings]
    in_range = sum(1 for v in values if target_low <= v <= target_high)
    avg = sum(values) / len(values)

    return {
        "count": len(values),
        "avg": round(avg, 1),
        "min": min(values),
        "max": max(values),
        "tir": round((in_range / len(values)) * 100, 1),
        "gmi": round(3.31 + 0.02392 * avg, 2),
    }


# ─── Meal Log ─────────────────────────────────────────────────────────────────

def create_meal_log(
    db: Session,
    logged_at: datetime,
    meal_name: str,
    calories: Optional[int],
    carbs: Optional[float],
    protein: Optional[float],
    fat: Optional[float],
    notes: Optional[str] = None,
) -> MealLog:
    meal = MealLog(
        logged_at=logged_at,
        meal_name=meal_name,
        calories=calories,
        carbs=carbs,
        protein=protein,
        fat=fat,
        notes=notes,
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal


def get_meal_logs(db: Session, limit: int = 100) -> List[MealLog]:
    return db.query(MealLog).order_by(MealLog.logged_at.desc()).limit(limit).all()


def get_today_meals(db: Session) -> List[MealLog]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(MealLog).filter(MealLog.logged_at >= today).order_by(MealLog.logged_at).all()


def delete_meal_log(db: Session, meal_id: int):
    meal = db.query(MealLog).filter(MealLog.id == meal_id).first()
    if meal:
        db.delete(meal)
        db.commit()


# ─── Exercise Log ─────────────────────────────────────────────────────────────

def create_exercise_log(
    db: Session,
    logged_at: datetime,
    exercise_type: str,
    duration_min: int,
    intensity: str,
    weight_kg: float = 65.0,
    notes: Optional[str] = None,
) -> ExerciseLog:
    met = EXERCISE_MET.get(exercise_type, 4.0)
    calories_burned = int(met * weight_kg * (duration_min / 60))
    exercise = ExerciseLog(
        logged_at=logged_at,
        exercise_type=exercise_type,
        duration_min=duration_min,
        intensity=intensity,
        calories_burned=calories_burned,
        notes=notes,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


def get_exercise_logs(db: Session, limit: int = 100) -> List[ExerciseLog]:
    return db.query(ExerciseLog).order_by(ExerciseLog.logged_at.desc()).limit(limit).all()


def get_today_exercises(db: Session) -> List[ExerciseLog]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(ExerciseLog)
        .filter(ExerciseLog.logged_at >= today)
        .order_by(ExerciseLog.logged_at)
        .all()
    )


def delete_exercise_log(db: Session, exercise_id: int):
    ex = db.query(ExerciseLog).filter(ExerciseLog.id == exercise_id).first()
    if ex:
        db.delete(ex)
        db.commit()


# ─── Recipe ───────────────────────────────────────────────────────────────────

def create_recipe(
    db: Session,
    name: str,
    description: Optional[str],
    ingredients: list,
    instructions: Optional[str],
    calories: Optional[int],
    carbs: Optional[float],
    protein: Optional[float],
    fat: Optional[float],
    servings: int = 1,
    tags: Optional[str] = None,
) -> Recipe:
    recipe = Recipe(
        name=name,
        description=description,
        ingredients=json.dumps(ingredients, ensure_ascii=False),
        instructions=instructions,
        calories=calories,
        carbs=carbs,
        protein=protein,
        fat=fat,
        servings=servings,
        tags=tags,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def get_recipes(db: Session) -> List[Recipe]:
    return db.query(Recipe).order_by(Recipe.created_at.desc()).all()


def get_recipe(db: Session, recipe_id: int) -> Optional[Recipe]:
    return db.query(Recipe).filter(Recipe.id == recipe_id).first()


def delete_recipe(db: Session, recipe_id: int):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe:
        db.delete(recipe)
        db.commit()


# ─── Insights ─────────────────────────────────────────────────────────────────

def get_weekly_stats(
    db: Session, target_low: int = 70, target_high: int = 180
) -> dict:
    week_ago = datetime.utcnow() - timedelta(days=7)
    readings = db.query(GlucoseReading).filter(GlucoseReading.timestamp >= week_ago).all()

    if not readings:
        return {
            "count": 0, "avg": None, "min": None, "max": None,
            "tir": None, "time_low": None, "time_high": None,
            "gmi": None, "std_dev": None, "cv": None,
        }

    values = [r.glucose_value for r in readings]
    n = len(values)
    avg = sum(values) / n
    in_range = sum(1 for v in values if target_low <= v <= target_high)
    in_low = sum(1 for v in values if v < target_low)
    in_high = sum(1 for v in values if v > target_high)
    variance = sum((v - avg) ** 2 for v in values) / n
    std_dev = variance ** 0.5
    cv = (std_dev / avg) * 100 if avg > 0 else 0

    return {
        "count": n,
        "avg": round(avg, 1),
        "min": min(values),
        "max": max(values),
        "tir": round((in_range / n) * 100, 1),
        "time_low": round((in_low / n) * 100, 1),
        "time_high": round((in_high / n) * 100, 1),
        "gmi": round(3.31 + 0.02392 * avg, 2),
        "std_dev": round(std_dev, 1),
        "cv": round(cv, 1),
    }


def get_hourly_avg_glucose(db: Session, days: int = 7) -> list:
    since = datetime.utcnow() - timedelta(days=days)
    readings = db.query(GlucoseReading).filter(GlucoseReading.timestamp >= since).all()

    hourly: dict = {h: [] for h in range(24)}
    for r in readings:
        hourly[r.timestamp.hour].append(r.glucose_value)

    return [
        {"hour": h, "avg": round(sum(v) / len(v), 1) if v else None}
        for h, v in hourly.items()
    ]
