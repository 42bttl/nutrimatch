import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import crud
import dexcom
import models
from database import Base, engine, get_db
from models import COMMON_FOODS, EXERCISE_TYPES, INTENSITY_LABELS

# ─── 초기화 ───────────────────────────────────────────────────────────────────

app = FastAPI(title="GlucoLife")
Base.metadata.create_all(bind=engine)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def fmt_time(dt: Optional[datetime]) -> str:
    return dt.strftime("%H:%M") if dt else "-"


def fmt_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%m/%d %H:%M") if dt else "-"


templates.env.filters["fmt_time"] = fmt_time
templates.env.filters["fmt_dt"] = fmt_dt


def common_ctx(db: Session) -> dict:
    profile = crud.get_user_profile(db)
    token = crud.get_dexcom_token(db)
    latest = crud.get_latest_glucose(db)
    return {
        "profile": profile,
        "dexcom_connected": token is not None,
        "dexcom_configured": dexcom.is_configured(),
        "latest_glucose": latest,
    }


# ─── 대시보드 ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    ctx = common_ctx(db)
    profile = ctx["profile"]
    today_meals = crud.get_today_meals(db)
    today_exercises = crud.get_today_exercises(db)
    daily_stats = crud.get_daily_glucose_stats(db, profile.target_low, profile.target_high)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        **ctx,
        "today_meals": today_meals,
        "today_exercises": today_exercises,
        "daily_stats": daily_stats,
        "total_calories_in": sum(m.calories or 0 for m in today_meals),
        "total_calories_out": sum(e.calories_burned or 0 for e in today_exercises),
        "total_carbs": round(sum(m.carbs or 0 for m in today_meals), 1),
    })


# ─── 혈당 차트 API ────────────────────────────────────────────────────────────

@app.get("/api/glucose")
def api_glucose(hours: int = 24, db: Session = Depends(get_db)):
    profile = crud.get_user_profile(db)
    readings = crud.get_glucose_readings(db, hours=hours)
    since = datetime.utcnow() - timedelta(hours=hours)

    meals = [
        {"x": m.logged_at.isoformat(), "y": profile.target_high + 15,
         "label": m.meal_name, "calories": m.calories}
        for m in crud.get_meal_logs(db, limit=500)
        if m.logged_at >= since
    ]
    exercises = [
        {"x": e.logged_at.isoformat(), "y": profile.target_low - 15,
         "label": e.exercise_type, "duration": e.duration_min}
        for e in crud.get_exercise_logs(db, limit=500)
        if e.logged_at >= since
    ]

    return JSONResponse({
        "glucose": [{"x": r.timestamp.isoformat(), "y": r.glucose_value, "trend": r.trend}
                    for r in readings],
        "meals": meals,
        "exercises": exercises,
        "target_low": profile.target_low,
        "target_high": profile.target_high,
    })


# ─── 혈당 페이지 ──────────────────────────────────────────────────────────────

@app.get("/glucose", response_class=HTMLResponse)
async def glucose_page(request: Request, db: Session = Depends(get_db)):
    ctx = common_ctx(db)
    profile = ctx["profile"]
    sync_error = None

    token = crud.get_dexcom_token(db)
    if token:
        try:
            now = datetime.utcnow()
            if token.expires_at <= now + timedelta(minutes=5):
                new_tokens = await dexcom.refresh_token_flow(token.refresh_token)
                expires_at = now + timedelta(seconds=new_tokens["expires_in"])
                crud.save_dexcom_token(db, new_tokens["access_token"],
                                       new_tokens["refresh_token"], expires_at)
                access_token = new_tokens["access_token"]
            else:
                access_token = token.access_token
            egvs = await dexcom.fetch_egvs(access_token, now - timedelta(hours=24), now)
            crud.save_glucose_readings(db, egvs)
        except Exception as e:
            sync_error = str(e)

    weekly_stats = crud.get_weekly_stats(db, profile.target_low, profile.target_high)
    recent = list(reversed(crud.get_glucose_readings(db, hours=3)[-10:]))
    return templates.TemplateResponse("glucose.html", {
        "request": request,
        **ctx,
        "weekly_stats": weekly_stats,
        "recent_readings": recent,
        "sync_error": sync_error,
        "msg": request.query_params.get("msg"),
    })


