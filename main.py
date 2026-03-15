import json
from datetime import time as dt_time
from typing import List, Optional

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import crud
import models
from database import Base, engine, get_db
from models import ALL_DAYS, DAY_LABELS, REGION_LABELS, SPECIALTY_LABELS

# ─── 앱 초기화 ────────────────────────────────────────────────────────────────

app = FastAPI(title="NutriMatch — 영양사 매칭 플랫폼")

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

# 정적 파일
app.mount("/static", StaticFiles(directory="static"), name="static")

# 템플릿
templates = Jinja2Templates(directory="templates")


# Jinja2 커스텀 필터
def format_krw(value: int) -> str:
    return f"₩{value:,}"


templates.env.filters["krw"] = format_krw


# ─── 홈 ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "nutritionist_count": crud.count_nutritionists(db),
        "match_count": crud.count_match_results(db),
        "company_count": crud.count_company_requests(db),
    })


# ─── 영양사 ───────────────────────────────────────────────────────────────────

@app.get("/nutritionists", response_class=HTMLResponse)
def nutritionist_list(request: Request, db: Session = Depends(get_db)):
    nutritionists = crud.get_nutritionists(db)
    return templates.TemplateResponse("nutritionist_list.html", {
        "request": request,
        "nutritionists": nutritionists,
    })


@app.get("/nutritionists/register", response_class=HTMLResponse)
def nutritionist_register_form(request: Request):
    return templates.TemplateResponse("nutritionist_register.html", {
        "request": request,
        "error": None,
        "form": {},
    })


