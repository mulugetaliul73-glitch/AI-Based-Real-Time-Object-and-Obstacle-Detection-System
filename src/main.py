"""
=============================================================================
 main.py — FastAPI Application
=============================================================================

 Project : AI-Based Real-Time Object and Obstacle Detection System
           for Visually Impaired People

 Features:
   • User registration & JWT login
   • YOLO object detection on uploaded images
   • Distance & danger-level estimation
   • Multi-language voice alerts (26 languages)
   • PostgreSQL persistence per user
=============================================================================
"""

from __future__ import annotations

import io
import logging
import os
import threading
import wave
from functools import lru_cache
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from src.ai.detector import DetectorUnavailable, ObstacleDetector
from src.ai.distance import enrich_detections
from src.ai.speech import build_message
from src.accessibility.battery import get_battery_monitor
from src.accessibility.location import describe_location, get_gps_from_image, reverse_geocode
from src.auth import create_access_token, get_current_user
from src.crud import (
    authenticate_user,
    clear_detections,
    create_user,
    get_stats as get_user_stats,
    list_detections,
    save_detection,
    save_detections,
)
from src.database import get_db, init_db
from src.models import User
from src.schemas import (
    DetectionCreate,
    DetectionItem,
    DetectionOut,
    DetectResponse,
    StatsOut,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)


# ─────────────────────────── App Setup ───────────────────────────
app = FastAPI(title="AI Obstacle Detection API")
detector = ObstacleDetector()

MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_TTS_TEXT_LENGTH = 200
logger = logging.getLogger(__name__)
_LOCAL_TTS_LOCK = threading.Lock()

# Languages your app accepts (must match keys in speech.py)
SUPPORTED_LANGUAGES = {
    "en", "am", "ti", "om", "so", "ar", "es", "fr", "pt", "de",
    "it", "ru", "zh", "ja", "ko", "hi", "sw", "tr", "vi", "id",
    "ur", "fa", "he", "pl", "nl", "uk",
}

LOCAL_TTS_MODELS = {
    "ti": "facebook/mms-tts-tir",
    "om": "facebook/mms-tts-orm",
    "so": "facebook/mms-tts-som",
}

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
get_battery_monitor().start()


@lru_cache(maxsize=len(LOCAL_TTS_MODELS))
def _load_local_tts_model(model_id: str):
    from transformers import AutoTokenizer, VitsModel

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = VitsModel.from_pretrained(model_id)
    model.eval()
    return tokenizer, model


@lru_cache(maxsize=1)
def _load_uroman():
    import uroman

    return uroman.Uroman()


def synthesize_local_tts(text: str, model_id: str) -> bytes:
    """Synthesize local-language speech and return 16-bit PCM WAV bytes."""
    import numpy as np
    import torch

    if model_id == LOCAL_TTS_MODELS["ti"]:
        text = _load_uroman().romanize_string(text, lcode="tir")

    with _LOCAL_TTS_LOCK:
        tokenizer, model = _load_local_tts_model(model_id)
        inputs = tokenizer(text, return_tensors="pt")
        with torch.inference_mode():
            output = model(**inputs)

    waveform = output.waveform[0].cpu().numpy()
    if waveform.size == 0 or not np.isfinite(waveform).all():
        raise ValueError("The local speech model returned invalid audio.")

    pcm = (np.clip(waveform, -1.0, 1.0) * 32767).astype("<i2")
    audio_buffer = io.BytesIO()
    with wave.open(audio_buffer, "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(model.config.sampling_rate)
        audio_file.writeframes(pcm.tobytes())
    return audio_buffer.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# HEALTH & ROOT
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/data")
async def get_data():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/health")
async def health_check():
    return {"status": "running"}


@app.get("/api/battery", tags=["Accessibility"])
def battery_status(current_user: User = Depends(get_current_user)):
    """Return the host device's current battery status."""
    del current_user
    return get_battery_monitor().get_status()


@app.get("/api/location/reverse", tags=["Accessibility"])
async def reverse_location(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    language: str = Query("en", min_length=2, max_length=16, pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$"),
    current_user: User = Depends(get_current_user),
):
    """Look up a human-readable place for coordinates supplied on demand."""
    del current_user
    address = await run_in_threadpool(reverse_geocode, latitude, longitude, language)
    description = (
        f"Your current location is {address}."
        if address
        else f"Place name unavailable. Your coordinates are latitude {latitude}, longitude {longitude}."
    )
    return {
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "description": description,
    }


@app.post("/api/location/from-image", tags=["Accessibility"])
async def location_from_image(
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Extract GPS coordinates from an authenticated image upload's EXIF."""
    del current_user
    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a JPEG, PNG, or WebP image.",
        )

    image_data = await image.read(MAX_IMAGE_BYTES + 1)
    if not image_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image is empty.",
        )
    if len(image_data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image is too large. Maximum size is 10 MiB.",
        )

    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp.write(image_data)
        tmp_path = tmp.name

    try:
        gps = get_gps_from_image(tmp_path)
        if not gps:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No GPS data in image.",
            )

        description = await run_in_threadpool(
            describe_location,
            gps["latitude"],
            gps["longitude"],
        )
        return {
            "latitude": gps["latitude"],
            "longitude": gps["longitude"],
            "description": description,
        }
    finally:
        os.unlink(tmp_path)


