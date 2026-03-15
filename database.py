import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 환경변수 DATABASE_URL이 있으면 PostgreSQL, 없으면 로컬 SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./nutrition_platform.db")

# Render는 postgres:// 로 제공하지만 SQLAlchemy는 postgresql:// 를 요구
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