@app.post("/glucose/manual")
def glucose_manual(
    glucose_value: int = Form(...),
    timestamp: str = Form(...),
    trend: str = Form(default="Flat"),
    db: Session = Depends(get_db),
):
    ts = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M")
    crud.add_manual_glucose(db, ts, glucose_value, trend)
    return RedirectResponse(url="/glucose?msg=혈당+기록이+추가되었습니다", status_code=303)


# ─── 식사 ─────────────────────────────────────────────────────────────────────

@app.get("/meals", response_class=HTMLResponse)
def meals_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("meals.html", {
        "request": request,
        **common_ctx(db),
        "meals": crud.get_meal_logs(db),
        "msg": request.query_params.get("msg"),
    })


@app.get("/meals/add", response_class=HTMLResponse)
def meals_add_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("meal_add.html", {
        "request": request,
        **common_ctx(db),
        "common_foods": COMMON_FOODS,
        "default_time": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "error": None,
        "form": {},
    })


@app.post("/meals/add", response_class=HTMLResponse)
def meals_add(
    request: Request,
    logged_at: str = Form(...),
    meal_name: str = Form(...),
    calories: Optional[str] = Form(default=None),
    carbs: Optional[str] = Form(default=None),
    protein: Optional[str] = Form(default=None),
    fat: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    ctx = common_ctx(db)
    try:
        ts = datetime.strptime(logged_at, "%Y-%m-%dT%H:%M")
        crud.create_meal_log(
            db,
            logged_at=ts,
            meal_name=meal_name.strip(),
            calories=int(calories) if calories and calories.strip() else None,
            carbs=float(carbs) if carbs and carbs.strip() else None,
            protein=float(protein) if protein and protein.strip() else None,
            fat=float(fat) if fat and fat.strip() else None,
            notes=notes.strip() if notes else None,
        )
        return RedirectResponse(url="/meals?msg=식사+기록이+추가되었습니다", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("meal_add.html", {
            "request": request, **ctx,
            "common_foods": COMMON_FOODS,
            "default_time": logged_at,
            "error": str(e),
            "form": {"meal_name": meal_name},
        })


@app.post("/meals/{meal_id}/delete")
def meals_delete(meal_id: int, db: Session = Depends(get_db)):
    crud.delete_meal_log(db, meal_id)
    return RedirectResponse(url="/meals?msg=삭제되었습니다", status_code=303)


# ─── 운동 ─────────────────────────────────────────────────────────────────────

@app.get("/exercise", response_class=HTMLResponse)
def exercise_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("exercise.html", {
        "request": request,
        **common_ctx(db),
        "exercises": crud.get_exercise_logs(db),
        "msg": request.query_params.get("msg"),
    })


@app.get("/exercise/add", response_class=HTMLResponse)
def exercise_add_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("exercise_add.html", {
        "request": request,
        **common_ctx(db),
        "exercise_types": EXERCISE_TYPES,
        "intensity_labels": INTENSITY_LABELS,
        "default_time": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "error": None,
        "form": {},
    })


@app.post("/exercise/add", response_class=HTMLResponse)
def exercise_add(
    request: Request,
    logged_at: str = Form(...),
    exercise_type: str = Form(...),
    duration_min: int = Form(...),
    intensity: str = Form(...),
    notes: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    ctx = common_ctx(db)
    profile = ctx["profile"]
    try:
        ts = datetime.strptime(logged_at, "%Y-%m-%dT%H:%M")
        crud.create_exercise_log(
            db,
            logged_at=ts,
            exercise_type=exercise_type,
            duration_min=duration_min,
            intensity=intensity,
            weight_kg=profile.weight_kg,
            notes=notes.strip() if notes else None,
        )
        return RedirectResponse(url="/exercise?msg=운동+기록이+추가되었습니다", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("exercise_add.html", {
            "request": request, **ctx,
            "exercise_types": EXERCISE_TYPES,
            "intensity_labels": INTENSITY_LABELS,
            "default_time": logged_at,
            "error": str(e),
            "form": {"exercise_type": exercise_type},
        })


@app.post("/exercise/{exercise_id}/delete")
def exercise_delete(exercise_id: int, db: Session = Depends(get_db)):
    crud.delete_exercise_log(db, exercise_id)
    return RedirectResponse(url="/exercise?msg=삭제되었습니다", status_code=303)


# ─── 인사이트 ─────────────────────────────────────────────────────────────────

@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request, db: Session = Depends(get_db)):
    ctx = common_ctx(db)
    profile = ctx["profile"]
    weekly_stats = crud.get_weekly_stats(db, profile.target_low, profile.target_high)
    hourly_avg = crud.get_hourly_avg_glucose(db, days=7)
    return templates.TemplateResponse("insights.html", {
        "request": request,
        **ctx,
        "weekly_stats": weekly_stats,
        "hourly_avg_json": json.dumps(hourly_avg),
    })


# ─── 레시피 ───────────────────────────────────────────────────────────────────

@app.get("/recipes", response_class=HTMLResponse)
def recipes_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("recipes.html", {
        "request": request,
        **common_ctx(db),
        "recipes": crud.get_recipes(db),
        "msg": request.query_params.get("msg"),
    })


@app.get("/recipes/add", response_class=HTMLResponse)
def recipes_add_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("recipe_add.html", {
        "request": request,
        **common_ctx(db),
        "error": None,
    })


@app.post("/recipes/add", response_class=HTMLResponse)
def recipes_add(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(default=None),
    ingredients: str = Form(...),
    instructions: Optional[str] = Form(default=None),
    calories: Optional[str] = Form(default=None),
    carbs: Optional[str] = Form(default=None),
    protein: Optional[str] = Form(default=None),
    fat: Optional[str] = Form(default=None),
    servings: int = Form(default=1),
    tags: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    ctx = common_ctx(db)
    try:
        ingredients_list = [i.strip() for i in ingredients.split("\n") if i.strip()]
        crud.create_recipe(
            db,
            name=name.strip(),
            description=description.strip() if description else None,
            ingredients=ingredients_list,
            instructions=instructions.strip() if instructions else None,
            calories=int(calories) if calories and calories.strip() else None,
            carbs=float(carbs) if carbs and carbs.strip() else None,
            protein=float(protein) if protein and protein.strip() else None,
            fat=float(fat) if fat and fat.strip() else None,
            servings=servings,
            tags=tags.strip() if tags else None,
        )
        return RedirectResponse(url="/recipes?msg=레시피가+추가되었습니다", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("recipe_add.html", {
            "request": request, **ctx, "error": str(e),
        })


@app.post("/recipes/{recipe_id}/delete")
def recipes_delete(recipe_id: int, db: Session = Depends(get_db)):
    crud.delete_recipe(db, recipe_id)
    return RedirectResponse(url="/recipes?msg=삭제되었습니다", status_code=303)


# ─── 설정 ─────────────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        **common_ctx(db),
        "diabetes_types": models.DIABETES_TYPE_LABELS,
        "saved": request.query_params.get("saved"),
        "error": request.query_params.get("error"),
    })


@app.post("/settings")
def settings_save(
    name: str = Form(...),
    weight_kg: float = Form(...),
    diabetes_type: str = Form(...),
    target_low: int = Form(...),
    target_high: int = Form(...),
    db: Session = Depends(get_db),
):
    crud.update_user_profile(db, name, weight_kg, diabetes_type, target_low, target_high)
    return RedirectResponse(url="/settings?saved=1", status_code=303)


# ─── Dexcom OAuth ─────────────────────────────────────────────────────────────

@app.get("/auth/dexcom")
def auth_dexcom_start():
    if not dexcom.is_configured():
        return RedirectResponse(url="/settings?error=dexcom_not_configured")
    return RedirectResponse(url=dexcom.get_auth_url())


@app.get("/auth/dexcom/callback")
async def auth_dexcom_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if error or not code:
        return RedirectResponse(url="/settings?error=dexcom_auth_failed")
    try:
        tokens = await dexcom.exchange_code(code)
        expires_at = datetime.utcnow() + timedelta(seconds=tokens["expires_in"])
        crud.save_dexcom_token(db, tokens["access_token"], tokens["refresh_token"], expires_at)
        return RedirectResponse(url="/glucose?msg=Dexcom+연동이+완료되었습니다")
    except Exception:
        return RedirectResponse(url="/settings?error=token_exchange_failed")


@app.post("/auth/dexcom/disconnect")
def auth_dexcom_disconnect(db: Session = Depends(get_db)):
    crud.delete_dexcom_token(db)
    return RedirectResponse(url="/settings?saved=disconnected", status_code=303)
