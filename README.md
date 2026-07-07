# NutriMatch — 기업 맞춤 영양사 매칭 플랫폼

전문 영양사와 기업을 연결하는 매칭 서비스. FastAPI + SQLAlchemy + Jinja2.

배포: https://nutrimatch-t8rm.onrender.com/ (Render, PostgreSQL)

## 주요 기능

- **회원가입/로그인**: 영양사·기업 역할별 계정 (세션 쿠키, PBKDF2 비밀번호 해싱)
- **면허 검증(관리자 승인제)**: 영양사는 가입 시 면허번호 형식 검증 → 승인 대기 → 관리자 승인 후 목록·매칭 노출. 반려 시 면허번호 재제출 가능
- **영양사**: 가입 시 프로필(전문분야·지역·일정·요금) 등록 → `/me`에서 수정, 매칭 활성화 on/off
- **기업**: 서비스 수요 등록 → 지역 40 + 전문분야 30 + 일정 20 + 예산 10점 기준 자동 매칭 (상위 5명 추천)
- **예약**: 기업이 예약 신청 → 영양사가 확정/완료 처리, 기업은 취소 가능
- **연락처 보호**: 양측 연락처는 예약 확정 후에만 상호 공개
- **비밀번호 재설정**: 서명 토큰(1시간 유효·1회용) + SMTP 이메일 발송. SMTP 미설정 시 관리자가 `/admin`에서 링크 직접 발급
- **관리자 페이지(`/admin`)**: 통계, 면허 승인/반려 큐, 회원 관리, 재설정 링크 발급, 최근 예약

## 로컬 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload   # SQLite(nutrition_platform.db) 자동 사용
```

환경변수:

| 이름 | 설명 |
|---|---|
| `DATABASE_URL` | 없으면 로컬 SQLite. Render에서는 PostgreSQL 자동 주입 |
| `SECRET_KEY` | 세션·재설정 토큰 서명 키. 운영에서는 반드시 설정 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | 설정 시 시작할 때 관리자 계정 자동 생성 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | 비밀번호 재설정 메일 발송 (선택). Gmail은 앱 비밀번호 사용, PORT 587 |
| `ENABLE_SEED` | `1`일 때만 `/seed` (샘플 영양사 8명) 동작. 운영에서는 비활성 |

## 구조

- `main.py` — 라우트(인증·권한 가드 포함), 구 스키마 자동 마이그레이션, 관리자 계정 부트스트랩
- `auth.py` — 비밀번호 해싱, 현재 사용자 의존성, 재설정 토큰
- `emailer.py` — SMTP 발송 (미설정 시 건너뜀)
- `models.py` — User / Nutritionist / CompanyRequest / MatchResult / Booking
- `crud.py` — DB 조회·매칭 알고리즘
- `templates/` — Jinja2 (공용 네비게이션: `partials/_nav.html`)
