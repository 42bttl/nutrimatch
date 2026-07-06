# NutriMatch — 기업 맞춤 영양사 매칭 플랫폼

전문 영양사와 기업을 연결하는 매칭 서비스. FastAPI + SQLAlchemy + Jinja2.

배포: https://nutrimatch-t8rm.onrender.com/ (Render, PostgreSQL)

## 주요 기능

- **회원가입/로그인**: 영양사·기업 역할별 계정 (세션 쿠키, PBKDF2 비밀번호 해싱)
- **영양사**: 가입 시 프로필(전문분야·지역·일정·요금) 등록 → `/me`에서 수정, 매칭 활성화 on/off
- **기업**: 서비스 수요 등록 → 지역 40 + 전문분야 30 + 일정 20 + 예산 10점 기준 자동 매칭 (상위 5명 추천)
- **예약**: 기업이 예약 신청 → 영양사가 확정/완료 처리, 기업은 취소 가능
- **연락처 보호**: 양측 연락처는 예약 확정 후에만 상호 공개

## 로컬 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload   # SQLite(nutrition_platform.db) 자동 사용
```

환경변수:

| 이름 | 설명 |
|---|---|
| `DATABASE_URL` | 없으면 로컬 SQLite. Render에서는 PostgreSQL 자동 주입 |
| `SECRET_KEY` | 세션 서명 키. 운영에서는 반드시 설정 (render.yaml에서 자동 생성) |
| `ENABLE_SEED` | `1`일 때만 `/seed` (샘플 영양사 8명) 동작. 운영에서는 비활성 |

## 구조

- `main.py` — 라우트(인증·권한 가드 포함) 및 구 스키마 자동 마이그레이션
- `auth.py` — 비밀번호 해싱, 현재 사용자 의존성
- `models.py` — User / Nutritionist / CompanyRequest / MatchResult / Booking
- `crud.py` — DB 조회·매칭 알고리즘
- `templates/` — Jinja2 (공용 네비게이션: `partials/_nav.html`)
