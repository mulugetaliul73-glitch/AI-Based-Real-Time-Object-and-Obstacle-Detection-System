"""Pydantic request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DetectionItem(BaseModel):
    label: str
    confidence: float
    bbox: list[float]
    distance_m: float | None
    direction: str
    danger_level: str


class DetectResponse(BaseModel):
    width: int
    height: int
    detections: list[DetectionItem]
    message: str | None = None
    fallback_message: str | None = None
    count: int


class DetectionCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(default=0.0, ge=0, le=1)
    distance_m: Optional[float] = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("distance_m", "distance"),
    )
    direction: Optional[str] = Field(default=None, max_length=16)
    danger_level: str = Field(default="low", max_length=16)


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    label: str
    confidence: float
    distance_m: Optional[float]
    direction: str
    danger_level: str
    created_at: datetime


class StatsOut(BaseModel):
    total: int
    by_label: dict[str, int]
    by_danger_level: dict[str, int]
