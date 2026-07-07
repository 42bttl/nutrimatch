"""비밀번호 해싱, 현재 로그인 사용자 조회, 비밀번호 재설정 토큰."""
import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Depends, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

import models
from database import get_db

PBKDF2_ITERATIONS = 260_000
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
RESET_TOKEN_MAX_AGE = 3600  # 1시간


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iterations, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(check, digest)
    except (ValueError, AttributeError):
        return False


def _reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(SECRET_KEY, salt="password-reset")


def make_reset_token(user: models.User) -> str:
    # password_hash 일부를 포함해 비밀번호 변경 시 기존 토큰을 무효화 (1회용)
    return _reset_serializer().dumps(
        {"uid": user.id, "ph": user.password_hash[-12:]}
    )


def verify_reset_token(token: str, db: Session) -> Optional[models.User]:
    try:
        data = _reset_serializer().loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    user = db.query(models.User).filter(models.User.id == data.get("uid")).first()
    if not user or user.password_hash[-12:] != data.get("ph"):
        return None
    return user


def current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[models.User]:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        request.session.clear()
    return user
