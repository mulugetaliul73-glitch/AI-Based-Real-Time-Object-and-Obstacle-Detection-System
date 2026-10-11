"""Database connection and session handling."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_SQLITE_URL = "sqlite:///./obstacle.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

if DATABASE_URL.startswith(("postgresql://", "postgres://")):
    DATABASE_URL = DATABASE_URL.replace("://", "+psycopg2://", 1)


def _build_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _fallback_to_sqlite() -> None:
    global DATABASE_URL, engine, SessionLocal
    DATABASE_URL = DEFAULT_SQLITE_URL
    engine = _build_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    global engine
    from src.models import Detection, User  # noqa: F401

    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        if DATABASE_URL.startswith(("postgresql", "postgres")):
            _fallback_to_sqlite()
        else:
            raise

    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "users" not in tables:
            return

        users_columns = {
            column["name"] for column in inspect(connection).get_columns("users")
        }
        if "password_hash" not in users_columns and "hashed_password" not in users_columns:
            raise RuntimeError(
                "Cannot migrate users table: neither password_hash nor hashed_password exists."
            )

        preparer = connection.dialect.identifier_preparer
        for old_name, new_name in (
            ("username", "name"),
            ("hashed_password", "password_hash"),
        ):
            if old_name in users_columns and new_name not in users_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE users RENAME COLUMN "
                    f"{preparer.quote(old_name)} TO {preparer.quote(new_name)}"
                )
                users_columns.remove(old_name)
                users_columns.add(new_name)

        if "name" not in users_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN name VARCHAR(120)")
            connection.exec_driver_sql(
                "UPDATE users SET name = email WHERE name IS NULL OR name = ''"
            )

        if "detections" in tables:
            detection_columns = {
                column["name"] for column in inspect(connection).get_columns("detections")
            }
            if "user_id" not in detection_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE detections ADD COLUMN user_id INTEGER "
                    "REFERENCES users(id)"
                )

            if "distance" in detection_columns and "distance_m" not in detection_columns:
                connection.execute(text("ALTER TABLE detections ADD COLUMN distance_m FLOAT"))
                connection.execute(text("UPDATE detections SET distance_m = distance"))
