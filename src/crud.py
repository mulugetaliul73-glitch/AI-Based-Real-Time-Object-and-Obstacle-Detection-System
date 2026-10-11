"""Database operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.auth import get_password_hash, verify_password
from src.models import Detection, User
from src.schemas import DetectionCreate, UserCreate


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, payload: UserCreate) -> User:
    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def save_detection(db: Session, user_id: int, payload: DetectionCreate) -> Detection:
    record = Detection(
        user_id=user_id,
        label=payload.label.strip(),
        confidence=payload.confidence,
        distance_m=payload.distance_m,
        direction=payload.direction or "unknown",
        danger_level=payload.danger_level.strip(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def save_detections(
    db: Session,
    user_id: int,
    detections: list[dict[str, Any]],
) -> list[Detection]:
    """Persist warning/danger detections for the authenticated user."""
    rows = [
        Detection(
            user_id=user_id,
            label=detection["label"],
            confidence=detection["confidence"],
            distance_m=detection.get("distance_m"),
            direction=detection["direction"],
            danger_level=detection["danger_level"],
        )
        for detection in detections
        if detection["danger_level"] != "safe"
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def list_detections(
    db: Session,
    user_id: int,
    limit: int = 50,
    danger_level: str | None = None,
) -> list[Detection]:
    stmt = (
        select(Detection)
        .where(Detection.user_id == user_id)
        .order_by(Detection.id.desc())
        .limit(limit)
    )
    if danger_level:
        stmt = stmt.where(Detection.danger_level == danger_level)
    return list(db.scalars(stmt))


def clear_detections(db: Session, user_id: int) -> int:
    result = db.execute(delete(Detection).where(Detection.user_id == user_id))
    db.commit()
    return result.rowcount or 0


def get_stats(db: Session, user_id: int) -> dict[str, Any]:
    total = db.scalar(
        select(func.count(Detection.id)).where(Detection.user_id == user_id)
    ) or 0
    by_label = dict(
        db.execute(
            select(Detection.label, func.count())
            .where(Detection.user_id == user_id)
            .group_by(Detection.label)
        ).all()
    )
    by_level = dict(
        db.execute(
            select(Detection.danger_level, func.count())
            .where(Detection.user_id == user_id)
            .group_by(Detection.danger_level)
        ).all()
    )
    return {"total": total, "by_label": by_label, "by_danger_level": by_level}
