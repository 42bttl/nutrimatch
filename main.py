import os
import re
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
import emailer
import models
from auth import (
    SECRET_KEY,
    current_user,
    hash_password,
    make_reset_token,
    verify_password,
    verify_reset_token,
)
from database import Base, SessionLocal, engine, get_db
from models import ALL_DAYS, DAY_LABELS, REGION_LABELS, SPECIALTY_LABELS

# ─── 앱 초기화 ────────────────────────────────────────────────────────────────

app = FastAPI(title="NutriMatch — 영양사 매칭 플랫폼")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=60 * 60 * 24 * 14,  # 2주
    same_site="lax",
)

# DB 테이블 생성
Base.metadata.create_all(bind=engine)


def _migrate_legacy_tables():
    """기존 배포 DB에 새 컬럼이 없으면 추가한다."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in ("nutritionists", "company_requests"):
            if table not in inspector.get_table_names():
                continue
            cols = [c["name"] for c in inspector.get_columns(table)]
            if "user_id" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
        # 면허 검증 상태 — 기존 등록 영양사는 verified로 이관 (서비스 중단 방지)
        nut_cols = [c["name"] for c in inspector.get_columns("nutritionists")]
        if "verification_status" not in nut_cols:
            conn.execute(text(
                "ALTER TABLE nutritionists ADD COLUMN verification_status VARCHAR(20)"
            ))
            conn.execute(text(
                "UPDATE nutritionists SET verification_status = 'verified' "
                "WHERE verification_status IS NULL"
            ))


def _ensure_admin():
    """환경변수 ADMIN_EMAIL / ADMIN_PASSWORD가 설정돼 있으면 관리자 계정 생성."""
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not email or not password:
        return
    db = SessionLocal()
    try:
        if not crud.get_user_by_email(db, email):
            crud.create_user(
                db, email=email, password_hash=hash_password(password),
                role="admin", name="관리자",
            )
    finally:
        db.close()


_migrate_legacy_tables()
_ensure_admin()

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


# 면허번호 형식: 영문/숫자/하이픈 4~20자, 숫자 3개 이상 포함 (예: RD-2024-00001, 12345)
LICENSE_RE = re.compile(r"^[A-Za-z0-9\-]{4,20}$")


def valid_license_format(license_number: str) -> bool:
    return (
        bool(LICENSE_RE.match(license_number))
        and sum(ch.isdigit() for ch in license_number) >= 3
    )


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
    if not valid_license_format(license_number):
        return fail("면허번호 형식이 올바르지 않습니다. 영문/숫자/하이픈 4~20자로 입력해주세요. (예: RD-2024-00001)")
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


# ─── 비밀번호 재설정 ───────────────────────────────────────────────────────────

@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(
    request: Request,
    user: Optional[models.User] = Depends(current_user),
):
    return render(
        request, "forgot_password.html", user,
        message=None, error=None, smtp_enabled=emailer.smtp_configured(),
    )


@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not emailer.smtp_configured():
        return render(
            request, "forgot_password.html", user,
            message=None, smtp_enabled=False,
            error="이메일 발송이 아직 설정되지 않았습니다. 관리자에게 문의해주세요.",
        )

    account = crud.get_user_by_email(db, email)
    if account:
        token = make_reset_token(account)
        base_url = str(request.base_url).rstrip("/")
        reset_link = f"{base_url}/reset-password?token={token}"
        emailer.send_email(
            account.email,
            "[NutriMatch] 비밀번호 재설정 안내",
            f"안녕하세요, {account.name}님.\n\n"
            f"아래 링크에서 비밀번호를 재설정할 수 있습니다. (1시간 동안 유효)\n\n"
            f"{reset_link}\n\n"
            f"본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.\n\n— NutriMatch",
        )
    # 계정 존재 여부와 무관하게 같은 메시지 (이메일 존재 여부 노출 방지)
    return render(
        request, "forgot_password.html", user,
        error=None, smtp_enabled=True,
        message=f"{email} 로 재설정 링크를 보냈습니다. 메일함을 확인해주세요. (1시간 유효)",
    )


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_form(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    account = verify_reset_token(token, db)
    if not account:
        return render(
            request, "reset_password.html", user,
            token=None, error="링크가 만료되었거나 올바르지 않습니다. 재설정을 다시 요청해주세요.",
        )
    return render(request, "reset_password.html", user, token=token, error=None)


@app.post("/reset-password", response_class=HTMLResponse)
def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    account = verify_reset_token(token, db)
    if not account:
        return render(
            request, "reset_password.html", user,
            token=None, error="링크가 만료되었거나 올바르지 않습니다. 재설정을 다시 요청해주세요.",
        )
    if len(password) < 8:
        return render(
            request, "reset_password.html", user,
            token=token, error="비밀번호는 8자 이상이어야 합니다.",
        )
    if password != password_confirm:
        return render(
            request, "reset_password.html", user,
            token=token, error="비밀번호가 서로 일치하지 않습니다.",
        )
    crud.update_password(db, account, hash_password(password))
    request.session.clear()
    return RedirectResponse(url="/login?reset=1", status_code=303)


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
    license_number: Optional[str] = Form(default=None),
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

    # 미인증(반려 포함) 상태에서만 면허번호 재제출 가능 → 재승인 대기
    if (
        license_number
        and license_number != profile.license_number
        and profile.verification_status != "verified"
    ):
        if not valid_license_format(license_number):
            return fail("면허번호 형식이 올바르지 않습니다. 영문/숫자/하이픈 4~20자로 입력해주세요.")
        existing = crud.get_nutritionist_by_license(db, license_number)
        if existing and existing.id != profile.id:
            return fail(f"이미 등록된 면허번호입니다: {license_number}")
        crud.update_license_number(db, profile, license_number)

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
    if (
        company_request.user_id is not None
        and company_request.user_id != user.id
        and user.role != "admin"
    ):
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
    if user.role == "admin":
        bookings = crud.get_bookings(db)
    elif user.role == "company":
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
    if user.role == "admin":
        return b
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


# ─── 관리자 ───────────────────────────────────────────────────────────────────

def _admin_context(db: Session, **extra):
    users = crud.get_users(db)
    ctx = {
        "pending_nutritionists": crud.get_pending_nutritionists(db),
        "all_nutritionists": crud.get_all_nutritionists(db),
        "users": users,
        "stats": {
            "nutritionist_users": sum(1 for u in users if u.role == "nutritionist"),
            "company_users": sum(1 for u in users if u.role == "company"),
            "verified": crud.count_nutritionists(db),
            "requests": crud.count_company_requests(db),
            "bookings": len(crud.get_bookings(db)),
        },
        "recent_bookings": crud.get_bookings(db)[:10],
        "reset_link": None,
        "reset_target": None,
    }
    ctx.update(extra)
    return ctx


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user:
        return login_redirect("/admin")
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    return render(request, "admin.html", user, **_admin_context(db))


@app.post("/admin/nutritionists/{nutritionist_id}/verify")
def admin_verify_nutritionist(
    nutritionist_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user or user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    n = crud.get_nutritionist(db, nutritionist_id)
    if n:
        crud.set_verification_status(db, n, "verified")
        if n.email:
            emailer.send_email(
                n.email,
                "[NutriMatch] 면허 인증이 완료되었습니다",
                f"{n.name}님, 면허 인증이 완료되어 이제 기업 매칭에 노출됩니다.\n\n— NutriMatch",
            )
    return RedirectResponse(url="/admin?msg=승인+완료", status_code=303)


@app.post("/admin/nutritionists/{nutritionist_id}/reject")
def admin_reject_nutritionist(
    nutritionist_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user or user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    n = crud.get_nutritionist(db, nutritionist_id)
    if n:
        crud.set_verification_status(db, n, "rejected")
        if n.email:
            emailer.send_email(
                n.email,
                "[NutriMatch] 면허 확인이 필요합니다",
                f"{n.name}님, 제출하신 면허번호({n.license_number})를 확인하지 못했습니다.\n"
                f"내 프로필에서 면허번호를 다시 확인해 제출해주세요.\n\n— NutriMatch",
            )
    return RedirectResponse(url="/admin?msg=반려+처리되었습니다", status_code=303)


@app.post("/admin/users/{user_id}/reset-link", response_class=HTMLResponse)
def admin_make_reset_link(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(current_user),
):
    if not user or user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    target = crud.get_user(db, user_id)
    if not target:
        return RedirectResponse(url="/admin", status_code=303)
    token = make_reset_token(target)
    base_url = str(request.base_url).rstrip("/")
    reset_link = f"{base_url}/reset-password?token={token}"
    # SMTP가 설정돼 있으면 메일도 발송
    emailed = emailer.send_email(
        target.email,
        "[NutriMatch] 비밀번호 재설정 안내",
        f"안녕하세요, {target.name}님.\n\n"
        f"아래 링크에서 비밀번호를 재설정할 수 있습니다. (1시간 동안 유효)\n\n{reset_link}\n\n— NutriMatch",
    )
    return render(
        request, "admin.html", user,
        **_admin_context(
            db,
            reset_link=reset_link,
            reset_target=target.email,
            reset_emailed=emailed,
        ),
    )


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
