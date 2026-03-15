import json
from datetime import datetime, time
from typing import List, Optional

from sqlalchemy.orm import Session

from models import Booking, CompanyRequest, MatchResult, Nutritionist


# ─── 영양사 CRUD ──────────────────────────────────────────────────────────────

def create_nutritionist(
    db: Session,
    name: str,
    license_number: str,
    specialty: str,
    region: str,
    available_days: List[str],
    available_time_start: time,
    available_time_end: time,
    hourly_rate: int,
    email: str,
    phone: str,
    bio: Optional[str] = None,
) -> Nutritionist:
    n = Nutritionist(
        name=name,
        license_number=license_number,
        specialty=specialty,
        region=region,
        available_days=json.dumps(available_days),
        available_time_start=available_time_start,
        available_time_end=available_time_end,
        hourly_rate=hourly_rate,
        email=email,
        phone=phone,
        bio=bio,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def get_nutritionist(db: Session, nutritionist_id: int) -> Optional[Nutritionist]:
    return db.query(Nutritionist).filter(Nutritionist.id == nutritionist_id).first()


def get_nutritionists(db: Session, skip: int = 0, limit: int = 100) -> List[Nutritionist]:
    return (
        db.query(Nutritionist)
        .filter(Nutritionist.is_active == True)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_nutritionist_by_license(db: Session, license_number: str) -> Optional[Nutritionist]:
    return db.query(Nutritionist).filter(Nutritionist.license_number == license_number).first()


def get_nutritionist_by_email(db: Session, email: str) -> Optional[Nutritionist]:
    return db.query(Nutritionist).filter(Nutritionist.email == email).first()


def count_nutritionists(db: Session) -> int:
    return db.query(Nutritionist).filter(Nutritionist.is_active == True).count()


# ─── 기업 수요 CRUD ───────────────────────────────────────────────────────────

def create_company_request(
    db: Session,
    company_name: str,
    company_size: str,
    service_type: str,
    preferred_region: str,
    budget_per_hour: int,
    required_specialty: str,
    contact_name: str,
    contact_email: str,
    contact_phone: str,
    preferred_days: List[str],
    preferred_time_start: time,
    preferred_time_end: time,
    notes: Optional[str] = None,
) -> CompanyRequest:
    r = CompanyRequest(
        company_name=company_name,
        company_size=company_size,
        service_type=service_type,
        preferred_region=preferred_region,
        budget_per_hour=budget_per_hour,
        required_specialty=required_specialty,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        preferred_days=json.dumps(preferred_days),
        preferred_time_start=preferred_time_start,
        preferred_time_end=preferred_time_end,
        notes=notes,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def get_company_request(db: Session, request_id: int) -> Optional[CompanyRequest]:
    return db.query(CompanyRequest).filter(CompanyRequest.id == request_id).first()


def get_company_requests(db: Session, skip: int = 0, limit: int = 100) -> List[CompanyRequest]:
    return db.query(CompanyRequest).order_by(CompanyRequest.created_at.desc()).offset(skip).limit(limit).all()


def count_company_requests(db: Session) -> int:
    return db.query(CompanyRequest).count()


# ─── 매칭 알고리즘 ─────────────────────────────────────────────────────────────

def _score_region(nutritionist: Nutritionist, request: CompanyRequest) -> int:
    return 40 if nutritionist.region == request.preferred_region else 0


def _score_specialty(nutritionist: Nutritionist, request: CompanyRequest) -> int:
    if request.required_specialty == "any":
        return 30
    return 30 if nutritionist.specialty == request.required_specialty else 0


def _score_availability(nutritionist: Nutritionist, request: CompanyRequest) -> int:
    req_days = set(json.loads(request.preferred_days))
    nut_days = set(json.loads(nutritionist.available_days))
    overlap_days = req_days & nut_days

    if not req_days:
        return 0

    day_ratio = len(overlap_days) / len(req_days)

    # 시간대 겹침 확인
    time_start = max(nutritionist.available_time_start, request.preferred_time_start)
    time_end = min(nutritionist.available_time_end, request.preferred_time_end)
    time_overlap = time_start < time_end

    if not time_overlap or not overlap_days:
        return 0
    if day_ratio >= 0.5:
        return 20
    return 10


def _score_budget(nutritionist: Nutritionist, request: CompanyRequest) -> int:
    if nutritionist.hourly_rate <= request.budget_per_hour:
        return 10
    if nutritionist.hourly_rate <= request.budget_per_hour * 1.2:
        return 5
    return 0


def run_matching(request_id: int, db: Session) -> List[MatchResult]:
    """기업 수요에 대한 영양사 매칭 실행 후 상위 5개 결과 반환."""
    request = db.query(CompanyRequest).filter(CompanyRequest.id == request_id).first()
    if not request:
        return []

    # 기존 매칭 결과 삭제 (재실행 지원)
    db.query(MatchResult).filter(MatchResult.request_id == request_id).delete()
    db.flush()

    nutritionists = db.query(Nutritionist).filter(Nutritionist.is_active == True).all()

    scored = []
    for n in nutritionists:
        region_score = _score_region(n, request)
        specialty_score = _score_specialty(n, request)
        availability_score = _score_availability(n, request)
        budget_score = _score_budget(n, request)
        total = region_score + specialty_score + availability_score + budget_score
        scored.append((total, n.hourly_rate, n.created_at, n, region_score, specialty_score, availability_score, budget_score))

    # 정렬: 총점 내림차순, 요금 오름차순, 등록일 오름차순
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))

    results = []
    for rank, item in enumerate(scored, start=1):
        total, _, _, n, rs, ss, avs, bs = item
        mr = MatchResult(
            request_id=request_id,
            nutritionist_id=n.id,
            total_score=total,
            region_score=rs,
            specialty_score=ss,
            availability_score=avs,
            budget_score=bs,
            rank=rank,
        )
        db.add(mr)
        results.append(mr)

    db.commit()

    # 상위 5개만 relationship 로드 후 반환
    top5 = (
        db.query(MatchResult)
        .filter(MatchResult.request_id == request_id)
        .order_by(MatchResult.rank)
        .limit(5)
        .all()
    )
    return top5


def get_match_results(db: Session, request_id: int) -> List[MatchResult]:
    return (
        db.query(MatchResult)
        .filter(MatchResult.request_id == request_id)
        .order_by(MatchResult.rank)
        .limit(5)
        .all()
    )


def count_match_results(db: Session) -> int:
    return db.query(MatchResult).count()


# ─── 예약 CRUD ────────────────────────────────────────────────────────────────

def create_booking(db: Session, match_result_id: int) -> Optional[Booking]:
    mr = db.query(MatchResult).filter(MatchResult.id == match_result_id).first()
    if not mr:
        return None
    # 이미 예약된 경우 방지
    existing = db.query(Booking).filter(Booking.match_result_id == match_result_id).first()
    if existing:
        return existing

    b = Booking(
        match_result_id=match_result_id,
        request_id=mr.request_id,
        nutritionist_id=mr.nutritionist_id,
        status="pending",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def get_bookings(db: Session) -> List[Booking]:
    return db.query(Booking).order_by(Booking.created_at.desc()).all()


def get_booking(db: Session, booking_id: int) -> Optional[Booking]:
    return db.query(Booking).filter(Booking.id == booking_id).first()


def update_booking_status(db: Session, booking_id: int, new_status: str) -> Optional[Booking]:
    b = get_booking(db, booking_id)
    if not b:
        return None
    b.status = new_status
    b.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(b)
    return b


# ─── 샘플 데이터 ──────────────────────────────────────────────────────────────

SEED_NUTRITIONISTS = [
    {
        "name": "김지수",
        "license_number": "RD-2019-00142",
        "specialty": "clinical",
        "region": "seoul",
        "available_days": ["mon", "tue", "wed", "thu", "fri"],
        "available_time_start": time(9, 0),
        "available_time_end": time(18, 0),
        "hourly_rate": 80000,
        "email": "jisu.kim@example.com",
        "phone": "010-1234-5678",
        "bio": "서울대학교 병원 임상영양팀 5년 근무. 만성질환 영양관리 전문.",
    },
    {
        "name": "박현우",
        "license_number": "RD-2020-00287",
        "specialty": "sports",
        "region": "seoul",
        "available_days": ["mon", "wed", "fri", "sat"],
        "available_time_start": time(7, 0),
        "available_time_end": time(16, 0),
        "hourly_rate": 90000,
        "email": "hw.park@example.com",
        "phone": "010-2345-6789",
        "bio": "프로스포츠팀 전속 영양사 경력. 체중관리 및 운동 퍼포먼스 최적화 전문.",
    },
    {
        "name": "이미래",
        "license_number": "RD-2018-00093",
        "specialty": "elderly",
        "region": "gyeonggi",
        "available_days": ["tue", "thu", "fri"],
        "available_time_start": time(10, 0),
        "available_time_end": time(17, 0),
        "hourly_rate": 70000,
        "email": "mirae.lee@example.com",
        "phone": "010-3456-7890",
        "bio": "노인요양병원 7년 근무. 노인성 질환 맞춤 식이요법 전문.",
    },
    {
        "name": "정수아",
        "license_number": "RD-2021-00415",
        "specialty": "pediatric",
        "region": "busan",
        "available_days": ["mon", "tue", "wed", "thu"],
        "available_time_start": time(9, 0),
        "available_time_end": time(17, 0),
        "hourly_rate": 75000,
        "email": "sua.jung@example.com",
        "phone": "010-4567-8901",
        "bio": "소아과 전문 영양사. 성장기 영양관리 및 식이 알레르기 상담 전문.",
    },
    {
        "name": "최동훈",
        "license_number": "RD-2017-00058",
        "specialty": "clinical",
        "region": "gyeonggi",
        "available_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        "available_time_start": time(8, 0),
        "available_time_end": time(20, 0),
        "hourly_rate": 100000,
        "email": "dh.choi@example.com",
        "phone": "010-5678-9012",
        "bio": "대형 종합병원 임상영양팀장 역임. 당뇨, 심혈관 질환 영양 중재 전문.",
    },
    {
        "name": "한소연",
        "license_number": "RD-2022-00531",
        "specialty": "sports",
        "region": "incheon",
        "available_days": ["wed", "thu", "fri", "sat", "sun"],
        "available_time_start": time(13, 0),
        "available_time_end": time(21, 0),
        "hourly_rate": 85000,
        "email": "soyeon.han@example.com",
        "phone": "010-6789-0123",
        "bio": "피트니스 센터 전문 영양사. 체성분 개선 및 건강체중 관리 프로그램 운영.",
    },
    {
        "name": "오민준",
        "license_number": "RD-2016-00031",
        "specialty": "clinical",
        "region": "daegu",
        "available_days": ["mon", "tue", "wed", "thu", "fri"],
        "available_time_start": time(9, 0),
        "available_time_end": time(18, 0),
        "hourly_rate": 65000,
        "email": "minjun.oh@example.com",
        "phone": "010-7890-1234",
        "bio": "대구 지역 병원 10년 근무 베테랑 영양사. 집단 영양교육 프로그램 다수 운영.",
    },
    {
        "name": "윤채원",
        "license_number": "RD-2023-00612",
        "specialty": "pediatric",
        "region": "seoul",
        "available_days": ["mon", "wed", "fri"],
        "available_time_start": time(10, 0),
        "available_time_end": time(16, 0),
        "hourly_rate": 72000,
        "email": "chaewon.yun@example.com",
        "phone": "010-8901-2345",
        "bio": "소아 비만 및 편식 교정 전문. 아동 친화적 영양교육 프로그램 개발.",
    },
]


def seed_nutritionists(db: Session) -> int:
    """샘플 영양사 데이터 삽입. 이미 존재하는 면허번호는 건너뜀."""
    inserted = 0
    for data in SEED_NUTRITIONISTS:
        existing = get_nutritionist_by_license(db, data["license_number"])
        if existing:
            continue
        create_nutritionist(db, **data)
        inserted += 1
    return inserted
