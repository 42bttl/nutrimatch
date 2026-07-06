import os
from datetime import time as dt_time
from typing import List, Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import crud
import models
from auth import current_user, hash_password, verify_password
from database import Base, engine, get_db
from models import ALL_DAYS, DAY_LABELS, REGION_LABELS, SPECIALTY_LABELS

# ─── 앱 초기화 ────────────────────────────────────────────────────────────────

app = FastAPI(title="NutriMatch — 영양사 매칭 플랫폼")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=60 * 60 * 24 * 14,  # 2주
    same_site="lax",
)

# DB 테이블 생성
Base.metadata.create_all(bind=engine)


def _migrate_legacy_tables():
    """기존 배포 DB에 user_id 컬럼이 없으면 추가한다."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in ("nutritionists", "company_requests"):
            if table not in inspector.get_table_names():
                continue
            cols = [c["name"] for c in inspector.get_columns(table)]
            if "user_id" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))


_migrate_legacy_tables()

# 정적 파일
app.mount("/static", StaticFiles(directory="static"), name="static")

# 템플릿
templates = Jinja2Templates(directory="templates")


# Jinja2 커스텀 필터
def format_krw(value: int) -> str:
    return f"₩{value:,}"


templates.env.filters["krw"] = format_krw


def render(request: Request, name: str, user: Optional[models.User], **ctx):
    ctx.update({"request": request, "user": user})
    return templates.TemplateResponse(name, ctx)


def login_redirect(next_path: str) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={quote(next_path)}", status_code=303)


def parse_time_range(start: str, end: str):
    start_h, start_m = map(int, start.split(":"))
    end_h, end_m = map(int, end.split(":"))
    t_start = dt_time(start_h, start_m)
    t_end = dt_time(end_h, end_m)
    if t_start >= t_end:
        raise ValueError("종료 시간이 시작 시간보다 늦어야 합니다.")
    return t_start, t_end


# ─── 홈 ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    return render(
        request, "index.html", user,
        nutritionist_count=crud.count_nutritionists(db),
        match_count=crud.count_match_results(db),
        company_count=crud.count_company_requests(db),
    )


# ─── 회원가입 / 로그인 ─────────────────────────────────────────────────────────

@app.get("/signup", response_class=HTMLResponse)
def signup_choice(
    request: Request,
    user: Optional[models.User] = Depends(current_user),
):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return render(request, "signup.html", user)


@app.get("/signup/nutritionist", response_class=HTMLResponse)
def signup_nutritionist_form(
    request: Request,
    user: Optional[models.User] = Depends(current_user),
):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return render(request, "signup_nutritionist.html", user, error=None, form={})


@app.post("/signup/nutritionist", response_class=HTMLResponse)
def signup_nutritionist(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    name: str = Form(...),
    license_number: str = Form(...),
    specialty: str = Form(...),
    region: str = Form(...),
    available_days: List[str] = Form(default=[]),
    available_time_start: str = Form(...),
    available_time_end: str = Form(...),
    hourly_rate: int = Form(...),
    phone: str = Form(...),
    bio: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    form_data = {
        "email": email, "name": name, "license_number": license_number,
        "specialty": specialty, "region": region,
        "available_time_start": available_time_start,
        "available_time_end": available_time_end,
        "hourly_rate": hourly_rate, "phone": phone, "bio": bio,
    }

    def fail(msg: str):
        return render(request, "signup_nutritionist.html", user, error=msg, form=form_data)

    if len(password) < 8:
        return fail("비밀번호는 8자 이상이어야 합니다.")
    if password != password_confirm:
        return fail("비밀번호가 서로 일치하지 않습니다.")
    if crud.get_user_by_email(db, email):
        return fail(f"이미 가입된 이메일입니다: {email}")
    if crud.get_nutritionist_by_email(db, email):
        return fail(f"이미 등록된 이메일입니다: {email}")
    if crud.get_nutritionist_by_license(db, license_number):
        return fail(f"이미 등록된 면허번호입니다: {license_number}")
    if not available_days:
        return fail("가능 요일을 하나 이상 선택해주세요.")

    try:
        t_start, t_end = parse_time_range(available_time_start, available_time_end)
    except ValueError as e:
        return fail(str(e))

    account = crud.create_user(
        db, email=email, password_hash=hash_password(password),
        role="nutritionist", name=name, phone=phone,
    )
    crud.create_nutritionist(
        db,
        name=name,
        license_number=license_number,
        specialty=specialty,
        region=region,
        available_days=available_days,
        available_time_start=t_start,
        available_time_end=t_end,
        hourly_rate=hourly_rate,
        email=account.email,
        phone=phone,
        bio=bio or None,
        user_id=account.id,
    )
    request.session["user_id"] = account.id
    return RedirectResponse(url="/me?welcome=1", status_code=303)


@app.get("/signup/company", response_class=HTMLResponse)
def signup_company_form(
    request: Request,
    user: Optional[models.User] = Depends(current_user),
):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return render(request, "signup_company.html", user, error=None, form={})


@app.post("/signup/company", response_class=HTMLResponse)
def signup_company(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    company_name: str = Form(...),
    contact_name: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    form_data = {
        "email": email, "company_name": company_name,
        "contact_name": contact_name, "phone": phone,
    }

    def fail(msg: str):
        return render(request, "signup_company.html", user, error=msg, form=form_data)

    if len(password) < 8:
        return fail("비밀번호는 8자 이상이어야 합니다.")
    if password != password_confirm:
        return fail("비밀번호가 서로 일치하지 않습니다.")
    if crud.get_user_by_email(db, email):
        return fail(f"이미 가입된 이메일입니다: {email}")

    account = crud.create_user(
        db, email=email, password_hash=hash_password(password),
        role="company", name=contact_name, phone=phone, company_name=company_name,
    )
    request.session["user_id"] = account.id
    return RedirectResponse(url="/companies/request?welcome=1", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    next: str = "/",
    user: Optional[models.User] = Depends(current_user),
):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return render(request, "login.html", user, error=None, next=next)


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/"),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    account = crud.get_user_by_email(db, email)
    if not account or not verify_password(password, account.password_hash):
        return render(
            request, "login.html", user,
            error="이메일 또는 비밀번호가 올바르지 않습니다.", next=next,
        )
    request.session["user_id"] = account.id
    if not next.startswith("/"):
        next = "/"
    return RedirectResponse(url=next, status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


# ─── 영양사 ───────────────────────────────────────────────────────────────────

@app.get("/nutritionists", response_class=HTMLResponse)
def nutritionist_list(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    nutritionists = crud.get_nutritionists(db)
    return render(request, "nutritionist_list.html", user, nutritionists=nutritionists)


# 기존 등록 URL은 회원가입으로 안내
@app.get("/nutritionists/register")
def nutritionist_register_redirect():
    return RedirectResponse(url="/signup/nutritionist", status_code=303)


@app.get("/me", response_class=HTMLResponse)
def my_profile(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user:
        return login_redirect("/me")
    if user.role != "nutritionist":
        return RedirectResponse(url="/companies/my", status_code=303)
    profile = crud.get_nutritionist_by_user(db, user.id)
    if not profile:
        return RedirectResponse(url="/signup/nutritionist", status_code=303)
    bookings = crud.get_bookings_for_nutritionist(db, profile.id)
    return render(
        request, "my_profile.html", user,
        profile=profile, bookings=bookings, error=None,
    )


@app.post("/me", response_class=HTMLResponse)
def my_profile_update(
    request: Request,
    specialty: str = Form(...),
    region: str = Form(...),
    available_days: List[str] = Form(default=[]),
    available_time_start: str = Form(...),
    available_time_end: str = Form(...),
    hourly_rate: int = Form(...),
    phone: str = Form(...),
    bio: Optional[str] = Form(default=None),
    is_active: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user or user.role != "nutritionist":
        return login_redirect("/me")
    profile = crud.get_nutritionist_by_user(db, user.id)
    if not profile:
        return RedirectResponse(url="/signup/nutritionist", status_code=303)

    def fail(msg: str):
        bookings = crud.get_bookings_for_nutritionist(db, profile.id)
        return render(
            request, "my_profile.html", user,
            profile=profile, bookings=bookings, error=msg,
        )

    if not available_days:
        return fail("가능 요일을 하나 이상 선택해주세요.")
    try:
        t_start, t_end = parse_time_range(available_time_start, available_time_end)
    except ValueError as e:
        return fail(str(e))

    crud.update_nutritionist_profile(
        db, profile,
        specialty=specialty,
        region=region,
        available_days=available_days,
        available_time_start=t_start,
        available_time_end=t_end,
        hourly_rate=hourly_rate,
        phone=phone,
        bio=bio or None,
        is_active=bool(is_active),
    )
    return RedirectResponse(url="/me?saved=1", status_code=303)


# ─── 기업 수요 ────────────────────────────────────────────────────────────────

@app.get("/companies/request", response_class=HTMLResponse)
def company_request_form(
    request: Request,
    user: Optional[models.User] = Depends(current_user),
):
    if not user:
        return login_redirect("/companies/request")
    if user.role != "company":
        return RedirectResponse(url="/me", status_code=303)
    return render(request, "company_request.html", user, error=None)


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
    user: Optional[models.User] = Depends(current_user),
):
    if not user or user.role != "company":
        return login_redirect("/companies/request")

    if not preferred_days:
        return render(
            request, "company_request.html", user,
            error="희망 요일을 하나 이상 선택해주세요.",
        )

    try:
        t_start, t_end = parse_time_range(preferred_time_start, preferred_time_end)
    except ValueError as e:
        return render(request, "company_request.html", user, error=str(e))

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
        user_id=user.id,
    )

    # 매칭 즉시 실행
    crud.run_matching(company_req.id, db)

    return RedirectResponse(
        url=f"/matching/{company_req.id}?status=success",
        status_code=303
    )


@app.get("/companies/my", response_class=HTMLResponse)
def my_requests(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user:
        return login_redirect("/companies/my")
    if user.role != "company":
        return RedirectResponse(url="/me", status_code=303)
    requests_ = crud.get_company_requests_by_user(db, user.id)
    return render(request, "my_requests.html", user, requests=requests_)


# ─── 매칭 결과 ────────────────────────────────────────────────────────────────

@app.get("/matching/{request_id}", response_class=HTMLResponse)
def matching_result(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    company_request = crud.get_company_request(db, request_id)
    if not company_request:
        return RedirectResponse(url="/", status_code=303)

    # 본인 신청 건만 열람 가능 (레거시 익명 데이터는 로그인한 기업 회원에게 허용)
    if not user:
        return login_redirect(f"/matching/{request_id}")
    if company_request.user_id is not None and company_request.user_id != user.id:
        return RedirectResponse(url="/", status_code=303)

    results = crud.get_match_results(db, request_id)

    return render(
        request, "matching_result.html", user,
        company_request=company_request,
        results=results,
        all_days=ALL_DAYS,
        day_labels=DAY_LABELS,
    )


# ─── 예약 ─────────────────────────────────────────────────────────────────────

@app.post("/bookings/create")
def create_booking(
    request: Request,
    match_result_id: int = Form(...),
    redirect_to: str = Form(default="/bookings"),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user or user.role != "company":
        return login_redirect("/bookings")
    mr = db.query(models.MatchResult).filter(
        models.MatchResult.id == match_result_id
    ).first()
    if not mr:
        return RedirectResponse(url="/", status_code=303)
    req = crud.get_company_request(db, mr.request_id)
    if req.user_id is not None and req.user_id != user.id:
        return RedirectResponse(url="/", status_code=303)
    crud.create_booking(db, match_result_id)
    if not redirect_to.startswith("/"):
        redirect_to = "/bookings"
    return RedirectResponse(url=redirect_to, status_code=303)


@app.get("/bookings", response_class=HTMLResponse)
def booking_list(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user:
        return login_redirect("/bookings")
    if user.role == "company":
        bookings = crud.get_bookings_for_company_user(db, user.id)
    else:
        profile = crud.get_nutritionist_by_user(db, user.id)
        bookings = crud.get_bookings_for_nutritionist(db, profile.id) if profile else []
    return render(request, "booking_list.html", user, bookings=bookings)


def _authorize_booking_action(
    db: Session, user: Optional[models.User], booking_id: int, action: str
) -> Optional[models.Booking]:
    """예약 상태 변경 권한 확인. 권한이 없으면 None."""
    if not user:
        return None
    b = crud.get_booking(db, booking_id)
    if not b:
        return None
    if user.role == "nutritionist":
        profile = crud.get_nutritionist_by_user(db, user.id)
        is_owner = profile is not None and b.nutritionist_id == profile.id
        # 영양사: 확정/완료/취소 모두 가능
        return b if is_owner else None
    if user.role == "company":
        req = crud.get_company_request(db, b.request_id)
        is_owner = req is not None and req.user_id == user.id
        # 기업: 취소만 가능
        return b if (is_owner and action == "cancel") else None
    return None


@app.post("/bookings/{booking_id}/confirm")
def confirm_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not _authorize_booking_action(db, user, booking_id, "confirm"):
        return RedirectResponse(url="/bookings", status_code=303)
    crud.update_booking_status(db, booking_id, "confirmed")
    return RedirectResponse(url="/bookings?msg=예약이+확정되었습니다", status_code=303)


@app.post("/bookings/{booking_id}/complete")
def complete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not _authorize_booking_action(db, user, booking_id, "complete"):
        return RedirectResponse(url="/bookings", status_code=303)
    crud.update_booking_status(db, booking_id, "completed")
    return RedirectResponse(url="/bookings?msg=서비스가+완료처리되었습니다", status_code=303)


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not _authorize_booking_action(db, user, booking_id, "cancel"):
        return RedirectResponse(url="/bookings", status_code=303)
    crud.update_booking_status(db, booking_id, "cancelled")
    return RedirectResponse(url="/bookings?msg=예약이+취소되었습니다", status_code=303)


# ─── 샘플 데이터 (운영에서는 ENABLE_SEED=1 일 때만 동작) ─────────────────────────

@app.get("/seed", response_class=HTMLResponse)
def seed(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if os.environ.get("ENABLE_SEED") != "1":
        return RedirectResponse(url="/", status_code=303)
    inserted = crud.seed_nutritionists(db)
    total = crud.count_nutritionists(db)
    return render(
        request, "index.html", user,
        nutritionist_count=total,
        match_count=crud.count_match_results(db),
        company_count=crud.count_company_requests(db),
        seed_msg=f"샘플 영양사 {inserted}명 추가 완료 (전체 {total}명)",
    )
