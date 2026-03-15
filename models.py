import json
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Integer, String, Text, Time, UniqueConstraint
)
from sqlalchemy.orm import relationship

from database import Base

# --- Enum 상수 ---

SPECIALTY_ENUM = Enum("clinical", "sports", "elderly", "pediatric", name="specialty_enum")

REGION_ENUM = Enum(
    "seoul", "gyeonggi", "incheon", "busan", "daegu",
    "gwangju", "daejeon", "ulsan", "sejong", "gangwon",
    "chungbuk", "chungnam", "jeonbuk", "jeonnam",
    "gyeongbuk", "gyeongnam", "jeju",
    name="region_enum"
)

SPECIALTY_ANY_ENUM = Enum(
    "clinical", "sports", "elderly", "pediatric", "any",
    name="specialty_any_enum"
)

# --- 한국어 레이블 매핑 ---

SPECIALTY_LABELS = {
    "clinical": "임상영양",
    "sports": "스포츠영양",
    "elderly": "노인영양",
    "pediatric": "소아영양",
    "any": "분야 무관",
}

REGION_LABELS = {
    "seoul": "서울",
    "gyeonggi": "경기",
    "incheon": "인천",
    "busan": "부산",
    "daegu": "대구",
    "gwangju": "광주",
    "daejeon": "대전",
    "ulsan": "울산",
    "sejong": "세종",
    "gangwon": "강원",
    "chungbuk": "충북",
    "chungnam": "충남",
    "jeonbuk": "전북",
    "jeonnam": "전남",
    "gyeongbuk": "경북",
    "gyeongnam": "경남",
    "jeju": "제주",
}

COMPANY_SIZE_LABELS = {
    "small": "소기업 (50인 미만)",
    "medium": "중기업 (50~300인)",
    "large": "대기업 (300인 이상)",
}

SERVICE_TYPE_LABELS = {
    "group_education": "집단 교육",
    "individual_counseling": "개인 상담",
    "both": "교육 + 상담",
}

BOOKING_STATUS_LABELS = {
    "pending": "신청 대기",
    "confirmed": "예약 확정",
    "completed": "완료",
    "cancelled": "취소",
}

DAY_LABELS = {
    "mon": "월", "tue": "화", "wed": "수",
    "thu": "목", "fri": "금", "sat": "토", "sun": "일",
}

ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# --- 모델 ---

class Nutritionist(Base):
    __tablename__ = "nutritionists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    license_number = Column(String(20), unique=True, nullable=False)
    specialty = Column(SPECIALTY_ENUM, nullable=False)
    region = Column(REGION_ENUM, nullable=False)
    available_days = Column(String(100), nullable=False)  # JSON: ["mon","wed"]
    available_time_start = Column(Time, nullable=False)
    available_time_end = Column(Time, nullable=False)
    hourly_rate = Column(Integer, nullable=False)
    bio = Column(Text, nullable=True)
    email = Column(String(100), unique=True, nullable=False)
    phone = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    match_results = relationship("MatchResult", back_populates="nutritionist")
    bookings = relationship("Booking", back_populates="nutritionist")

    @property
    def available_days_list(self):
        return json.loads(self.available_days)

    @property
    def specialty_label(self):
        return SPECIALTY_LABELS.get(self.specialty, self.specialty)

    @property
    def region_label(self):
        return REGION_LABELS.get(self.region, self.region)


class CompanyRequest(Base):
    __tablename__ = "company_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(100), nullable=False)
    company_size = Column(
        Enum("small", "medium", "large", name="company_size_enum"), nullable=False
    )
    service_type = Column(
        Enum("group_education", "individual_counseling", "both", name="service_type_enum"),
        nullable=False
    )
    preferred_region = Column(REGION_ENUM, nullable=False)
    budget_per_hour = Column(Integer, nullable=False)
    required_specialty = Column(SPECIALTY_ANY_ENUM, nullable=False)
    contact_name = Column(String(50), nullable=False)
    contact_email = Column(String(100), nullable=False)
    contact_phone = Column(String(20), nullable=False)
    preferred_days = Column(String(100), nullable=False)  # JSON
    preferred_time_start = Column(Time, nullable=False)
    preferred_time_end = Column(Time, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    match_results = relationship("MatchResult", back_populates="request")
    bookings = relationship("Booking", back_populates="request")

    @property
    def preferred_days_list(self):
        return json.loads(self.preferred_days)

    @property
    def region_label(self):
        return REGION_LABELS.get(self.preferred_region, self.preferred_region)

    @property
    def specialty_label(self):
        return SPECIALTY_LABELS.get(self.required_specialty, self.required_specialty)

    @property
    def service_type_label(self):
        return SERVICE_TYPE_LABELS.get(self.service_type, self.service_type)

    @property
    def company_size_label(self):
        return COMPANY_SIZE_LABELS.get(self.company_size, self.company_size)


class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("company_requests.id"), nullable=False)
    nutritionist_id = Column(Integer, ForeignKey("nutritionists.id"), nullable=False)
    total_score = Column(Integer, nullable=False)
    region_score = Column(Integer, nullable=False)
    specialty_score = Column(Integer, nullable=False)
    availability_score = Column(Integer, nullable=False)
    budget_score = Column(Integer, nullable=False)
    rank = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    request = relationship("CompanyRequest", back_populates="match_results")
    nutritionist = relationship("Nutritionist", back_populates="match_results")
    booking = relationship("Booking", back_populates="match_result", uselist=False)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_result_id = Column(
        Integer, ForeignKey("match_results.id"), unique=True, nullable=False
    )
    request_id = Column(Integer, ForeignKey("company_requests.id"), nullable=False)
    nutritionist_id = Column(Integer, ForeignKey("nutritionists.id"), nullable=False)
    status = Column(
        Enum("pending", "confirmed", "completed", "cancelled", name="booking_status_enum"),
        default="pending", nullable=False
    )
    session_date = Column(Date, nullable=True)
    session_time_start = Column(Time, nullable=True)
    session_time_end = Column(Time, nullable=True)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    match_result = relationship("MatchResult", back_populates="booking")
    request = relationship("CompanyRequest", back_populates="bookings")
    nutritionist = relationship("Nutritionist", back_populates="bookings")

    @property
    def status_label(self):
        return BOOKING_STATUS_LABELS.get(self.status, self.status)