@app.get("/api/tts", tags=["Speech"])
def get_speech_audio(
    text: str = Query(..., min_length=1, max_length=MAX_TTS_TEXT_LENGTH),
    language: str = Query("en"),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Proxy short speech requests through the authenticated app origin."""
    del current_user
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported speech language.",
        )

    if language in LOCAL_TTS_MODELS:
        model_id = LOCAL_TTS_MODELS[language]
        try:
            audio_data = synthesize_local_tts(text, model_id)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            logger.exception("Local TTS synthesis failed for %s.", language)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Local speech for '{language}' is unavailable. "
                    "Check that the TTS dependencies and model download are available."
                ),
            ) from exc
        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Cache-Control": "no-store",
                "X-TTS-Provider": "local-mms",
            },
        )

    query = urlencode({"ie": "UTF-8", "client": "tw-ob", "tl": language, "q": text})
    request = Request(
        f"https://translate.google.com/translate_tts?{query}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urlopen(request, timeout=10) as upstream:
            content_type = upstream.headers.get_content_type()
            audio_data = upstream.read(2 * 1024 * 1024 + 1)
    except HTTPError as exc:
        if exc.code in {400, 404, 422}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Google Translate TTS does not support language '{language}'.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google Translate TTS returned an error.",
        ) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Speech provider could not be reached.",
        ) from exc

    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google Translate TTS returned a non-audio response.",
        )

    if not audio_data or len(audio_data) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Speech provider returned an invalid audio response.",
        )

    return Response(
        content=audio_data,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-TTS-Provider": "google"},
    )


@app.get("/")
async def root():
    return {
        "project": "AI-Based Real-Time Object and Obstacle Detection System",
        "for": "Visually Impaired People",
        "status": "running",
        "supported_languages": sorted(SUPPORTED_LANGUAGES),
    }


# ═════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    from src.crud import get_user_by_email

    if get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = create_user(db, payload)
    return user


@app.post("/api/auth/login", response_model=Token)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/auth/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


# ═════════════════════════════════════════════════════════════════════════════
# DETECTIONS (manual CRUD)
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/detections", response_model=DetectionOut, status_code=status.HTTP_201_CREATED)
def create_detection(
    payload: DetectionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return save_detection(db, current_user.id, payload)


@app.post(
    "/api/detections/batch",
    response_model=list[DetectionOut],
    status_code=status.HTTP_201_CREATED,
)
def create_detection_batch(
    payload: list[DetectionItem],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return save_detections(
        db,
        current_user.id,
        [detection.model_dump() for detection in payload],
    )


@app.get("/api/detections", response_model=list[DetectionOut])
def list_user_detections(
    limit: int = Query(default=50, ge=1, le=200),
    danger_level: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_detections(db, current_user.id, limit, danger_level)


@app.get("/api/detections/stats", response_model=StatsOut)
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_stats(db, current_user.id)


@app.delete("/api/detections")
def delete_detections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cleared = clear_detections(db, current_user.id)
    return {"deleted": cleared}


# ═════════════════════════════════════════════════════════════════════════════
# IMAGE DECODING HELPER
# ═════════════════════════════════════════════════════════════════════════════

def decode_image(image_data: bytes) -> Any:
    """
    Decode raw bytes into an OpenCV image (BGR numpy array).

    Raises HTTPException 503 if OpenCV/numpy aren't installed.
    """
    try:
        import cv2
        import numpy as np
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image processing dependencies are missing. Run `uv sync --locked`.",
        ) from exc

    return cv2.imdecode(np.frombuffer(image_data, dtype=np.uint8), cv2.IMREAD_COLOR)


# ═════════════════════════════════════════════════════════════════════════════
# AI DETECTION — accepts ?language=xx
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/detect", response_model=DetectResponse, tags=["Detection"])
def detect_objects(
    image: UploadFile = File(...),
    language: str = Query(
        "en",
        description="ISO 639-1 language code for the voice alert (e.g. en, am, es, fr, ar)",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DetectResponse:
    """
    Detect objects in an uploaded camera frame.

    Query parameters:
        language: 2-letter code; falls back to English if unsupported.

    Returns:
        Width/height of the image, list of enriched detections,
        and a localized voice message.
    """
    # Validate the image type
    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a JPEG, PNG, or WebP image.",
        )

    # Read up to 10 MiB + 1 byte (to detect oversize)
    image_data = image.file.read(MAX_IMAGE_BYTES + 1)
    if not image_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image is empty.",
        )
    if len(image_data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image is too large. Maximum size is 10 MiB.",
        )

    # Decode to numpy array
    frame = decode_image(image_data)
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file could not be decoded as an image.",
        )

    height, width = frame.shape[:2]

    # Run YOLO
    try:
        raw_detections = detector.detect(frame)
    except DetectorUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    # Enrich with distance, direction, danger level
    detections = enrich_detections(raw_detections, width, height)

    # Save to database (only danger/warning rows are kept)
    try:
        save_detections(db, current_user.id, detections)
    except Exception as exc:
        print(f"⚠️  Could not save detections: {exc}")

    # Build localized speech and an English voice fallback for devices missing this locale.
    lang = language if language in SUPPORTED_LANGUAGES else "en"
    message = build_message(detections, language=lang)
    fallback_message = (
        build_message(detections, language="en")
        if lang != "en"
        else None
    )

    return DetectResponse(
        width=width,
        height=height,
        detections=detections,
        message=message,
        fallback_message=fallback_message,
        count=len(detections),
    )


# ═════════════════════════════════════════════════════════════════════════════
# SERVE BUILT FRONTEND (production)
# ═════════════════════════════════════════════════════════════════════════════

frontend_dist = "frontend/dist"
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=frontend_dist + "/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(frontend_dist + "/index.html")