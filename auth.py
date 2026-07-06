"""비밀번호 해싱 및 현재 로그인 사용자 조회."""
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

import models
from database import get_db

PBKDF2_ITERATIONS = 260_000


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