@app.post("/nutritionists/register", response_class=HTMLResponse)
def nutritionist_register(
    request: Request,
    name: str = Form(...),
    license_number: str = Form(...),
    specialty: str = Form(...),
    region: str = Form(...),
    available_days: List[str] = Form(default=[]),
    available_time_start: str = Form(...),
    available_time_end: str = Form(...),
    hourly_rate: int = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    bio: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    form_data = {
        "name": name, "license_number": license_number,
        "specialty": specialty, "region": region,
        "available_time_start": available_time_start,
        "available_time_end": available_time_end,
        "hourly_rate": hourly_rate, "email": email,
        "phone": phone, "bio": bio,
    }

    # 중복 검사
    if crud.get_nutritionist_by_license(db, license_number):
        return templates.TemplateResponse("nutritionist_register.html", {
            "request": request,
            "error": f"이미 등록된 면허번호입니다: {license_number}",
            "form": form_data,
        })
    if crud.get_nutritionist_by_email(db, email):
        return templates.TemplateResponse("nutritionist_register.html", {
            "request": request,
            "error": f"이미 사용 중인 이메일입니다: {email}",
            "form": form_data,
        })
    if not available_days:
        return templates.TemplateResponse("nutritionist_register.html", {
            "request": request,
            "error": "가능 요일을 하나 이상 선택해주세요.",
            "form": form_data,
        })

    # 시간 파싱
    try:
        start_h, start_m = map(int, available_time_start.split(":"))
        end_h, end_m = map(int, available_time_end.split(":"))
        t_start = dt_time(start_h, start_m)
        t_end = dt_time(end_h, end_m)
        if t_start >= t_end:
            raise ValueError("종료 시간이 시작 시간보다 늦어야 합니다.")
    except ValueError as e:
        return templates.TemplateResponse("nutritionist_register.html", {
            "request": request,
            "error": str(e),
            "form": form_data,
        })

    n = crud.create_nutritionist(
        db,
        name=name,
        license_number=license_number,
        specialty=specialty,
        region=region,
        available_days=available_days,
        available_time_start=t_start,
        available_time_end=t_end,
        hourly_rate=hourly_rate,
        email=email,
        phone=phone,
        bio=bio or None,
    )
    return RedirectResponse(url=f"/nutritionists?registered=1", status_code=303)


# ─── 기업 수요 ────────────────────────────────────────────────────────────────

@app.get("/companies/request", response_class=HTMLResponse)
def company_request_form(request: Request):
    return templates.TemplateResponse("company_request.html", {
        "request": request,
        "error": None,
    })


@app.post("/companies/request", response_class=HTMLResponse)
def company_request_submit(
    request: Request,
    company_name: str = Form(...),
    company_size: str = Form(...),
    service_type: str = Form(...),
    preferred_region: str = Form(...),
    budget_per_hour: int = Form(...),
    required_specialty: str = Form(...),
    contact_name: str = Form(...),
    contact_email: str = Form(...),
    contact_phone: str = Form(...),
    preferred_days: List[str] = Form(default=[]),
    preferred_time_start: str = Form(...),
    preferred_time_end: str = Form(...),
    notes: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    if not preferred_days:
        return templates.TemplateResponse("company_request.html", {
            "request": request,
            "error": "희망 요일을 하나 이상 선택해주세요.",
        })

    try:
        start_h, start_m = map(int, preferred_time_start.split(":"))
        end_h, end_m = map(int, preferred_time_end.split(":"))
        t_start = dt_time(start_h, start_m)
        t_end = dt_time(end_h, end_m)
        if t_start >= t_end:
            raise ValueError("종료 시간이 시작 시간보다 늦어야 합니다.")
    except ValueError as e:
        return templates.TemplateResponse("company_request.html", {
            "request": request,
            "error": str(e),
        })

    company_req = crud.create_company_request(
        db,
        company_name=company_name,
        company_size=company_size,
        service_type=service_type,
        preferred_region=preferred_region,
        budget_per_hour=budget_per_hour,
        required_specialty=required_specialty,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        preferred_days=preferred_days,
        preferred_time_start=t_start,
        preferred_time_end=t_end,
        notes=notes or None,
    )

    # 매칭 즉시 실행
    crud.run_matching(company_req.id, db)

    return RedirectResponse(
        url=f"/matching/{company_req.id}?status=success",
        status_code=303
    )


# ─── 매칭 결과 ────────────────────────────────────────────────────────────────

@app.get("/matching/{request_id}", response_class=HTMLResponse)
def matching_result(request: Request, request_id: int, db: Session = Depends(get_db)):
    company_request = crud.get_company_request(db, request_id)
    if not company_request:
        return RedirectResponse(url="/", status_code=303)

    results = crud.get_match_results(db, request_id)

    return templates.TemplateResponse("matching_result.html", {
        "request": request,
        "company_request": company_request,
        "results": results,
        "all_days": ALL_DAYS,
        "day_labels": DAY_LABELS,
    })


# ─── 예약 ─────────────────────────────────────────────────────────────────────

@app.post("/bookings/create")
def create_booking(
    match_result_id: int = Form(...),
    redirect_to: str = Form(default="/bookings"),
    db: Session = Depends(get_db),
):
    crud.create_booking(db, match_result_id)
    return RedirectResponse(url=redirect_to, status_code=303)


@app.get("/bookings", response_class=HTMLResponse)
def booking_list(request: Request, db: Session = Depends(get_db)):
    bookings = crud.get_bookings(db)
    return templates.TemplateResponse("booking_list.html", {
        "request": request,
        "bookings": bookings,
    })


@app.post("/bookings/{booking_id}/confirm")
def confirm_booking(booking_id: int, db: Session = Depends(get_db)):
    crud.update_booking_status(db, booking_id, "confirmed")
    return RedirectResponse(url="/bookings?msg=예약이+확정되었습니다", status_code=303)


@app.post("/bookings/{booking_id}/complete")
def complete_booking(booking_id: int, db: Session = Depends(get_db)):
    crud.update_booking_status(db, booking_id, "completed")
    return RedirectResponse(url="/bookings?msg=서비스가+완료처리되었습니다", status_code=303)


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    crud.update_booking_status(db, booking_id, "cancelled")
    return RedirectResponse(url="/bookings?msg=예약이+취소되었습니다", status_code=303)


# ─── 샘플 데이터 ──────────────────────────────────────────────────────────────

@app.get("/seed", response_class=HTMLResponse)
def seed(request: Request, db: Session = Depends(get_db)):
    inserted = crud.seed_nutritionists(db)
    total = crud.count_nutritionists(db)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "nutritionist_count": total,
        "match_count": crud.count_match_results(db),
        "company_count": crud.count_company_requests(db),
        "seed_msg": f"샘플 영양사 {inserted}명 추가 완료 (전체 {total}명)",
    })
